import unittest
from fastapi.testclient import TestClient
from video_farm.web import app
from video_farm import db

client = TestClient(app, base_url="http://127.0.0.1:8088")
HEADERS = {"Origin": "http://127.0.0.1:8088"}

class TestApiBatchEngine(unittest.TestCase):
    def test_vids_batch_import_with_engine_vids(self):
        clean_json = [
            {
                "name": "镜头A",
                "mode": "first_last_frame",
                "prompt": "推近特写",
                "duration": 8
            }
        ]
        resp = client.post("/api/vids/batch_import", json={
            "import_mode": "new",
            "engine": "vids",
            "auto_start": False,
            "data": clean_json
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        wf = data["workflow"]
        self.assertEqual(wf.get("engine"), "vids")
        self.assertEqual(wf["shots"][0].get("engine"), "vids")

    def test_vids_batch_import_with_engine_flow(self):
        clean_json = [
            {
                "name": "镜头B",
                "mode": "first_last_frame",
                "prompt": "全景拉远",
                "duration": 8
            }
        ]
        resp = client.post("/api/vids/batch_import", json={
            "import_mode": "new",
            "engine": "flow",
            "auto_start": False,
            "data": clean_json
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        wf = data["workflow"]
        self.assertEqual(wf.get("engine"), "flow")
        self.assertEqual(wf["shots"][0].get("engine"), "flow")

    def test_main_batch_import_with_engine_vids(self):
        clean_shots = [
            {
                "prompt": "主控台测试镜头Vids",
                "duration_sec": 8
            }
        ]
        resp = client.post("/api/tasks/batch", json={
            "shots": clean_shots,
            "engine": "vids"
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        task_id = data["task_ids"][0]
        task = db.get_task(task_id)
        self.assertEqual(task.engine, "vids")

    def test_main_batch_import_with_engine_flow(self):
        clean_shots = [
            {
                "prompt": "主控台测试镜头Flow",
                "duration_sec": 8
            }
        ]
        resp = client.post("/api/tasks/batch", json={
            "shots": clean_shots,
            "engine": "flow"
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        task_id = data["task_ids"][0]
        task = db.get_task(task_id)
        self.assertEqual(task.engine, "flow")

if __name__ == "__main__":
    unittest.main()
