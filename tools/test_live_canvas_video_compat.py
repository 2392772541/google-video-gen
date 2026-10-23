import urllib.request
import json
from video_farm import db
from video_farm.web import DB_PATH

def run_tests():
    print("=== 1. 验证 /v1/models 模型发现 ===")
    with urllib.request.urlopen("http://127.0.0.1:8088/v1/models", timeout=5) as r:
        data = json.loads(r.read().decode())
        model_ids = [m["id"] for m in data.get("data", [])]
        print("Discovered Models:", model_ids)
        assert "flow" in model_ids
        assert "vids" in model_ids
        assert "gemini" in model_ids

    print("=== 2. 验证 /v1/videos (POST) 创建 Google Flow 视频生成任务 ===")
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    parts = [
        "--" + boundary,
        'Content-Disposition: form-data; name="model"',
        "",
        "flow",
        "--" + boundary,
        'Content-Disposition: form-data; name="prompt"',
        "",
        "金色麦浪微风起伏镜头",
        "--" + boundary,
        'Content-Disposition: form-data; name="seconds"',
        "",
        "6",
        "--" + boundary + "--",
        ""
    ]
    body = "\r\n".join(parts).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8088/v1/videos", data=body, headers={
        "Content-Type": "multipart/form-data; boundary=" + boundary
    })
    with urllib.request.urlopen(req, timeout=5) as r:
        task_res = json.loads(r.read().decode())
        print("Flow Video Task Created:", task_res)
        flow_task_id = task_res["id"]
        assert task_res["status"] == "queued"

    print("=== 3. 验证 /v1/videos/{task_id} (GET) 状态轮询 ===")
    with urllib.request.urlopen("http://127.0.0.1:8088/v1/videos/" + flow_task_id, timeout=5) as r:
        poll_res = json.loads(r.read().decode())
        print("Flow Video Task Poll Status:", poll_res)
        assert poll_res["id"] == flow_task_id
        assert poll_res["status"] in ("pending", "queued", "running")

    db.delete_task(flow_task_id, DB_PATH)
    print("Flow test task cleaned up.")

    print("=== 4. 验证 /v1/videos (POST) 创建 Google Vids 视频生成任务 ===")
    parts_vids = [
        "--" + boundary,
        'Content-Disposition: form-data; name="model"',
        "",
        "vids",
        "--" + boundary,
        'Content-Disposition: form-data; name="prompt"',
        "",
        "科研大棚自动化灌溉展示",
        "--" + boundary,
        'Content-Disposition: form-data; name="seconds"',
        "",
        "8",
        "--" + boundary + "--",
        ""
    ]
    body_vids = "\r\n".join(parts_vids).encode("utf-8")
    req_vids = urllib.request.Request("http://127.0.0.1:8088/v1/videos", data=body_vids, headers={
        "Content-Type": "multipart/form-data; boundary=" + boundary
    })
    with urllib.request.urlopen(req_vids, timeout=5) as r:
        vids_res = json.loads(r.read().decode())
        print("Vids Video Task Created:", vids_res)
        vids_task_id = vids_res["id"]
        assert vids_res["status"] == "queued"

    db.delete_task(vids_task_id, DB_PATH)
    print("Vids test task cleaned up.")
    print("\nALL LIVE INTEGRATION TESTS PASSED 100%!")

if __name__ == "__main__":
    run_tests()
