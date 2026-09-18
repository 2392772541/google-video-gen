"""
api_client.py
-------------
跨会话 / 跨脚本调用本地视频工坊 (Video Farm) 的轻量 Python 客户端。
服务端默认监听: http://127.0.0.1:8088
"""

import os
import sys
import time
import json
import argparse
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = os.environ.get("VIDEO_FARM_URL", "http://127.0.0.1:8088")

def request_json(endpoint: str, method="GET", form_data=None):
    url = f"{BASE_URL}{endpoint}"
    if form_data:
        data_bytes = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, method=method)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        req = urllib.request.Request(url, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Error] 请求失败 [{method} {url}]: {e}")
        return None

def check_status():
    return request_json("/api/overview")

def get_profiles():
    return request_json("/api/profiles")

def get_tasks():
    return request_json("/api/tasks")

def get_task(task_id: str):
    return request_json(f"/api/tasks/{task_id}")

def submit_image_task(prompt: str, ref_image=None, model="nano2", aspect="16:9", priority=10):
    form_data = {
        "prompt": prompt,
        "model": model,
        "aspect_ratio": aspect,
        "priority": priority
    }
    if ref_image:
        form_data["ref_image_path"] = str(Path(ref_image).resolve())
    return request_json("/api/tasks/create-image", method="POST", form_data=form_data)

def submit_video_task(prompt: str, start_frame: str, end_frame=None, aspect="16:9", duration=8, model="veo-lite", priority=10):
    form_data = {
        "engine": "flow",
        "prompt": prompt,
        "model": model,
        "start_image_path": str(Path(start_frame).resolve()),
        "aspect_ratio": aspect,
        "duration_sec": duration,
        "priority": priority
    }
    if end_frame:
        form_data["end_image_path"] = str(Path(end_frame).resolve())
    return request_json("/api/tasks/create", method="POST", form_data=form_data)

def wait_task(task_id: str, timeout_sec=600, poll_interval=5):
    print(f"[*] 等待任务 {task_id} 完成...")
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        res = get_task(task_id)
        if not res:
            time.sleep(poll_interval)
            continue
        status = res.get("status")
        if status == "completed":
            print(f"\n[Success] 任务成功! 产物路径: {res.get('output_video_path')}")
            return res
        elif status in ["failed", "cancelled"]:
            print(f"\n[Failed] 任务执行失败: {res.get('error_message')}")
            return res
        elif status in ["running", "queued"]:
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(poll_interval)
        else:
            time.sleep(poll_interval)
    print(f"\n[Timeout] 任务 {task_id} 超时 ({timeout_sec}s)")
    return None

def main():
    parser = argparse.ArgumentParser(description="Video Farm API 客户端")
    sub = parser.add_subparsers(dest="subcmd")

    sub.add_parser("status", help="检查系统概览状态")
    sub.add_parser("profiles", help="查看各 Google 账号状态")
    sub.add_parser("tasks", help="查看任务列表")

    p_get = sub.add_parser("get", help="查看指定任务")
    p_get.add_argument("task_id", help="任务 ID")

    p_img = sub.add_parser("image", help="提交生图任务")
    p_img.add_argument("--prompt", required=True, help="生图提示词")
    p_img.add_argument("--ref", default=None, help="参考图路径")
    p_img.add_argument("--aspect", default="16:9", help="画幅比例 (16:9 / 9:16)")
    p_img.add_argument("--model", default="nano2", help="模型 (nano2 / nano-pro)")
    p_img.add_argument("--wait", action="store_true", help="阻塞等待完成")

    p_vid = sub.add_parser("video", help="提交生视频任务")
    p_vid.add_argument("--prompt", required=True, help="生视频提示词")
    p_vid.add_argument("--start", required=True, help="首帧图片路径")
    p_vid.add_argument("--end", default=None, help="尾帧图片路径")
    p_vid.add_argument("--aspect", default="16:9", help="画幅比例 (16:9 / 9:16)")
    p_vid.add_argument("--duration", type=int, default=8, help="视频时长(秒)")
    p_vid.add_argument("--model", default="veo-lite", help="模型 (veo-lite / veo-2.0-generate-001)")
    p_vid.add_argument("--wait", action="store_true", help="阻塞等待完成")

    args = parser.parse_args()
    if args.subcmd == "status":
        print(json.dumps(check_status(), indent=2, ensure_ascii=False))
    elif args.subcmd == "profiles":
        print(json.dumps(get_profiles(), indent=2, ensure_ascii=False))
    elif args.subcmd == "tasks":
        print(json.dumps(get_tasks(), indent=2, ensure_ascii=False))
    elif args.subcmd == "get":
        print(json.dumps(get_task(args.task_id), indent=2, ensure_ascii=False))
    elif args.subcmd == "image":
        res = submit_image_task(args.prompt, ref_image=args.ref, model=args.model, aspect=args.aspect)
        print(f"Task created: {res}")
        if args.wait and res and "id" in res:
            wait_task(res["id"])
    elif args.subcmd == "video":
        res = submit_video_task(args.prompt, start_frame=args.start, end_frame=args.end, aspect=args.aspect, duration=args.duration, model=args.model)
        print(f"Task created: {res}")
        if args.wait and res and "id" in res:
            wait_task(res["id"])
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
