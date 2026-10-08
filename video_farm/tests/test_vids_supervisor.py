"""Isolated Vids supervisor contracts. No browser, provider or real process."""
import json
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Profile, Task
from video_farm.vids_worker import VidsWorker
from video_farm.gemini_worker import GeminiWebWorker


@pytest.fixture(params=["vids", "gemini"])
def provider(request):
    return request.param


@pytest.fixture
def task(provider):
    return Task(id="task_supervisor", prompt="contract check", engine=provider,
                model="Omni (1080p)" if provider == "vids" else "auto",
                aspect_ratio="16:9", duration_sec=3 if provider == "vids" else 8)


@pytest.fixture
def profile(tmp_path):
    return Profile(id="profile_supervisor", name="isolated", profile_path=str(tmp_path / "profile"))


@pytest.fixture
def worker(tmp_path, monkeypatch, provider):
    cls = VidsWorker if provider == "vids" else GeminiWebWorker
    w = cls(output_dir=tmp_path / "outputs", timeout_sec=5)
    monkeypatch.setattr(w, "_validate_output", Mock())
    return w


class Child:
    pid = 12345

    def __init__(self, *, exit_code=0, cleanup=True, blocked=False, cancel_event=None):
        self.exit_code, self.cleanup_result = exit_code, cleanup
        self.blocked, self.cancel_event = blocked, cancel_event
        self.alive, self.cleanups = True, 0

    def wait(self, timeout=None):
        if self.cancel_event is not None:
            self.cancel_event.set()
            raise subprocess.TimeoutExpired("fixture", timeout)
        if self.blocked:
            time.sleep(min(0.01, timeout))
            raise subprocess.TimeoutExpired("fixture", timeout)
        self.alive = False
        return self.exit_code

    def is_alive(self):
        return self.alive

    def cleanup(self, timeout=3):
        self.cleanups += 1
        if isinstance(self.cleanup_result, Exception):
            raise self.cleanup_result
        if self.cleanup_result:
            self.alive = False
        return self.cleanup_result


def install_child(worker, monkeypatch, child=None, *, result="success", submitted=False):
    child = child or Child()
    paths = []

    def launch(request_path, log_file):
        paths.append(request_path.parent)
        spec = json.loads(request_path.read_text(encoding="utf8"))
        attempt = request_path.parent
        output = attempt / (spec["task"]["id"] + ".mp4")
        output.write_bytes(b"fixture MP4; metadata verified by explicit mock")
        if submitted:
            (attempt / "submission.json").write_text("{}", encoding="utf8")
        if result == "success":
            payload = {"success": True, "output_video_path": str(output), "logs": "done", "submission_possible": True}
        elif result == "failure":
            payload = {"success": False, "error_code": "AUTH_EXPIRED", "logs": "login required", "submission_possible": False}
        elif isinstance(result, dict):
            payload = result
        else:
            if result == "malformed":
                (attempt / "result.json").write_text("{bad", encoding="utf8")
            return child
        (attempt / "result.json").write_text(json.dumps(payload), encoding="utf8")
        return child

    monkeypatch.setattr(worker, "_launch_runner", launch)
    return child, paths


def test_success_is_published_atomically_for_player_and_download(worker, profile, task, monkeypatch):
    child, paths = install_child(worker, monkeypatch)
    result = worker.execute_task(task, profile)
    target = worker.output_dir / (task.id + ".mp4")
    assert result["success"] is True
    assert result["cleanup_confirmed"] is True
    assert result["output_video_path"] == str(target)
    assert target.read_bytes() == (paths[0] / target.name).read_bytes()
    assert not worker.has_live_execution(task.id)
    assert child.cleanups == 1
    monkeypatch.setattr(web, "OUTPUTS_DIR", worker.output_dir)
    db.add_task(task)
    db.update_task_status(task.id, "completed", output_video_path=result["output_video_path"])
    client = TestClient(web.app, base_url="http://127.0.0.1:8088")
    response = client.get("/api/tasks/" + task.id)
    assert response.status_code == 200
    media_url = response.json()["video_url"]
    assert media_url == "/media/outputs/" + target.name
    assert client.get(media_url).content == target.read_bytes()
    assert client.get("/api/tasks/" + task.id + "/download").content == target.read_bytes()


