import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from video_farm.web import app
from video_farm import db

client = TestClient(app, base_url="http://127.0.0.1:8088")
HEADERS = {"Origin": "http://127.0.0.1:8088"}

USER_SHOTS_DATA = [
  {
    "engine": "flow",
    "prompt": "镜头1：以提供的首帧开场、尾帧收束，10秒，16:9。真实烈日麦田，先短暂停留，镜头沿前景发黄麦叶快速俯冲。经过叶表气孔的短暂微观过渡后进入暗青绿细胞内部，最后稳定呈现半透明膜包围的暗淡叶绿体和堆叠片层；左下弱蓝紫颗粒，细胞空间有湿润有机膜质感。先快后稳，微观主体不能凭空扭曲。无字幕、无人、无产品、无标志。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/01_首帧_烈日干旱麦田.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/01_尾帧_暗沉叶片内部.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  },
  {
    "engine": "flow",
    "prompt": "镜头2：首尾帧约束，10秒，16:9。同一休眠叶绿体，堆叠片层暗橄榄绿，半透明外膜、暗青绿背景、上方红色薄光面。镜头缓慢向右环绕约30度，保持同一叶绿体结构；右侧有机组织内逐渐显露琥珀金、电光蓝、银白三条细光轨，保持纵深和有机质感。光轨亮起但叶绿体尚未全面激活。无文字、无图标、无金属工厂、无人、无产品。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/02_首帧_休眠叶绿体与屏障.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/02_尾帧_三条技术通道.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  },
  {
    "engine": "flow",
    "prompt": "镜头3：首尾帧约束，10秒，16:9。保持参考画面的同一构图、同一弯曲有机通道、左侧金色晶体、右侧叶绿体片层。镜头轻微轴向推进。暖琥珀液体沿通道从左向右流动，到达片层后，翡翠绿发光依次沿每层边缘和连接膜扩散。从暗淡到活跃，材料与结构不变，局部生物发光有节奏地增强，避免过曝。无受体锁孔、无齿轮、无注射器、无文字、无人、无产品。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/03_首帧_金色前体进入通道.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/03_尾帧_翡翠绿叶绿体激活.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  },
  {
    "engine": "flow",
    "prompt": "镜头4：首尾帧约束，10秒，16:9。沿同一绿色麦叶表面向右缓慢横移，透明细小棱镜晶体保持原位，阳光从左上照入。机位逐渐降低，叶肉以平滑概念剖面展开；从晶体下方出现细窄清晰的电光蓝光束，逐渐进入半透明绿色叶肉细胞。保留叶脉和湿润细胞质感。光线变化柔顺，避免镭射武器感和燃烧，宏观叶面与微观组织的比例为艺术示意。无文字、无人、无产品。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/04_首帧_纳米晶体叶表.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/04_尾帧_光束进入叶肉.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  },
  {
    "engine": "flow",
    "prompt": "镜头5：首尾帧约束，10秒，16:9。保持同一半透明有机筛管、带孔筛板、深青绿背景。银白细波纹首先沿通道向右前方传播，琥珀金糖液随后向前流动。镜头穿行于通道，抵达一个与通道相连的发育籽粒；最后以尾帧的籽粒剖面收束，内部金色填充逐渐增加，外形自然饱满。银白信号与金色糖液始终分开，不变成金属管道，不制造爆炸或破壳。无文字、无人、无产品。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/05_首帧_糖液与信号起点.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/05_尾帧_籽粒灌浆充盈.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  },
  {
    "engine": "flow",
    "prompt": "镜头6：首尾帧约束，10秒，16:9。以自然饱满、略弯的金色麦穗近景开始，左侧暖阳，真实蓝天与云层。麦穗轻轻随风摆动，镜头平滑后拉、升高，穗头按透视自然变小并消失在田间；最终呈现同色调辽阔金色麦田航拍，真实田块、自然绿边、天空金色光柱。最后稳住尾帧，不能留下巨大麦穗悬在农田上，不出现能量矩阵或文字。无人、无产品、无水印。",
    "start_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/06_首帧_饱满金色麦穗.png",
    "end_image_path": "E:/BaiduNetdiskDownload/视频生成素材打包/光合密码_12张首尾帧与脚本/光合密码_首尾帧与脚本/首尾帧/06_尾帧_壮阔金色麦田.png",
    "aspect_ratio": "16:9",
    "duration_sec": 10,
    "priority": 10
  }
]

class TestUserBatchImportPipeline(unittest.TestCase):
    def test_01_direct_list_post_import(self):
        """测试直接将 JSON 列表 POST 给 /api/vids/batch_import 且 auto_start=False"""
        resp = client.post("/api/vids/batch_import", json=USER_SHOTS_DATA, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["imported_count"], 6)
        wf = data["workflow"]
        self.assertEqual(wf["engine"], "flow")
        self.assertEqual(len(wf["shots"]), 6)
        for s in wf["shots"]:
            self.assertEqual(s["engine"], "flow")
            self.assertEqual(s["mode"], "first_last_frame")
            self.assertEqual(s["duration"], 10)
            self.assertTrue(s["image_url"].endswith(".png"))
            self.assertTrue(s["end_image_url"].endswith(".png"))
        # clean up
        client.delete(f"/api/vids/workflows/{wf['id']}", headers=HEADERS)

    def test_02_ui_wrapper_with_auto_engine_and_auto_start(self):
        """测试 UI 弹窗封装对象提交（engine=auto，auto_start=True），全部6个镜头原子入队"""
        resp = client.post("/api/vids/batch_import", json={
            "engine": "auto",
            "import_mode": "new",
            "auto_start": True,
            "data": USER_SHOTS_DATA
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["imported_count"], 6)
        self.assertTrue(data["auto_started"])
        self.assertEqual(len(data["task_ids"]), 6)
        wf = data["workflow"]
        self.assertEqual(wf["engine"], "flow")
        self.assertEqual(wf["status"], "generating")

        # 检查各分镜任务属性与绑定
        for s, tid in zip(wf["shots"], data["task_ids"]):
            self.assertEqual(s["task_id"], tid)
            self.assertEqual(s["status"], "queued")
            task = db.get_task(tid)
            self.assertIsNotNone(task)
            self.assertEqual(task.engine, "flow")
            self.assertEqual(task.model, "omni-flash")
            self.assertEqual(task.duration_sec, 10)
            self.assertEqual(task.aspect_ratio, "16:9")
            self.assertEqual(task.priority, 10)
            self.assertTrue(Path(task.start_image_path).exists())
            self.assertTrue(Path(task.end_image_path).exists())

        # 清理任务与工作流，避免残留
        for tid in data["task_ids"]:
            client.post(f"/api/tasks/{tid}/cancel", headers=HEADERS)
        client.delete(f"/api/vids/workflows/{wf['id']}", headers=HEADERS)

    def test_03_main_tasks_batch_endpoint(self):
        """测试主控台 /api/tasks/batch 批量接口直接消费该 JSON"""
        resp = client.post("/api/tasks/batch", json=USER_SHOTS_DATA, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["created_count"], 6)
        tids = data["task_ids"]
        self.assertEqual(len(tids), 6)
        for tid in tids:
            t = db.get_task(tid)
            self.assertEqual(t.engine, "flow")
            self.assertEqual(t.model, "omni-flash")
            self.assertEqual(t.duration_sec, 10)
            self.assertEqual(t.aspect_ratio, "16:9")
        # cancel all
        client.post("/api/tasks/batch/cancel", json={"task_ids": tids}, headers=HEADERS)

    def test_04_media_file_serving_for_all_assets(self):
        """测试所有 12 张首尾帧图片均可通过 /media/file 路由被前端正常展示"""
        for shot in USER_SHOTS_DATA:
            for key in ("start_image_path", "end_image_path"):
                p = shot[key]
                resp = client.get("/media/file", params={"path": p}, headers=HEADERS)
                self.assertEqual(resp.status_code, 200, f"Failed serving {p}")
                self.assertIn("image/png", resp.headers.get("content-type", ""))
                self.assertGreater(len(resp.content), 1000000)

    def test_05_export_json_format_integrity(self):
        """测试导入后导出的 JSON 结构保持完整且规范"""
        resp = client.post("/api/vids/batch_import", json={
            "import_mode": "new",
            "auto_start": False,
            "data": USER_SHOTS_DATA
        }, headers=HEADERS)
        self.assertEqual(resp.status_code, 200)
        wf_id = resp.json()["workflow"]["id"]

        exp_resp = client.get(f"/api/vids/workflows/{wf_id}/export_json", headers=HEADERS)
        self.assertEqual(exp_resp.status_code, 200)
        exp_data = exp_resp.json()
        self.assertEqual(exp_data["engine"], "flow")
        self.assertEqual(len(exp_data["shots"]), 6)
        self.assertEqual(exp_data["shots"][0]["engine"], "flow")
        self.assertEqual(exp_data["shots"][0]["duration"], 10)
        self.assertEqual(exp_data["shots"][0]["mode"], "first_last_frame")

        client.delete(f"/api/vids/workflows/{wf_id}", headers=HEADERS)

if __name__ == "__main__":
    unittest.main()
