import json
"""ZIP sorting and downloads against ASGI fixtures, never the production queue."""
import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Task


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    database = tmp_path / "tasks.db"
    db.init_db(database)
    monkeypatch.setattr(web, "DB_PATH", database)
    tasks, contents = [], {}
    for shot in ("05", "04", "03C", "03B", "03A"):
        task = Task(id="zip_" + shot, prompt="镜头" + shot + " 测试", status="completed")
        db.add_task(task, database)
        artifact = tmp_path / (task.id + ".mp4")
        contents[task.id] = (shot.encode() + b"fixture") * 256
        artifact.write_bytes(contents[task.id])
        with db.get_db_connection(database) as conn:
            conn.execute("UPDATE tasks SET output_video_path=? WHERE id=?", (str(artifact), task.id))
        tasks.append(db.get_task(task.id, database))
    return tasks, contents


def test_unit_sort_and_naming(downloads):
    tasks, _ = downloads
    sorted_tasks = sorted(tasks, key=web.get_task_sort_key)
    assert ["%02d%s" % web.parse_shot_info(t.prompt) for t in sorted_tasks] == ["03A", "03B", "03C", "04", "05"]
    for index, (task, shot) in enumerate(zip(sorted_tasks, ("03A", "03B", "03C", "04", "05")), 1):
        assert web.format_ordered_filename(task, index, ".mp4").startswith("%02d_镜头%s" % (index, shot))


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_batch_download_zip(downloads, method):
    tasks, contents = downloads
    ids = [t.id for t in tasks]
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")  # No application lifespan.
    try:
        response = (client.post("/api/tasks/batch-download-zip", json={"task_ids": ids}) if method == "POST"
                    else client.get("/api/tasks/batch-download-zip", params={"task_ids": ",".join(ids)}))
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"
        assert "attachment;" in response.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == 5
            for index, (name, shot) in enumerate(zip(names, ("03A", "03B", "03C", "04", "05")), 1):
                assert name.startswith("%02d_镜头%s" % (index, shot))
                assert archive.read(name) == contents["zip_" + shot]
    finally:
        client.close()

def test_single_task_download_single_image(tmp_path, monkeypatch):
    database = tmp_path / "tasks.db"
    db.init_db(database)
    monkeypatch.setattr(web, "DB_PATH", database)
    img = tmp_path / "img1.png"
    img.write_bytes(b"png_single_image_data")
    task = Task(id="img_task_single", prompt="镜头01 唯美画质", status="completed", task_type="image")
    db.add_task(task, database)
    with db.get_db_connection(database) as conn:
        conn.execute("UPDATE tasks SET output_image_paths=? WHERE id=?", (json.dumps([str(img)]), task.id))
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    try:
        res = client.get(f"/api/tasks/{task.id}/download")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert res.content == b"png_single_image_data"
    finally:
        client.close()


def test_single_task_download_multiple_images_packs_zip(tmp_path, monkeypatch):
    database = tmp_path / "tasks.db"
    db.init_db(database)
    monkeypatch.setattr(web, "DB_PATH", database)
    img1 = tmp_path / "img1.png"
    img2 = tmp_path / "img2.png"
    img1.write_bytes(b"data_1")
    img2.write_bytes(b"data_2")
    task = Task(id="img_task_multi", prompt="镜头02 多图展示", status="completed", task_type="image")
    db.add_task(task, database)
    with db.get_db_connection(database) as conn:
        conn.execute("UPDATE tasks SET output_image_paths=? WHERE id=?", (json.dumps([str(img1), str(img2)]), task.id))
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    try:
        res = client.get(f"/api/tasks/{task.id}/download")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == 2
            assert any("_img01.png" in n for n in names)
            assert any("_img02.png" in n for n in names)
    finally:
        client.close()


def test_batch_download_zip_includes_all_images_for_multi_image_task(tmp_path, monkeypatch):
    database = tmp_path / "tasks.db"
    db.init_db(database)
    monkeypatch.setattr(web, "DB_PATH", database)
    img1 = tmp_path / "batch_img1.png"
    img2 = tmp_path / "batch_img2.png"
    img1.write_bytes(b"batch_data_1")
    img2.write_bytes(b"batch_data_2")
    task = Task(id="img_task_batch", prompt="镜头03 批量多图", status="completed", task_type="image")
    db.add_task(task, database)
    with db.get_db_connection(database) as conn:
        conn.execute("UPDATE tasks SET output_image_paths=? WHERE id=?", (json.dumps([str(img1), str(img2)]), task.id))
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    try:
        res = client.post("/api/tasks/batch-download-zip", json={"task_ids": [task.id]})
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(res.content)) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert len(names) == 2
            assert any("_img01.png" in n for n in names)
            assert any("_img02.png" in n for n in names)
    finally:
        client.close()
