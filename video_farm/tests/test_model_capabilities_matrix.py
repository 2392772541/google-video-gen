import pytest
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from video_farm.web import app, DB_PATH
from video_farm import db
from video_farm.models import Task
from video_farm.video_contract import validate_video_request, VideoRequestError
from video_farm.model_capabilities import get_model_spec, get_canvas_models_payload

@pytest.fixture
def test_images(tmp_path):
    p1 = tmp_path / "img1.png"
    p2 = tmp_path / "img2.png"
    p3 = tmp_path / "img3.png"
    p4 = tmp_path / "img4.png"
    for p in (p1, p2, p3, p4):
        Image.new("RGB", (128, 128), "blue").save(p)
    return {"p1": p1, "p2": p2, "p3": p3, "p4": p4, "tmp": tmp_path}

def test_model_capabilities_registry_coverage():
    models = get_canvas_models_payload()
    model_ids = [m["id"] for m in models]
    assert "omni-flash" in model_ids
    assert "veo-lite" in model_ids
    assert "veo-fast" in model_ids
    assert "veo-quality" in model_ids
    assert "vids" in model_ids
    assert "gemini" in model_ids

    # Group A: Flow Omni Flash
    spec_omni = get_model_spec("omni-flash")
    assert spec_omni["duration_control_mode"] == "selectable"
    assert spec_omni["supportedDurations"] == [4, 6, 8, 10]
    assert spec_omni["max_reference_images"] == 3
    assert spec_omni["supported_output_counts"] == [1, 2, 3, 4]

    # Group B: Veo Lite
    spec_lite = get_model_spec("veo-lite")
    assert spec_lite["duration_control_mode"] == "selectable"
    assert spec_lite["supportedDurations"] == [4, 6, 8]
    assert spec_lite["supportsExtend"] is True
    assert spec_lite["supportsIngredients"] is True
    assert spec_lite["max_reference_images"] == 3

    # Group C: Veo Fast
    spec_fast = get_model_spec("veo-fast")
    assert spec_fast["duration_control_mode"] == "selectable"
    assert spec_fast["supportedDurations"] == [4, 6, 8]
    assert spec_fast["supportsExtend"] is False
    assert spec_fast["supportsIngredients"] is True

    # Group D: Veo Quality
    spec_qual = get_model_spec("veo-quality")
    assert spec_qual["duration_control_mode"] == "selectable"
    assert spec_qual["supportedDurations"] == [4, 6, 8]
    assert spec_qual["supportsIngredients"] is False
    assert spec_qual["supportsFrames"] is True

    # Group E: Vids
    spec_vids = get_model_spec("vids")
    assert spec_vids["duration_control_mode"] == "selectable"
    assert spec_vids["supportedDurations"] == [3, 4, 5, 6, 7, 8, 9, 10]
    assert spec_vids["supportsFrames"] is False
    assert spec_vids["supportsIngredients"] is True
    assert spec_vids["max_reference_images"] == 3

    # Group F: Gemini
    spec_gemini = get_model_spec("gemini")
    assert spec_gemini["duration_control_mode"] == "upstream_default"
    assert spec_gemini["supportsFrames"] is False
    assert spec_gemini["max_reference_images"] == 1