def test_nonzero_child_exit_cannot_publish_a_success_file(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch, Child(exit_code=9), submitted=True)
    result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert result["error_code"] == worker.unconfirmed_code
    assert result["submission_possible"] is True
    assert not (worker.output_dir / (task.id + ".mp4")).exists()


@pytest.mark.parametrize("cleanup", [False, OSError("cannot query process")])
def test_unconfirmed_cleanup_keeps_owner_and_never_publishes(worker, profile, task, monkeypatch, cleanup):
    child, paths = install_child(worker, monkeypatch, Child(cleanup=cleanup))
    result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert result["error_code"] == "PROCESS_CLEANUP_FAILED"
    assert result["cleanup_confirmed"] is False
    assert result["pid"] == child.pid
    assert task.id in worker._active_sessions
    assert not (worker.output_dir / (task.id + ".mp4")).exists()
    assert (paths[0] / (task.id + ".mp4")).exists()
    child.cleanup_result, child.alive = True, False
    assert not worker.has_live_execution(task.id)


@pytest.mark.parametrize("payload", ["missing", "malformed", {"success": "true"}, {"success": True, "output_video_path": "old.mp4"}])
def test_missing_malformed_or_foreign_result_fails_closed(worker, profile, task, monkeypatch, payload):
    install_child(worker, monkeypatch, result=payload, submitted=True)
    result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert result["submission_possible"] is True
    assert result["cleanup_confirmed"] is True
    assert not (worker.output_dir / (task.id + ".mp4")).exists()


def test_pre_submit_known_failure_retains_explicit_submission_state(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch, result="failure")
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "AUTH_EXPIRED"
    assert result["submission_possible"] is False
    assert result["cleanup_confirmed"] is True


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_blocked_child_is_stopped_and_not_automatically_retried(worker, profile, task, monkeypatch, mode):
    event = threading.Event()
    worker.prepare_task(task.id, event)
    worker.timeout_sec = 0.08 if mode == "timeout" else 5
    child = Child(blocked=True, cancel_event=event if mode == "cancel" else None)
    install_child(worker, monkeypatch, child, result="missing", submitted=True)
    started = time.monotonic()
    result = worker.execute_task(task, profile)
    assert time.monotonic() - started < 1
    assert result["success"] is False
    assert result["error_code"] == ("USER_CANCELLED" if mode == "cancel" else worker.unconfirmed_code)
    assert result["submission_possible"] is True
    assert result["cleanup_confirmed"] is True
    assert child.cleanups == 1
    assert not worker.has_live_execution(task.id)


def test_invalid_tail_frame_does_not_launch_or_change_engine(worker, profile, task, monkeypatch, tmp_path):
    from PIL import Image
    frame = tmp_path / "frame.png"
    Image.new("RGB", (4, 4)).save(frame)
    task.start_image_path = task.end_image_path = str(frame)
    launch = Mock(side_effect=AssertionError("Must reject before launch"))
    monkeypatch.setattr(worker, "_launch_runner", launch)
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "INVALID_VIDEO_REQUEST"
    assert "尾帧" in result["error_message"]
    assert result["submission_possible"] is False
    assert task.engine == worker.provider_label.lower()
    assert task.end_image_path == str(frame)
    launch.assert_not_called()


def test_cancel_before_launch_is_preserved(worker, profile, task, monkeypatch):
    event = threading.Event()
    event.set()
    worker.prepare_task(task.id, event)
    launch = Mock()
    monkeypatch.setattr(worker, "_launch_runner", launch)
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "USER_CANCELLED"
    assert result["cleanup_confirmed"] is True
    assert result["submission_possible"] is False
    launch.assert_not_called()


def test_mock_result_uses_same_finalized_outcome(worker, profile, task, monkeypatch):
    monkeypatch.setenv(worker.mock_env_var, "1")
    worker.mock_sample_video = "explicit fixture"
    monkeypatch.setattr(worker, "_execute_browser_task", lambda *a: {"success": True, "mock": True, "submission_possible": False})
    result = worker.execute_task(task, profile)
    assert result["success"] is True
    assert result["cleanup_confirmed"] is True
    assert result["pid"] is None
    assert result["submission_possible"] is False


def test_failed_validation_never_replaces_existing_output(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch)
    previous = worker.output_dir / (task.id + ".mp4")
    previous.write_bytes(b"previous validated video")
    monkeypatch.setattr(worker, "_validate_output", Mock(side_effect=ValueError("bad probe")))
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "VIDEO_OUTPUT_INVALID"
    assert result["cleanup_confirmed"] is True
    assert previous.read_bytes() == b"previous validated video"


