"""ASGI regressions for Vids imports; never starts a real generation job."""
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from video_farm import db, web, vids_workflow


@pytest.fixture
def client(monkeypatch):
    conn = db.get_db_connection()
    actual = Path(conn.execute("PRAGMA database_list").fetchone()["file"])
    conn.close()
    monkeypatch.setattr(web, "DB_PATH", actual)
    monkeypatch.setattr(web.mgr, "scheduler", SimpleNamespace(lock=threading.Lock(), active_tasks={}))
    # Do not enter TestClient as a context manager: lifespan must not start workers.
    return TestClient(web.app, base_url="http://127.0.0.1:8088", raise_server_exceptions=False)


def payload(**changes):
    data = {"title": "isolated draft", "duration_per_shot": 6,
            "shots": [{"prompt": "gentle movement", "duration": 6, "engine": "vids"}]}
    data.update(changes)
    return {"auto_start": False, "data": data}


def task_count():
    conn = db.get_db_connection()
    try:
        return conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def test_normalization_without_document_url_leaves_new_project_unbound():
    result = vids_workflow.normalize_imported_workflow_json(payload()["data"])
    assert result["doc_url"] == ""
    assert vids_workflow.SAMPLE_BATCH_IMPORT_DATA["doc_url"] == ""


def test_normalization_preserves_explicit_and_existing_document_urls():
    url = "https://docs.google.com/videos/d/explicit_test_document/edit"
    assert vids_workflow.normalize_imported_workflow_json(payload(doc_url=url)["data"])["doc_url"] == url
    assert vids_workflow.normalize_imported_workflow_json(
        payload()["data"], default_workflow={"doc_url": url})["doc_url"] == url


@pytest.mark.parametrize("url", [None, "", "https://docs.google.com/videos/d/explicit_test_document/edit"])
def test_new_draft_import_binds_only_an_explicit_document_url(client, url):
    response = client.post("/api/vids/batch_import", json=payload(**({} if url is None else {"doc_url": url})))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow"]["doc_url"] == (url or "")
    assert not body["task_ids"] and not body["auto_started"]
    assert task_count() == 0


def test_append_draft_preserves_existing_document_url(client):
    url = "https://docs.google.com/videos/d/existing_test_document/edit"
    first = client.post("/api/vids/batch_import", json=payload(doc_url=url))
    assert first.status_code == 200, first.text
    request = payload()
    request.update(workflow_id=first.json()["workflow"]["id"], import_mode="append")
    response = client.post("/api/vids/batch_import", json=request)
    assert response.status_code == 200, response.text
    assert response.json()["workflow"]["doc_url"] == url
    assert task_count() == 0


def test_valid_paired_frames_import_then_generate_success(client, tmp_path):
    start, end = tmp_path/"start.png", tmp_path/"end.png"
    Image.new("RGB", (64, 36), "blue").save(start)
    Image.new("RGB", (64, 36), "red").save(end)
    request = payload(shots=[{"prompt": "gentle movement", "duration": 6,
        "engine": "vids", "mode": "first_last_frame",
        "start_image_path": str(start), "end_image_path": str(end)}])
    imported = client.post("/api/vids/batch_import", json=request)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert not body["auto_started"] and not body["task_ids"]
    assert task_count() == 0
    shot = body["workflow"]["shots"][0]
    response = client.post(f"/api/vids/shots/{shot['id']}/generate", json={})
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    assert task_count() == 1
    current = db.get_vids_shot(shot["id"])
    assert current["engine"] == "vids" and current["mode"] == "first_last_frame"
    assert current["image_url"] == str(start) and current["end_image_url"] == str(end)
    assert current["task_id"]


def test_empty_account_ui_does_not_hardcode_a_personal_project():
    source = (Path(__file__).parents[1]/"static"/"vids.js").read_text("utf-8")
    initial = source.split("async function loadInitialWorkflow()", 1)[1].split("return;", 1)[0]
    assert 'doc_url: ""' in initial
    assert "docs.google.com/videos/d/" not in initial