# --- Test Group A: Flow Omni Flash ---
def test_group_a_omni_flash_durations_and_count(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # 1. 验证 4s, 6s, 8s, 10s 及 count=1~4 均正常放行
    for sec in (4, 6, 8, 10):
        with open(test_images["p1"], "rb") as f:
            resp = client.post("/v1/videos", data={
                "model": "flow::omni-flash",
                "prompt": "flying eagle over majestic snow mountains",
                "seconds": str(sec),
                "count": "2",
                "mode": "frames"
            }, files={"first_frame": ("f.png", f, "image/png")})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        task = db.get_task(data["id"], DB_PATH)
        assert task.duration_sec == sec
        assert data["status"] == "queued"

    # 2. 验证超过 3 张参考图被拦截
    files = [("images", (f"r{i}.png", open(test_images[f"p{i+1}"], "rb"), "image/png")) for i in range(4)]
    try:
        resp = client.post("/v1/videos", data={
            "model": "flow::omni-flash",
            "prompt": "eagle",
            "seconds": "6",
            "mode": "reference"
        }, files=files)
        assert resp.status_code == 422
        assert "最多支持 3 张参考图" in resp.json()["detail"]
    finally:
        for _, ftuple in files:
            ftuple[1].close()


# --- Test Group B: Flow Veo Lite ---
def test_group_b_veo_lite_durations_and_extend(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # 1. Veo Lite 8s extend 允许放行
    with open(test_images["p1"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-lite",
            "prompt": "eagle flies forward",
            "seconds": "8",
            "mode": "extend"
        }, files={"first_frame": ("f.png", f, "image/png")})
    assert resp.status_code == 200
    assert resp.json()["model"] == "veo-lite"

    # 2. 严禁 10s 静默替模：Veo Lite 10s 必须 422 拦截
    with open(test_images["p1"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-lite",
            "prompt": "eagle flies forward",
            "seconds": "10",
            "mode": "frames"
        }, files={"first_frame": ("f.png", f, "image/png")})
    assert resp.status_code == 422
    assert "Veo 系列模型 (veo-lite) 仅支持 4s、6s、8s 时长" in resp.json()["detail"]


# --- Test Group C: Flow Veo Fast ---
def test_group_c_veo_fast_restrictions(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # 1. Veo Fast 不支持 extend 延展，必须拦截
    with open(test_images["p1"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-fast",
            "prompt": "eagle diving",
            "seconds": "8",
            "mode": "extend"
        }, files={"first_frame": ("f.png", f, "image/png")})
    assert resp.status_code == 422
    assert "视频延展 (Extend) 功能仅开放给 Google Flow 的 Veo 3.1 Lite" in resp.json()["detail"]


# --- Test Group D: Flow Veo Quality ---
def test_group_d_veo_quality_ingredients_rejected(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # Veo Quality 不支持普通参考图 (Ingredients)
    with open(test_images["p1"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-quality",
            "prompt": "hyper-detailed close-up",
            "seconds": "6",
            "mode": "reference"
        }, files=[("images", ("r1.png", f, "image/png"))])
    assert resp.status_code == 422
    assert "Veo Quality 模型不支持参考图" in resp.json()["detail"]


# --- Test Group E: Google Vids ---
def test_group_e_vids_capabilities(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # 1. Vids 支持 3~10s 与 1~3 张参考图
    files = [("images", (f"r{i}.png", open(test_images[f"p{i+1}"], "rb"), "image/png")) for i in range(3)]
    try:
        resp = client.post("/v1/videos", data={
            "model": "vids",
            "prompt": "product showcase video",
            "seconds": "5",
            "mode": "reference",
            "vquality": "1080"
        }, files=files)
        assert resp.status_code == 200
        assert resp.json()["model"] == "Omni (1080p)"
        task = db.get_task(resp.json()["id"], DB_PATH)
        assert task.duration_sec == 5
    finally:
        for _, ftuple in files:
            ftuple[1].close()

    # 2. Vids 暂不支持双关键帧插值首尾帧，必须 422 提示
    with open(test_images["p1"], "rb") as f1, open(test_images["p2"], "rb") as f2:
        resp = client.post("/v1/videos", data={
            "model": "vids",
            "prompt": "product showcase video",
            "seconds": "8",
            "mode": "frames"
        }, files={"first_frame": ("f1.png", f1, "image/png"), "last_frame": ("f2.png", f2, "image/png")})
    assert resp.status_code == 422
    assert "Google Vids 暂不支持双关键帧首尾插值模式" in resp.json()["detail"]


# --- Test Group F: Google Gemini ---
def test_group_f_gemini_strict_upload_and_limit(test_images):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    # 1. Gemini 单图首帧驱动放行
    with open(test_images["p1"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "gemini",
            "prompt": "camera pan across vibrant botanical garden",
            "seconds": "6",
            "mode": "reference"
        }, files=[("images", ("f1.png", f, "image/png"))])
    assert resp.status_code == 200
    assert resp.json()["model"] == "gemini"

    # 2. Gemini 多图参考被拦截
    files = [("images", (f"r{i}.png", open(test_images[f"p{i+1}"], "rb"), "image/png")) for i in range(2)]
    try:
        resp = client.post("/v1/videos", data={
            "model": "gemini",
            "prompt": "camera pan",
            "seconds": "6",
            "mode": "reference"
        }, files=files)
        assert resp.status_code == 422
        assert "Google Gemini 网页通道仅支持单张参考图驱动" in resp.json()["detail"]
    finally:
        for _, ftuple in files:
            ftuple[1].close()

    # 3. Gemini 尾帧绑定被拦截
    with open(test_images["p1"], "rb") as f1, open(test_images["p2"], "rb") as f2:
        resp = client.post("/v1/videos", data={
            "model": "gemini",
            "prompt": "camera pan",
            "seconds": "6",
            "mode": "frames"
        }, files={"first_frame": ("f1.png", f1, "image/png"), "last_frame": ("f2.png", f2, "image/png")})
    assert resp.status_code == 422
    assert "Google Gemini 网页通道不支持尾帧绑定" in resp.json()["detail"]
