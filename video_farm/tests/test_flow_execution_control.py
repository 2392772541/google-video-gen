"""Flow attempts must own their outputs and never transparently spend twice."""
import json
import threading
import subprocess
from pathlib import Path
from unittest.mock import patch, Mock

import pytest
from video_farm.worker import VideoWorker
from video_farm.models import Task, Profile
from video_farm.scheduler import classify_failure
from video_farm import db


def worker(tmp_path):
    instance = VideoWorker(gflow_dir=tmp_path, output_dir=tmp_path / "outputs", timeout_sec=5)
    instance._ensure_profile_marker = Mock()
    return instance


def task():
    return Task(id="flow-owned-output", prompt="test", project_id="project", aspect_ratio="16:9")


class Process:
    pid = 123
    returncode = 0
    def __init__(self, stdout="", stderr=""):
        self.stdout, self.stderr = stdout, stderr
    def emit(self, kwargs):
        for name in ("stdout", "stderr"):
            stream = kwargs[name]
            stream.write(getattr(self, name).encode("utf-8"))
            stream.flush()
        return self
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        return self.returncode
    def cleanup(self):
        return True
    def is_alive(self):
        return self.returncode is None


def success_record(path):
    return json.dumps({"status": "ok", "succeeded": True, "local_path": str(path)})


def test_other_task_output_cannot_complete_this_attempt(tmp_path):
    w = worker(tmp_path)
    def launch(*args, **kwargs):
        unrelated = w.output_dir / "other-task.mp4"
        unrelated.write_bytes(b"x" * 60000)
        return Process(success_record(unrelated)).emit(kwargs)
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=launch):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["success"] is False
    assert result["error_code"] == "VIDEO_OUTPUT_INVALID"


def test_no_output_scanning_fallback(tmp_path):
    w = worker(tmp_path)
    def launch(*args, **kwargs):
        (w.output_dir / "other.mp4").write_bytes(b"x" * 60000)
        return Process().emit(kwargs)
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=launch):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["success"] is False
    assert result["error_code"] == "FLOW_RESULT_UNCONFIRMED"


def test_owned_file_requires_success_receipt_and_media_validation(tmp_path):
    w = worker(tmp_path)
    def launch(command, **kwargs):
        out = Path(command[command.index("--out-dir") + 1])
        assert out != w.output_dir and out.is_relative_to(w.output_dir / task().id)
        video = out / "result.mp4"
        video.write_bytes(b"x" * 60000)
        return Process(success_record(video)).emit(kwargs)
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=launch), patch.object(w, "_validate_output", create=True, side_effect=ValueError("invalid MP4")):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["success"] is False
    assert result["error_code"] == "VIDEO_OUTPUT_INVALID"


@pytest.mark.parametrize("stderr", ["BrowserSessionClosedError", "TransportTimeoutError", "unknown after submit"])
def test_uncertain_cli_failure_must_not_retry(tmp_path, stderr):
    w = worker(tmp_path)
    p = Process("", stderr)
    p.returncode = 15 if "Browser" in stderr else 9 if "Timeout" in stderr else 1
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=lambda command, **kwargs: p.emit(kwargs)):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["error_code"] == "FLOW_RESULT_UNCONFIRMED"
    assert classify_failure(result["error_code"], result["error_message"], result["logs"])[3] is False


def test_prelaunch_stop_never_starts_cli(tmp_path):
    w = worker(tmp_path)
    event = threading.Event()
    w.prepare_task(task().id, event)
    assert w.cancel_task(task().id)
    with patch("video_farm.worker.VideoWorker._launch_cli") as launch:
        result = w.execute_task(task(), Profile(id="p", name="p"))
    launch.assert_not_called()
    assert event.is_set() and result["error_code"] == "USER_CANCELLED"


def test_stop_during_launch_terminates_owned_process(tmp_path):
    w = worker(tmp_path)
    event = threading.Event()
    w.prepare_task(task().id, event)
    p = Process()
    p.returncode = None  # Still alive when cancellation arrives during Popen.
    def launch(*args, **kwargs):
        event.set()
        return p.emit(kwargs)
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=launch), patch.object(w, "_terminate", return_value=True) as terminate:
        result = w.execute_task(task(), Profile(id="p", name="p"))
    terminate.assert_called_once_with(p)
    assert result["error_code"] == "USER_CANCELLED"


def test_missing_project_never_submits(tmp_path, monkeypatch):
    w = worker(tmp_path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    t = task()
    t.project_id = ""
    with patch("video_farm.worker.VideoWorker._launch_cli") as launch, patch("video_farm.onboard.ensure_profile_onboarded", return_value=None):
        result = w.execute_task(t, Profile(id="p", name="p"))
    launch.assert_not_called()
    assert result["error_code"] == "PROJECT_INIT_REQUIRED"


def test_manual_retry_blocks_unconfirmed_flow_result():
    t = task()
    db.add_task(t)
    db.update_task_status(t.id, "failed", error_code="FLOW_RESULT_UNCONFIRMED")
    with pytest.raises(db.TaskOperationConflict):
        db.transition_task(t.id, "retry")


def test_8_second_request_is_explicit_and_na_duration_uses_format(tmp_path):
    w = worker(tmp_path)
    def launch(command, **kwargs):
        assert command[command.index("--duration") + 1] == "8"
        out = Path(command[command.index("--out-dir") + 1]) / "result.mp4"
        out.write_bytes(b"x" * 60000)
        return Process(success_record(out)).emit(kwargs)
    probe = Mock(returncode=0, stdout=json.dumps({
        "streams": [{"width": 1920, "height": 1080, "duration": "N/A"}],
        "format": {"duration": "8.008"}}))
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=launch), \
         patch("video_farm.worker.shutil.which", return_value="ffprobe"), \
         patch("video_farm.worker.subprocess.run", return_value=probe):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["success"], result
    target = w.output_dir / (task().id + ".mp4")
    assert result["output_video_path"] == str(target)
    assert target.is_file() and result["cleanup_confirmed"] is True
    assert list((w.output_dir / task().id).glob("attempt_*/result.mp4"))


def test_failed_process_cleanup_retains_execution_owner(tmp_path):
    w = worker(tmp_path)
    event = threading.Event()
    w.prepare_task(task().id, event)
    proc = Process()
    proc.returncode = None
    def wait(timeout=None):
        event.set()
        raise subprocess.TimeoutExpired("flow", timeout)
    proc.wait = wait
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=lambda command, **kwargs: proc.emit(kwargs)), \
         patch.object(w, "_terminate", return_value=False):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result.get("cleanup_confirmed") is False
    assert w.has_live_execution(task().id) is True
    proc.returncode = -9
    proc.is_alive = lambda: True  # Root exited, descendant still owns the profile.
    assert w.has_live_execution(task().id) is True
    proc.is_alive = lambda: False
    assert w.has_live_execution(task().id) is False


def test_cli_config_error_not_treated_as_unconfirmed_result(tmp_path):
    w = worker(tmp_path)
    stderr_content = "Usage: python -m gflow_cli video i2v\nError: the default model veo_3_1_lite: model 'veo_3_1_lite' caps at 8s; duration 10 is only available for omni_flash"
    p = Process("", stderr_content)
    p.returncode = 2
    with patch("video_farm.worker.VideoWorker._launch_cli", side_effect=lambda command, **kwargs: p.emit(kwargs)):
        result = w.execute_task(task(), Profile(id="p", name="p"))
    assert result["error_code"] == "CONFIG_ERROR"
    assert "caps at 8s" in result["error_message"]
    assert result["submission_possible"] is False
