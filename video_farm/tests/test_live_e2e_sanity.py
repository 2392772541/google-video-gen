import urllib.request
import json
import pytest

def test_live_e2e_smoke():
    """全链路真实 HTTP 端点烟雾验证测试"""
    def req(url, method="GET", data=None):
        headers = {"Content-Type": "application/json"} if data else {}
        body = json.dumps(data).encode("utf-8") if data else None
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status, r.headers, r.read().decode("utf-8")

    try:
        s, h, _ = req("http://127.0.0.1:8088/")
    except Exception:
        pytest.skip("8088 端口未启动，跳过 live e2e smoke 测试")

    assert s == 200 and "no-cache" in h.get("Cache-Control", "")

    s, h, _ = req("http://127.0.0.1:8088/vids")
    assert s == 200 and "no-cache" in h.get("Cache-Control", "")

    s, h, _ = req("http://127.0.0.1:8088/static/app.js")
    assert s == 200 and "no-cache" in h.get("Cache-Control", "")

    s, _, body = req("http://127.0.0.1:8088/api/overview")
    assert s == 200

    s, _, body = req("http://127.0.0.1:8088/api/vids/overview")
    assert s == 200

    # 测试创建工程与导入分镜
    s, _, body = req("http://127.0.0.1:8088/api/vids/workflows", method="POST", data={
        "title": "Smoke 验收工程",
        "resolution": "1080p",
        "model_name": "Omni",
        "engine": "vids"
    })
    assert s == 200
    wf_id = json.loads(body)["id"]

    try:
        s, _, body = req("http://127.0.0.1:8088/api/vids/batch_import", method="POST", data={
            "workflow_id": wf_id,
            "import_mode": "append",
            "data": [{
                "name": "镜头Smoke",
                "mode": "first_last_frame",
                "image_url": "start.png",
                "end_image_url": "end.png",
                "prompt": "金色麦田",
                "duration": 8,
                "resolution": "1080p"
            }]
        })
        assert s == 200
        shot_id = json.loads(body)["workflow"]["shots"][0]["id"]

        # 下发分镜
        s, _, body = req(f"http://127.0.0.1:8088/api/vids/shots/{shot_id}/generate", method="POST")
        assert s == 200

        # 强行中止
        s, _, body = req(f"http://127.0.0.1:8088/api/vids/shots/{shot_id}/cancel", method="POST")
        assert s == 200
    finally:
        req(f"http://127.0.0.1:8088/api/vids/workflows/{wf_id}", method="DELETE")
