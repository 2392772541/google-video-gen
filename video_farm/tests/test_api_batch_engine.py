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

    def test_running_task_stop_and_force_cancel(self):
        resp = client.post("/api/tasks/batch", json={
            "shots": [{"prompt": "测试中断镜头", "duration_sec": 8}],
            "engine": "flow"
        }, headers=HEADERS)
        task_id = resp.json()["task_ids"][0]
        
        c = db.get_db_connection()
        with c:
            c.execute("UPDATE tasks SET status='running' WHERE id=?", (task_id,))
        c.close()
        
        r_conflict = client.post(f"/api/tasks/{task_id}/cancel", headers=HEADERS)
        self.assertEqual(r_conflict.status_code, 409)
        
        r_stop = client.post(f"/api/tasks/{task_id}/stop", headers=HEADERS)
        self.assertEqual(r_stop.status_code, 200)
        self.assertTrue(r_stop.json()["success"])
        t_after = db.get_task(task_id)
        self.assertEqual(t_after.status, "cancelled")

    def test_batch_cancel_running_and_queued(self):
        resp = client.post("/api/tasks/batch", json={
            "shots": [{"prompt": "批量中止1", "duration_sec": 8}, {"prompt": "批量中止2", "duration_sec": 8}],
            "engine": "vids"
        }, headers=HEADERS)
        tids = resp.json()["task_ids"]
        
        c = db.get_db_connection()
        with c:
            c.execute("UPDATE tasks SET status='running' WHERE id=?", (tids[0],))
        c.close()
        
        r_batch = client.post("/api/tasks/batch/cancel", json={"task_ids": tids}, headers=HEADERS)
        self.assertEqual(r_batch.status_code, 200)
        self.assertEqual(r_batch.json()["cancelled_count"], 2)
        
        self.assertEqual(db.get_task(tids[0]).status, "cancelled")
        self.assertEqual(db.get_task(tids[1]).status, "cancelled")

if __name__ == "__main__":
    unittest.main()
