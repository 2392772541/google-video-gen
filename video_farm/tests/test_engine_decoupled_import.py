import unittest
import tempfile
import sqlite3
from pathlib import Path
from video_farm import db, vids_workflow
from video_farm.models import Task, Profile

class TestEngineDecoupledImport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "tasks.db"
        db.init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalize_imported_json_without_engine_uses_default_engine(self):
        # 用户提供的纯净 JSON，不带 engine 字段
        clean_json = [
            {
                "name": "镜头01",
                "mode": "first_last_frame",
                "image_url": "C:/images/01_start.png",
                "end_image_url": "C:/images/01_end.png",
                "prompt": "麦田金黄，微风拂动",
                "duration": 8
            },
            {
                "name": "镜头02",
                "mode": "image2video",
                "image_url": "C:/images/02_start.png",
                "prompt": "微观根系，养分流动",
                "duration": 8
            }
        ]

        # 1. 模拟用户在前端单选 [●] Google Vids
        res_vids = vids_workflow.normalize_imported_workflow_json(clean_json, default_engine="vids")
        self.assertEqual(res_vids["engine"], "vids")
        self.assertEqual(len(res_vids["shots"]), 2)
        for s in res_vids["shots"]:
            self.assertEqual(s["engine"], "vids")

        # 2. 模拟用户在前端单选 (○) Google Flow
        res_flow = vids_workflow.normalize_imported_workflow_json(clean_json, default_engine="flow")
        self.assertEqual(res_flow["engine"], "flow")
        self.assertEqual(len(res_flow["shots"]), 2)
        for s in res_flow["shots"]:
            self.assertEqual(s["engine"], "flow")

    def test_db_workflow_and_shot_persist_engine(self):
        # 测试数据库能够正确持久化 engine 字段
        wf_vids = db.create_vids_workflow(
            title="Vids工程",
            engine="vids",
            db_path=self.db_path
        )
        self.assertEqual(wf_vids.get("engine"), "vids")

        shot1 = db.create_vids_shot(
            workflow_id=wf_vids["id"],
            name="镜头1",
            prompt="测试提示词",
            engine="vids",
            db_path=self.db_path
        )
        self.assertEqual(shot1.get("engine"), "vids")

        # 读取并验证
        read_wf = db.get_vids_workflow(wf_vids["id"], db_path=self.db_path)
        self.assertEqual(read_wf.get("engine"), "vids")
        self.assertEqual(read_wf["shots"][0].get("engine"), "vids")

        # 更新 engine 为 flow
        db.update_vids_workflow(wf_vids["id"], {"engine": "flow"}, db_path=self.db_path)
        db.update_vids_shot(shot1["id"], {"engine": "flow"}, db_path=self.db_path)

        read_wf_after = db.get_vids_workflow(wf_vids["id"], db_path=self.db_path)
        self.assertEqual(read_wf_after.get("engine"), "flow")
        self.assertEqual(read_wf_after["shots"][0].get("engine"), "flow")

if __name__ == "__main__":
    unittest.main()
