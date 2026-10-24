import sys
import uuid
import time
from pathlib import Path

from video_farm.models import Task, Profile
from video_farm.gemini_worker import GeminiWebWorker

def run_real_gemini():
    test_img = Path(r"D:\AI-Projects\infinite-canvas\audit_output_AUDIT_20261024_222501_d1a836.png").resolve()
    assert test_img.exists(), "测试图片不存在"

    task_id = f"gemini_{uuid.uuid4().hex[:8]}"
    print(f"=== 发起真实 Gemini 视频生成任务: {task_id} ===")

    task = Task(
        id=task_id,
        prompt="A golden retriever running happily across green meadow, cinematic lighting",
        aspect_ratio="16:9",
        duration_sec=6,
        model="gemini",
        engine="gemini",
        start_image_path=str(test_img),
        project_id="default"
    )

    profile = Profile(
        id="prof_5a4f2eb4",
        name="gflow-test"
    )

    worker = GeminiWebWorker(
        output_dir=Path("video_farm_data/outputs"),
        timeout_sec=300,
        headless=True
    )

    print("开始调用 worker._execute_browser_task ...")
    res = worker._execute_browser_task(task, profile)
    print("=== 执行结果 ===")
    print("Success:", res.get("success"))
    print("Error code:", res.get("error_code"))
    print("Error message:", res.get("error_message"))
    print("Output video path:", res.get("output_video_path"))
    print("Logs:")
    print(res.get("logs", ""))

if __name__ == "__main__":
    run_real_gemini()
