import unittest
from fastapi.testclient import TestClient
from video_farm.web import app, DB_PATH
from video_farm import db

class SystemHealthAndCorsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, base_url="http://127.0.0.1:8088")

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
