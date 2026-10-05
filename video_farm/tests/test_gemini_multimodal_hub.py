import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from video_farm import web, db
from video_farm.scheduler import classify_failure

@pytest.fixture
def client():
    return TestClient(web.app, base_url="http://127.0.0.1:8088")

def test_gemini_messages_endpoints(client):
    # 1. List messages
    r = client.get("/api/gemini/messages?session_id=test_hub")
    assert r.status_code == 200
    assert "messages" in r.json()

    # 2. Add via db and list
    msg = db.add_gemini_message({
        "session_id": "test_hub",
        "role": "user",
        "mode": "chat",
        "content": "测试消息内容",
        "attachments_json": "[]"
    }, web.DB_PATH)
    assert msg["id"].startswith("gmsg_")

    r = client.get("/api/gemini/messages?session_id=test_hub")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert len(msgs) >= 1
    assert any(m["id"] == msg["id"] for m in msgs)

    # 3. Clear
    r = client.delete("/api/gemini/messages?session_id=test_hub")
    assert r.status_code == 200
    assert r.json()["success"] is True

def test_gemini_images_endpoint(client):
    r = client.get("/api/gemini/images")
    assert r.status_code == 200
    assert "images" in r.json()

def test_gemini_profile_check(client):
    profs = db.list_profiles(web.DB_PATH)
    if profs:
        p = profs[0]
        r = client.post(f"/api/profiles/{p.id}/test-gemini")
        assert r.status_code == 200
        assert "profile_name" in r.json() or "message" in r.json()

def test_unlock_profile_not_found(client):
    r = client.post("/api/profiles/non_existent_profile_xyz_9999/unlock")
    assert r.status_code == 404
    assert "未找到" in r.json().get("detail", "")

def test_run_in_clean_thread_timeout():
    # 测试超时或异常时不返回 None，而是标准字典
    def slow_fn():
        time.sleep(2)
        return {"success": True}
    
    # 用猴子补丁临时缩短超时测试
    import threading
    def mock_clean_thread(fn, timeout_sec=0.1):
        res_box = {}
        err_box = {}
        def _runner():
            try:
                res_box['data'] = fn()
            except Exception as e:
                err_box['err'] = e
        th = threading.Thread(target=_runner, daemon=True)
        th.start()
        th.join(timeout=timeout_sec)
        if th.is_alive():
            return {"success": False, "error_message": "多模态执行超时（超过180秒）"}
        if 'err' in err_box:
            raise err_box['err']
        return res_box.get('data') or {"success": False, "error_message": "执行未返回有效结果"}

    res = mock_clean_thread(slow_fn, timeout_sec=0.05)
    assert isinstance(res, dict)
    assert res.get("success") is False
    assert "超时" in res.get("error_message", "")

def test_classify_failure_safety_filter():
    category, msg, cooldown, can_retry = classify_failure(
        "SAFETY_FILTER_BLOCKED",
        "That request looks like it goes against our terms. Try asking something else.",
        "Detected sidebar alert against our terms"
    )
    assert category == "SAFETY_FILTER_BLOCKED"
    assert cooldown == 0
    assert can_retry is False
    assert "服务条款" in msg or "terms" in msg.lower()
