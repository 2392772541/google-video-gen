import pytest
import tempfile
import json
import subprocess
from pathlib import Path
from video_farm.timeline_assembler import (
    probe_video,
    assemble_timeline,
    calculate_sha256,
    TimelineAssemblyError,
    ShotSpec
)

TOMATO_DIR = Path(__file__).resolve().parent.parent.parent / "QA_EVIDENCE" / "tomato_story"
SHOT1 = TOMATO_DIR / "shot1_sprout_video.mp4"
SHOT2 = TOMATO_DIR / "shot2_growing_video.mp4"


def test_probe_valid_video(monkeypatch):
    dummy_json = json.dumps({
        "format": {"duration": "8.0", "size": "1000", "bit_rate": "1000"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "r_frame_rate": "24/1"},
            {"codec_type": "audio", "codec_name": "aac"}
        ]
    })
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=dummy_json, stderr=""))
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"dummy")
        p = Path(f.name)
    try:
        info = probe_video(p)
    finally:
        p.unlink()
    assert info["width"] == 1280
    assert info["height"] == 720
    assert info["fps"] == 24.0
    assert info["has_video"] is True
    assert info["has_audio"] is True
    assert info["duration"] == 8.0


def test_probe_non_existent():
    with pytest.raises(TimelineAssemblyError) as exc:
        probe_video(Path("non_existent_file_xyz.mp4"))
    assert exc.value.code == 404


def test_probe_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        p = Path(f.name)
    try:
        with pytest.raises(TimelineAssemblyError) as exc:
            probe_video(p)
        assert exc.value.code == 400
    finally:
        if p.exists():
            p.unlink()


def test_assemble_less_than_two():
    with pytest.raises(TimelineAssemblyError) as exc:
        assemble_timeline([SHOT1], Path("out.mp4"))
    assert exc.value.code == 400


def test_assemble_two_clips(monkeypatch):
    dummy_probe_json = json.dumps({
        "format": {"duration": "6.0", "size": "1000", "bit_rate": "1000"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "r_frame_rate": "24/1"},
            {"codec_type": "audio", "codec_name": "aac"}
        ]
    })
    def mock_run(cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            return subprocess.CompletedProcess(cmd, 0, stdout=dummy_probe_json, stderr="")
        elif cmd[0] == "ffmpeg":
            out_p = Path(cmd[-1])
            out_p.write_bytes(b"dummy_assembled_mp4_bytes")
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise ValueError(f"Unexpected command: {cmd}")
    monkeypatch.setattr(subprocess, "run", mock_run)

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        p1 = td / "clip1.mp4"
        p2 = td / "clip2.mp4"
        p1.write_bytes(b"data1")
        p2.write_bytes(b"data2")
        out_file = td / "test_assembled.mp4"
        res = assemble_timeline([p1, p2], out_file, max_threads=2)
        assert res["success"] is True
        assert out_file.is_file()
        assert out_file.stat().st_size > 0
        assert res["total_duration"] == 6.0
        assert len(res["timeline"]) == 2
        assert res["timeline"][0]["shot_index"] == 1
        assert res["timeline"][1]["shot_index"] == 2
        assert res["timeline"][0]["end_time"] == res["timeline"][1]["start_time"]


def test_shotspec_trim_validation(monkeypatch):
    dummy_probe_json = json.dumps({
        "format": {"duration": "10.0", "size": "1000", "bit_rate": "1000"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "r_frame_rate": "24/1"},
            {"codec_type": "audio", "codec_name": "aac"}
        ]
    })
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=dummy_probe_json, stderr=""))

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        p1 = td / "c1.mp4"
        p2 = td / "c2.mp4"
        p1.write_bytes(b"1")
        p2.write_bytes(b"2")
        out = td / "out.mp4"

        # 起始时间大于结束时间
        with pytest.raises(TimelineAssemblyError) as exc1:
            assemble_timeline([ShotSpec(p1, trim_start_s=5.0, trim_end_s=3.0), ShotSpec(p2)], out)
        assert "必须大于起始时间" in exc1.value.message

        # 结束时间超过原视频时长
        with pytest.raises(TimelineAssemblyError) as exc2:
            assemble_timeline([ShotSpec(p1, trim_start_s=0.0, trim_end_s=15.0), ShotSpec(p2)], out)
        assert "超过了源视频物理时长" in exc2.value.message

        # 裁剪后有效时长过短 (<0.1s)
        with pytest.raises(TimelineAssemblyError) as exc3:
            assemble_timeline([ShotSpec(p1, trim_start_s=1.0, trim_end_s=1.05), ShotSpec(p2)], out)
        assert "有效时长必须大于 0.1s" in exc3.value.message
