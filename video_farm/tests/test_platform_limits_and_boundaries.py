import pytest
import tempfile
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient

from video_farm.web import app, DB_PATH
from video_farm.models import Task
from video_farm.video_contract import validate_video_request, VideoRequestError


@pytest.fixture
def test_assets(tmp_path):
    normal_png = tmp_path / "normal.png"
    Image.new("RGB", (256, 256), "blue").save(normal_png, format="PNG")

    normal_jpg = tmp_path / "normal.jpg"
    Image.new("RGB", (256, 256), "green").save(normal_jpg, format="JPEG")

    normal_webp = tmp_path / "normal.webp"
    Image.new("RGB", (256, 256), "red").save(normal_webp, format="WEBP")

    bad_bmp = tmp_path / "bad.bmp"
    Image.new("RGB", (100, 100), "yellow").save(bad_bmp, format="BMP")

    bad_gif = tmp_path / "bad.gif"
    Image.new("RGB", (100, 100), "purple").save(bad_gif, format="GIF")

    extreme_aspect = tmp_path / "extreme_ratio.png"
    Image.new("RGB", (1000, 20), "white").save(extreme_aspect, format="PNG")

    empty_file = tmp_path / "empty.png"
    empty_file.write_bytes(b"")

    oversized_file = tmp_path / "oversized.png"
    with open(oversized_file, "wb") as f:
        f.seek(33 * 1024 * 1024 - 1)
        f.write(b"\0")

    return {
        "normal_png": normal_png,
        "normal_jpg": normal_jpg,
        "normal_webp": normal_webp,
        "bad_bmp": bad_bmp,
        "bad_gif": bad_gif,
        "extreme_aspect": extreme_aspect,
        "empty_file": empty_file,
        "oversized_file": oversized_file,
        "tmp_path": tmp_path,
    }


def test_flow_durations_supported_for_veo(test_assets):
    for model in ("veo-lite", "veo-fast", "veo-quality"):
        for sec in (4, 6, 8):
            task = Task(id=f"t_flow_{model}_{sec}", prompt="cat", engine="flow",
                        model=model, duration_sec=sec, aspect_ratio="16:9",
                        start_image_path=str(test_assets["normal_png"]))
            validate_video_request(task)


def test_flow_10s_rejected_for_veo_quality_and_lite():
    for model in ("veo-lite", "veo-fast", "veo-quality"):
        task = Task(id="t_flow_10s_bad", prompt="cat", engine="flow",
                    model=model, duration_sec=10, aspect_ratio="16:9")
        with pytest.raises(VideoRequestError, match="10秒时长仅支持 Omni"):
            validate_video_request(task)


def test_flow_10s_accepted_for_omni(test_assets):
    for model in ("omni-flash", "omni", "Omni"):
        task = Task(id="t_flow_10s_omni", prompt="cat", engine="flow",
                    model=model, duration_sec=10, aspect_ratio="16:9",
                    start_image_path=str(test_assets["normal_png"]))
        validate_video_request(task)


def test_flow_unsupported_durations_rejected():
    for bad_sec in (3, 5, 7, 9, 12, 30):
        task = Task(id="t_flow_bad_sec", prompt="cat", engine="flow",
                    model="veo-lite", duration_sec=bad_sec, aspect_ratio="16:9")
        with pytest.raises(VideoRequestError, match="Flow 视频时长仅支持 4、6、8、10 秒"):
            validate_video_request(task)


def test_vids_durations_valid_and_boundaries(test_assets):
    for sec in (3, 5, 8, 10):
        task = Task(id=f"t_vids_{sec}", prompt="cat", engine="vids",
                    model="Omni", duration_sec=sec, aspect_ratio="16:9",
                    start_image_path=str(test_assets["normal_png"]))
        validate_video_request(task)

    t_under = Task(id="t_vids_2s", prompt="cat", engine="vids",
                   model="Omni", duration_sec=2, aspect_ratio="16:9")
    with pytest.raises(VideoRequestError, match="Google Vids 时长必须为 3 到 10 秒"):
        validate_video_request(t_under)

    t_over = Task(id="t_vids_15s", prompt="cat", engine="vids",
                  model="Omni", duration_sec=15, aspect_ratio="16:9")
    with pytest.raises(VideoRequestError, match="Google Vids 时长必须为 3 到 10 秒"):
        validate_video_request(t_over)


def test_image_formats_supported(test_assets):
    for fmt_key in ("normal_png", "normal_jpg", "normal_webp"):
        task = Task(id="t_fmt_ok", prompt="cat", engine="flow",
                    model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                    start_image_path=str(test_assets[fmt_key]))
        validate_video_request(task)


def test_unsupported_image_formats_rejected(test_assets):
    for bad_key in ("bad_bmp", "bad_gif"):
        task = Task(id="t_fmt_bad", prompt="cat", engine="flow",
                    model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                    start_image_path=str(test_assets[bad_key]))
        with pytest.raises(VideoRequestError, match="格式不支持"):
            validate_video_request(task)


def test_empty_image_rejected(test_assets):
    task = Task(id="t_empty_img", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=str(test_assets["empty_file"]))
    with pytest.raises(VideoRequestError, match="文件内容为空"):
        validate_video_request(task)


def test_oversized_image_rejected(test_assets):
    task = Task(id="t_oversized_img", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=str(test_assets["oversized_file"]))
    with pytest.raises(VideoRequestError, match="体积超过限制"):
        validate_video_request(task)


