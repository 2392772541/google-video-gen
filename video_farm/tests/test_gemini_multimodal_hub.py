import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from video_farm import web, db

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