def test_cleanup_failure_preserves_previous_output(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch, Child(cleanup=False))
    previous = worker.output_dir / (task.id + ".mp4")
    previous.write_bytes(b"previous validated video")
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "PROCESS_CLEANUP_FAILED"
    assert previous.read_bytes() == b"previous validated video"


def test_filesystem_without_hardlinks_keeps_atomic_publication(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch)
    monkeypatch.setattr("video_farm.vids_worker.os.link", Mock(side_effect=OSError("unsupported")))
    result = worker.execute_task(task, profile)
    assert result["success"] is True
    assert Path(result["output_video_path"]).is_file()
    assert not list(worker.output_dir.glob("*.publishing"))


def test_cancel_during_cleanup_does_not_publish(worker, profile, task, monkeypatch):
    event = threading.Event()
    worker.prepare_task(task.id, event)
    child, _ = install_child(worker, monkeypatch)
    cleanup = child.cleanup
    def stop_during_cleanup():
        event.set()
        return cleanup()
    child.cleanup = stop_during_cleanup
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "USER_CANCELLED"
    assert result["cleanup_confirmed"] is True
    assert result["submission_possible"] is True
    assert not (worker.output_dir / (task.id + ".mp4")).exists()


def test_bad_log_type_cannot_bypass_cleanup_status(worker, profile, task, monkeypatch):
    install_child(worker, monkeypatch, result={"success": False, "error_code": "AUTH_EXPIRED", "logs": None, "submission_possible": False})
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "AUTH_EXPIRED"
    assert result["cleanup_confirmed"] is True
    assert not worker.has_live_execution(task.id)


@pytest.mark.parametrize("mode", ["timeout", "cancel"])
def test_proven_pre_submit_stop_is_not_an_unknown_submission(worker, profile, task, monkeypatch, mode):
    event = threading.Event()
    worker.prepare_task(task.id, event)
    worker.timeout_sec = 0.08 if mode == "timeout" else 5
    child = Child(blocked=True, cancel_event=event if mode == "cancel" else None)
    install_child(worker, monkeypatch, child, result="missing", submitted=False)
    result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert result["cleanup_confirmed"] is True
    assert result["submission_possible"] is False
    assert result["error_code"] == ("USER_CANCELLED" if mode == "cancel" else "PRE_SUBMIT_TIMEOUT")
    assert "未提交" in result["error_message"]
    assert child.cleanups == 1 and not worker.has_live_execution(task.id)


@pytest.mark.parametrize("cleanup", [False, OSError("cannot query child tree")])
def test_stopped_child_without_marker_stays_unknown_if_cleanup_fails(worker, profile, task, monkeypatch, cleanup):
    event = threading.Event()
    worker.prepare_task(task.id, event)
    child = Child(cancel_event=event, cleanup=cleanup)
    install_child(worker, monkeypatch, child, result="missing", submitted=False)
    result = worker.execute_task(task, profile)
    assert result["error_code"] == "PROCESS_CLEANUP_FAILED"
    assert result["submission_possible"] is True
    assert result["cleanup_confirmed"] is False
    assert task.id in worker._active_sessions


def test_submission_marker_created_during_cleanup_is_not_lost(worker, profile, task, monkeypatch):
    event = threading.Event()
    worker.prepare_task(task.id, event)
    child, paths = install_child(worker, monkeypatch, Child(cancel_event=event), result="missing")
    original = child.cleanup
    def cleanup(*args, **kwargs):
        (paths[0] / "submission.json").write_text("{}", encoding="utf8")
        return original(*args, **kwargs)
    child.cleanup = cleanup
    result = worker.execute_task(task, profile)
    assert result["submission_possible"] is True
    assert result["cleanup_confirmed"] is True


@pytest.mark.parametrize("payload,exit_code", [("missing", 0), ("malformed", 0), ("missing", 9)])
def test_abnormal_child_without_marker_is_still_unknown(worker, profile, task, monkeypatch, payload, exit_code):
    install_child(worker, monkeypatch, Child(exit_code=exit_code), result=payload, submitted=False)
    result = worker.execute_task(task, profile)
    assert result["error_code"] == worker.unconfirmed_code
    assert result["submission_possible"] is True
