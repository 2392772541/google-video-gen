import unittest
import io
from PIL import Image
from fastapi.testclient import TestClient
from video_farm.web import app, DB_PATH
from video_farm import db
from video_farm.models import Task

class SystemHealthAndCorsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8088")

    def test_canvas_models_discovery(self):
        resp = self.client.get("/v1/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("object"), "list")
        model_ids = [m["id"] for m in data.get("data", [])]
        self.assertIn("flow", model_ids)
        self.assertIn("vids", model_ids)
        self.assertIn("gemini", model_ids)

    def test_canvas_create_video_task_flow(self):
        resp = self.client.post("/v1/videos", data={
            "model": "flow",
            "prompt": "微风吹过麦田，金色麦浪起伏",
            "seconds": "6",
            "ratio": "16:9"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        self.assertEqual(data["status"], "queued")
        self.assertEqual(data["model"], "flow")

        # Poll task status
        task_id = data["id"]
        poll_resp = self.client.get(f"/v1/videos/{task_id}")
        self.assertEqual(poll_resp.status_code, 200)
        pdata = poll_resp.json()
        self.assertEqual(pdata["id"], task_id)
        self.assertEqual(pdata["status"], "pending")

        # Clean up
        db.delete_task(task_id, DB_PATH)

    def test_canvas_create_video_task_vids(self):
        resp = self.client.post("/v1/videos", data={
            "model": "vids",
            "prompt": "实验室分子结构动画",
            "seconds": "8",
            "ratio": "9:16"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("id", data)
        task = db.get_task(data["id"], DB_PATH)
        self.assertIsNotNone(task)
        self.assertEqual(task.engine, "vids")
        self.assertEqual(task.aspect_ratio, "9:16")
        self.assertEqual(task.duration_sec, 8)

        # Clean up
        db.delete_task(data["id"], DB_PATH)

    def test_canvas_create_video_task_first_and_last_frames(self):
        buf1 = io.BytesIO()
        Image.new("RGB", (100, 100), color="blue").save(buf1, format="PNG")
        buf1.seek(0)

        buf2 = io.BytesIO()
        Image.new("RGB", (100, 100), color="red").save(buf2, format="PNG")
        buf2.seek(0)

        resp = self.client.post(
            "/v1/videos",
            data={
                "model": "flow",
                "prompt": "首尾帧过渡动态镜头",
                "seconds": "6",
                "mode": "frames"
            },
            files={
                "first_frame": ("start.png", buf1, "image/png"),
                "last_frame": ("end.png", buf2, "image/png")
            }
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        task = db.get_task(data["id"], DB_PATH)
        self.assertIsNotNone(task)
        self.assertTrue(task.start_image_path)
        self.assertTrue(task.end_image_path)

        # Clean up
        db.delete_task(data["id"], DB_PATH)

    def test_health_endpoint_healthy(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "video_farm_studio")
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["database"], "ok")
        self.assertIn("memory_rss_mb", data)
        self.assertIn("disk_free_gb", data)
        self.assertIn("timestamp", data)

    def test_cors_options_preflight_port_3000(self):
        resp = self.client.options("/api/canvas/status", headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type"
        })
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://127.0.0.1:3000")
        self.assertEqual(resp.headers.get("access-control-allow-credentials"), "true")
        self.assertIn("OPTIONS", resp.headers.get("access-control-allow-methods", ""))
        self.assertEqual(resp.headers.get("cross-origin-resource-policy"), "cross-origin")

    def test_cors_get_port_23210_proxy(self):
        resp = self.client.get("/api/canvas/status", headers={
            "Origin": "http://127.0.0.1:23210"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://127.0.0.1:23210")
        self.assertEqual(resp.headers.get("cross-origin-resource-policy"), "cross-origin")

    def test_cors_get_localhost_port_3000(self):
        resp = self.client.get("/api/canvas/status", headers={
            "Origin": "http://localhost:3000"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_cors_untrusted_origin_rejected(self):
        resp = self.client.get("/api/canvas/status", headers={
            "Origin": "http://malicious-website.com"
        })
        self.assertEqual(resp.status_code, 403)

    def test_workflow_status_auto_healing(self):
        # Create a test workflow
        wf = db.create_vids_workflow(
            title="测试自愈工作流",
            style_prompt="现代写实",
            db_path=DB_PATH
        )
        wf_id = wf["id"]
        # Force status to generating
        conn = db.get_db_connection(DB_PATH)
        conn.execute("UPDATE vids_workflows SET status='generating' WHERE id=?", (wf_id,))
        conn.commit()
        conn.close()

        # Query workflow: with no shots, it should auto-heal to draft
        healed_wf = db.get_vids_workflow(wf_id, db_path=DB_PATH)
        self.assertIsNotNone(healed_wf)
        self.assertEqual(healed_wf["status"], "draft")

        # Clean up
        db.delete_vids_workflow(wf_id, db_path=DB_PATH)

if __name__ == "__main__":
    unittest.main()