def test_extreme_aspect_ratio_rejected(test_assets):
    task = Task(id="t_ratio_bad", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=str(test_assets["extreme_aspect"]))
    with pytest.raises(VideoRequestError, match="长宽比异常"):
        validate_video_request(task)


def test_flow_ingredients_omni_cap_7(test_assets):
    tmp = test_assets["tmp_path"]
    refs = []
    for i in range(7):
        p = tmp / f"ref_omni_{i}.png"
        Image.new("RGB", (64, 64), "cyan").save(p)
        refs.append(str(p))

    task = Task(id="t_omni_7refs", prompt="cat", engine="flow",
                model="omni-flash", duration_sec=6, aspect_ratio="16:9",
                start_image_path=";".join(refs))
    validate_video_request(task)

    p_extra = tmp / "ref_omni_8.png"
    Image.new("RGB", (64, 64), "cyan").save(p_extra)
    refs.append(str(p_extra))

    task_over = Task(id="t_omni_8refs", prompt="cat", engine="flow",
                     model="omni-flash", duration_sec=6, aspect_ratio="16:9",
                     start_image_path=";".join(refs))
    with pytest.raises(VideoRequestError, match="Flow Omni 模型最多支持 7 张参考图"):
        validate_video_request(task_over)


def test_flow_ingredients_veo_lite_cap_3(test_assets):
    tmp = test_assets["tmp_path"]
    refs = []
    for i in range(3):
        p = tmp / f"ref_lite_{i}.png"
        Image.new("RGB", (64, 64), "magenta").save(p)
        refs.append(str(p))

    task = Task(id="t_lite_3refs", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=";".join(refs))
    validate_video_request(task)

    p_extra = tmp / "ref_lite_4.png"
    Image.new("RGB", (64, 64), "magenta").save(p_extra)
    refs.append(str(p_extra))

    task_over = Task(id="t_lite_4refs", prompt="cat", engine="flow",
                     model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                     start_image_path=";".join(refs))
    with pytest.raises(VideoRequestError, match="最多支持 3 张参考图"):
        validate_video_request(task_over)


def test_flow_ingredients_rejected_for_veo_quality(test_assets):
    tmp = test_assets["tmp_path"]
    p1 = tmp / "ref_q1.png"
    p2 = tmp / "ref_q2.png"
    Image.new("RGB", (64, 64), "red").save(p1)
    Image.new("RGB", (64, 64), "blue").save(p2)

    task = Task(id="t_quality_r2v", prompt="cat", engine="flow",
                model="veo-quality", duration_sec=6, aspect_ratio="16:9",
                start_image_path=f"{p1};{p2}")
    with pytest.raises(VideoRequestError, match="Veo Quality 模型不支持参考图"):
        validate_video_request(task)


def test_frames_start_only_accepted(test_assets):
    task = Task(id="t_frames_start_only", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=str(test_assets["normal_png"]))
    validate_video_request(task)


def test_frames_start_and_end_accepted(test_assets):
    task = Task(id="t_frames_pair", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path=str(test_assets["normal_png"]),
                end_image_path=str(test_assets["normal_jpg"]))
    validate_video_request(task)


def test_frames_end_without_start_rejected(test_assets):
    task = Task(id="t_frames_end_only", prompt="cat", engine="flow",
                model="veo-lite", duration_sec=6, aspect_ratio="16:9",
                start_image_path="",
                end_image_path=str(test_assets["normal_jpg"]))
    with pytest.raises(VideoRequestError, match="尾帧必须与首帧一起提供"):
        validate_video_request(task)


def test_canvas_api_handles_duration_auto_healing(test_assets):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    with open(test_assets["normal_png"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-quality",
            "prompt": "cat running",
            "seconds": "10",
            "mode": "frames",
        }, files={"first_frame": ("first.png", f, "image/png")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "video"
    assert data["status"] == "queued"


def test_canvas_api_rejects_ingredients_for_veo_quality(test_assets):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    with open(test_assets["normal_png"], "rb") as f1, open(test_assets["normal_jpg"], "rb") as f2:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-quality",
            "prompt": "cat running",
            "seconds": "6",
            "mode": "reference",
        }, files=[
            ("images", ("ref1.png", f1, "image/png")),
            ("images", ("ref2.jpg", f2, "image/jpeg"))
        ])
    assert resp.status_code == 422
    assert "Veo Quality 模型不支持参考图" in resp.json()["detail"]


def test_canvas_api_rejects_excessive_ingredients_for_veo_lite(test_assets):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    files = []
    open_files = []
    for i in range(4):
        f = open(test_assets["normal_png"], "rb")
        open_files.append(f)
        files.append(("images", (f"ref{i}.png", f, "image/png")))

    try:
        resp = client.post("/v1/videos", data={
            "model": "flow::veo-lite",
            "prompt": "cat running",
            "seconds": "6",
            "mode": "reference",
        }, files=files)
        assert resp.status_code == 422
        assert "最多支持 3 张参考图" in resp.json()["detail"]
    finally:
        for f in open_files:
            f.close()


def test_canvas_api_rejects_unsupported_image_format(test_assets):
    client = TestClient(app, base_url="http://127.0.0.1:8088")
    with open(test_assets["bad_bmp"], "rb") as f:
        resp = client.post("/v1/videos", data={
            "model": "flow",
            "prompt": "cat running",
            "seconds": "6",
            "mode": "frames",
        }, files={"first_frame": ("test.bmp", f, "image/bmp")})
    assert resp.status_code == 422
    assert "格式不支持" in resp.json()["detail"]
