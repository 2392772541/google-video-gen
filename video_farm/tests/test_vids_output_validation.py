"""Validate native Vids downloads using real ffprobe-shaped metadata."""
import json
from types import SimpleNamespace
import pytest
from video_farm.models import Task
from video_farm.execution_control import ExecutionControl
from video_farm.vids_worker import VidsUIError, VidsWorker


def output_probe(monkeypatch, stream_duration, format_duration):
    monkeypatch.setattr('video_farm.vids_worker.shutil.which', lambda name: 'ffprobe')
    data = {'streams': [{'width': 1920, 'height': 1080, 'duration': stream_duration}],
            'format': {'duration': format_duration}}
    monkeypatch.setattr('video_farm.vids_worker.subprocess.run', lambda *a, **k:
        SimpleNamespace(returncode=0, stdout=json.dumps(data)))
    return Task(id='test', prompt='test', engine='vids', model='Omni (1080p)',
                aspect_ratio='16:9', duration_sec=3)


@pytest.mark.parametrize('stream_duration', ['N/A', 'nan', 'inf', '-inf', 0, -1, None])
def test_valid_format_duration_is_used_when_stream_duration_is_unknown(monkeypatch, stream_duration):
    task = output_probe(monkeypatch, stream_duration, '3.008')
    logs = []
    VidsWorker()._validate_output('result.mp4', task, ExecutionControl(timeout_sec=20), logs)
    assert any('3.008s' in line for line in logs)


@pytest.mark.parametrize('stream_duration,format_duration', [
    ('N/A', 'N/A'), ('nan', 'inf'), (None, None), (0, 0), (-1, -1)])
def test_unknown_or_nonfinite_duration_fails_closed(monkeypatch, stream_duration, format_duration):
    task = output_probe(monkeypatch, stream_duration, format_duration)
    logs = []
    with pytest.raises(VidsUIError) as caught:
        VidsWorker()._validate_output('result.mp4', task, ExecutionControl(timeout_sec=20), logs)
    assert caught.value.code == 'VIDEO_OUTPUT_INVALID'
    assert not logs


def test_valid_stream_duration_remains_authoritative(monkeypatch):
    task = output_probe(monkeypatch, '8.0', '3.008')
    with pytest.raises(VidsUIError) as caught:
        VidsWorker()._validate_output('result.mp4', task, ExecutionControl(timeout_sec=20), [])
    assert caught.value.code == 'VIDEO_OUTPUT_INVALID'
