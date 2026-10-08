"""Independent Gemini video probe; no browser, provider or real ffprobe."""
import json
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from video_farm.execution_control import ExecutionControl, ExecutionStopped
from video_farm.gemini_worker import GeminiWebWorker, GeminiVideoSettingsError
from video_farm.models import Task


def request(aspect="16:9"):
    return Task(id="gemini-probe", engine="gemini", prompt="test", duration_sec=8,
                aspect_ratio=aspect, model="veo")


def install_probe(monkeypatch, width=1280, height=720, stream_duration="8.008", format_duration="8.0", returncode=0):
    probe = Mock(return_value=SimpleNamespace(returncode=returncode, stdout=json.dumps({
        "streams": [{"width": width, "height": height, "duration": stream_duration}],
        "format": {"duration": format_duration}})))
    monkeypatch.setattr("video_farm.gemini_worker.shutil.which", lambda _: "ffprobe")
    monkeypatch.setattr("video_farm.gemini_worker.subprocess.run", probe)
    return probe


@pytest.mark.parametrize("dimensions,aspect", [((1280,720),"16:9"), ((720,1280),"9:16"), ((1024,576),"16:9")])
def test_gemini_validates_ratio_without_vids_resolution_assumptions(tmp_path, monkeypatch, dimensions, aspect):
    probe = install_probe(monkeypatch, *dimensions)
    logs = []
    GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(aspect), ExecutionControl(timeout_sec=20), logs)
    assert "真实成片规格通过" in logs[0]
    assert 0 < probe.call_args.kwargs["timeout"] <= 15


@pytest.mark.parametrize("duration", ["N/A", "nan", "inf", "-inf", 0, -1, None])
def test_gemini_uses_finite_format_duration_when_stream_unknown(tmp_path, monkeypatch, duration):
    install_probe(monkeypatch, stream_duration=duration, format_duration="8.008")
    logs = []
    GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(timeout_sec=20), logs)
    assert "8.008s" in logs[0]


@pytest.mark.parametrize("duration,format_duration", [("nan","inf"), ("N/A","N/A"), (None,None), (0,0), (-1,-1)])
def test_gemini_nonfinite_or_missing_duration_fails_closed(tmp_path, monkeypatch, duration, format_duration):
    install_probe(monkeypatch, stream_duration=duration, format_duration=format_duration)
    with pytest.raises(GeminiVideoSettingsError) as caught:
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(timeout_sec=20), [])
    assert caught.value.code == "VIDEO_OUTPUT_INVALID"


@pytest.mark.parametrize("dimensions", [(0,720), (1280,0), (float("inf"),720), (1280,float("nan")), ("1280",720)])
def test_gemini_dimensions_must_be_positive_and_finite(tmp_path, monkeypatch, dimensions):
    install_probe(monkeypatch, *dimensions)
    with pytest.raises(GeminiVideoSettingsError) as caught:
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(timeout_sec=20), [])
    assert caught.value.code == "VIDEO_OUTPUT_INVALID"


@pytest.mark.parametrize("options,expected_code", [({"width": 720, "height": 1280}, "VIDEO_ASPECT_MISMATCH"),
    ({"stream_duration": "10", "format_duration": "8"}, "VIDEO_DURATION_MISMATCH"),
    ({"returncode": 1}, "VIDEO_OUTPUT_INVALID")])
def test_gemini_spec_mismatch_and_failed_probe_are_not_success(tmp_path, monkeypatch, options, expected_code):
    install_probe(monkeypatch, **options)
    with pytest.raises(GeminiVideoSettingsError) as caught:
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(timeout_sec=20), [])
    assert caught.value.code == expected_code


def test_gemini_probe_timeout_is_bounded_by_remaining_budget(tmp_path, monkeypatch):
    probe = install_probe(monkeypatch)
    probe.side_effect = subprocess.TimeoutExpired("ffprobe", 0.1)
    control = ExecutionControl(timeout_sec=0.1)
    with pytest.raises(subprocess.TimeoutExpired):
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), control, [])
    assert 0 < probe.call_args.kwargs["timeout"] <= 0.1 + 1e-6


def test_gemini_stop_before_probe_launches_nothing(tmp_path, monkeypatch):
    probe = install_probe(monkeypatch)
    event = threading.Event()
    event.set()
    with pytest.raises(ExecutionStopped) as caught:
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(event), [])
    assert caught.value.code == "USER_CANCELLED"
    probe.assert_not_called()


def test_missing_ffprobe_cannot_mark_gemini_success(tmp_path, monkeypatch):
    monkeypatch.setattr("video_farm.gemini_worker.shutil.which", lambda _: None)
    with pytest.raises(GeminiVideoSettingsError) as caught:
        GeminiWebWorker(output_dir=tmp_path)._validate_output("result.mp4", request(), ExecutionControl(), [])
    assert caught.value.code == "VIDEO_OUTPUT_INVALID"
