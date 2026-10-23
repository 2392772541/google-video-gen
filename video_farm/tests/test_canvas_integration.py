import unittest
import json
import base64
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from video_farm.web import app, DB_PATH, OUTPUTS_DIR
from video_farm import db
from video_farm.models import Task

class CanvasIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8088")

    def test_canvas_page_served_at_200(self):
        resp = self.client.get("/canvas")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("canvas-iframe", resp.text)
        self.assertIn("http://127.0.0.1:3000/", resp.text)

    def test_canvas_status_endpoint(self):
        resp = self.client.get("/api/canvas/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("canvas_app", data)
        self.assertIn("canvas_proxy", data)
        self.assertIn("cliproxyapi", data)
        self.assertIn("ports", data)
        self.assertEqual(data["ports"]["canvas"], 3000)
        self.assertEqual(data["ports"]["farm"], 8088)

    def test_canvas_recent_media_endpoint(self):
        now_str = datetime.now().astimezone().isoformat()
        dummy_img = OUTPUTS_DIR / "dummy_test_canvas.png"
        dummy_img.write_bytes(b"fake_png_bytes")
        dummy_vid = OUTPUTS_DIR / "dummy_test_canvas.mp4"
        dummy_vid.write_bytes(b"fake_mp4_bytes")

        t1 = Task(id="test_canvas_t1", prompt="测试生图任务", task_type="image", status="completed",
                  output_image_paths=json.dumps([str(dummy_img)]), finish_time=now_str)
        t2 = Task(id="test_canvas_t2", prompt="测试生视频任务", task_type="video", status="completed",
                  output_video_path=str(dummy_vid), finish_time=now_str)
        db.add_task(t1, DB_PATH)
        db.add_task(t2, DB_PATH)

        resp = self.client.get("/api/canvas/recent-media?limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        names = [item.get("name") for item in data]
        self.assertTrue(any("测试生图任务" in n for n in names))
        self.assertTrue(any("测试生视频任务" in n for n in names))

    def test_canvas_navigation_in_all_shells(self):
        static_dir = Path(__file__).resolve().parents[1] / "static"
        for fname in ["index.html", "vids.html", "canvas.html"]:
            p = static_dir / fname
            self.assertTrue(p.is_file(), f"{fname} should exist")
            text = p.read_text("utf-8")
            self.assertIn('href="/canvas"', text, f"{fname} should contain link to /canvas")
            self.assertIn('id="nav-infinite-canvas"', text, f"{fname} should contain nav-infinite-canvas ID")

    def test_loopback_3000_cors_permitted_untrusted_rejected(self):
        # Allowed loopback 3000 (127.0.0.1)
        r_local1 = self.client.get("/api/canvas/status", headers={"Origin": "http://127.0.0.1:3000"})
        self.assertEqual(r_local1.status_code, 200)

        # Allowed loopback 3000 (localhost)
        r_local2 = self.client.get("/api/canvas/status", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(r_local2.status_code, 200)

        # Rejected untrusted origin
        r_bad = self.client.get("/api/canvas/status", headers={"Origin": "https://attacker.com"})
        self.assertEqual(r_bad.status_code, 403)

    def test_canvas_import_to_farm_base64_image(self):
        fake_png = b"fake_image_content"
        b64 = "data:image/png;base64," + base64.b64encode(fake_png).decode()
        resp = self.client.post("/api/canvas/import-to-farm", json={
            "data_url": b64,
            "media_type": "image",
            "prompt": "画布生成的概念海报"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("media_type"), "image")
        self.assertTrue(data.get("filename").startswith("canvas_"))
        self.assertTrue(data.get("filename").endswith(".png"))
        t = db.get_task(data["task_id"], DB_PATH)
        self.assertIsNotNone(t)
        self.assertEqual(t.engine, "canvas")
        self.assertEqual(t.status, "completed")

    def test_canvas_import_to_farm_base64_video(self):
        fake_mp4 = b"fake_video_content"
        b64 = "data:video/mp4;base64," + base64.b64encode(fake_mp4).decode()
        resp = self.client.post("/api/canvas/import-to-farm", json={
            "data_url": b64,
            "media_type": "video",
            "prompt": "画布生成的运镜视频"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("media_type"), "video")
        self.assertTrue(data.get("filename").endswith(".mp4"))

    def test_canvas_import_invalid_params(self):
        r1 = self.client.post("/api/canvas/import-to-farm", json={"prompt": "空内容"})
        self.assertEqual(r1.status_code, 400)

        r2 = self.client.post("/api/canvas/import-to-farm", json={
            "data_url": "data:image/png;base64,AAAA",
            "media_type": "exe"
        })
        self.assertEqual(r2.status_code, 400)

if __name__ == "__main__":
    unittest.main(verbosity=2)
