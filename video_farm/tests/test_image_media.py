"""Image URLs must serve this attempt, not silently point to missing/stale media."""
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
from video_farm import web


def test_nested_output_image_roundtrip(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    picture = outputs / "task_image_test" / "attempt_current" / "generated.png"
    picture.parent.mkdir(parents=True)
    Image.new("RGB", (128, 128), "navy").save(picture)
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    response = client.get("/media/outputs/task_image_test/attempt_current/generated.png")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/png"
    assert response.content == picture.read_bytes()


def test_flat_output_image_backwards_compatible(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    picture = outputs / "legacy.png"
    Image.new("RGB", (64, 64), "green").save(picture)
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    response = TestClient(web.app, base_url="http://127.0.0.1:8088").get("/media/outputs/legacy.png")
    assert response.status_code == 200
    assert response.content == picture.read_bytes()


def test_output_image_traversal_rejected(tmp_path, monkeypatch):
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    outside = tmp_path / "private.png"
    Image.new("RGB", (64, 64), "red").save(outside)
    monkeypatch.setattr(web, "OUTPUTS_DIR", outputs)
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    for name in ("%2e%2e%2fprivate.png", "%2e%2e%5cprivate.png"):
        response = client.get("/media/outputs/" + name)
        assert response.status_code == 404
        assert response.content != outside.read_bytes()
