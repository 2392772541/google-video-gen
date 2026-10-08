"""Opt-in real process-tree regression; no provider/browser/network activity.

VIDEO_FARM_PROCESS_REGRESSION=1 python -m pytest ... -q
The child calls the real Playwright SyncBase._sync with a dead dispatcher.
Media validation is explicitly mocked: this tests isolation, not generation.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from video_farm.models import Profile, Task
from video_farm.vids_worker import VidsWorker
from video_farm.gemini_worker import GeminiWebWorker

# Capture at collection time, before the autouse side-effect guards are applied.
# The fixture below admits only this exact local Python regression child.
_REAL_POPEN = subprocess.Popen
_FIXTURE = Path(__file__).parent / "fixtures" / "vids_process_fixture.py"
pytestmark = pytest.mark.skipif(
    os.environ.get("VIDEO_FARM_PROCESS_REGRESSION") != "1",
    reason="Explicit opt-in required for real local child processes",
)


@pytest.fixture
def local_process_permission(monkeypatch):
    def fixture_only(command, *args, **kwargs):
        assert isinstance(command, (list, tuple)) and len(command) == 3
        assert Path(command[0]).resolve() == Path(sys.executable).resolve()
        assert Path(command[1]).resolve() == _FIXTURE.resolve()
        request = Path(command[2]).resolve()
        assert request.name == "request.json" and request.parent.name.startswith("attempt_")
        return _REAL_POPEN(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, "Popen", fixture_only)
    # Network and sync_playwright guards remain in force.


def hold_exit_observer(pid):
    if sys.platform != "win32":
        return lambda: _posix_exited(pid), lambda: None
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
    assert handle, "The fixture descendant must be observed while alive"
    return lambda: kernel.WaitForSingleObject(handle, 0) == 0, lambda: kernel.CloseHandle(handle)


def _posix_exited(pid):
    stat = Path("/proc") / str(pid) / "stat"
    if stat.exists() and stat.read_text().split(")", 1)[1].strip().startswith("Z"):
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


@pytest.mark.parametrize("provider", ["vids", "gemini"])
@pytest.mark.parametrize("stop_kind", ["cancel", "deadline"])
@pytest.mark.parametrize("submitted", [False, True])
def test_dead_sync_is_contained_and_next_task_can_run(
        tmp_path, monkeypatch, local_process_permission, stop_kind, submitted, provider):
    worker_class = VidsWorker if provider == "vids" else GeminiWebWorker
    worker = worker_class(output_dir=tmp_path / "outputs", timeout_sec=10)
    monkeypatch.setattr(worker, "_runner_command", lambda path: [sys.executable, str(_FIXTURE), str(path)])
    monkeypatch.setattr(worker, "_validate_output", Mock())
    original_launch = worker._launch_runner
    processes = []
    def tracked_launch(*args):
        proc = original_launch(*args)
        processes.append(proc)
        return proc
    monkeypatch.setattr(worker, "_launch_runner", tracked_launch)
    profile = Profile(id="profile_fixture", name="fixture", profile_path=str(tmp_path / "profile"))
    task = Task(id="task_dead_sync", prompt="dead sync submitted" if submitted else "dead sync",
                engine=provider, model="Omni (1080p)" if provider == "vids" else "veo", duration_sec=3, aspect_ratio="16:9")
    result = {}
    errors = []
    def execute():
        try:
            result.update(worker.execute_task(task, profile))
        except BaseException as exc:
            errors.append(exc)
    thread = threading.Thread(target=execute, daemon=True)
    close_observer = lambda: None
    thread.start()
    try:
        ready = None
        startup_deadline = time.monotonic() + 7
        while time.monotonic() < startup_deadline and thread.is_alive():
            markers = list(worker.output_dir.glob(task.id + "/attempt_*/ready.json"))
            if markers:
                try:
                    ready = json.loads(markers[0].read_text(encoding="utf8"))
                    break
                except (ValueError, OSError):
                    pass
            time.sleep(0.02)
        assert ready and ready["real_sync"] and ready["dispatcher_dead"], (result, errors)
        descendant_exited, close_observer = hold_exit_observer(ready["descendant_pid"])
        assert not descendant_exited()
        # Avoid timing a cold Python import: trigger the hard deadline only
        # after the child is observed inside the dead-dispatcher scenario.
        started = time.monotonic()
        if stop_kind == "cancel":
            assert worker.cancel_task(task.id)
        else:
            with worker._sessions_lock:
                worker._active_sessions[task.id]["control"].deadline = time.monotonic() + 0.12
        thread.join(timeout=5)
        elapsed = time.monotonic() - started
        assert not thread.is_alive(), "Parent supervisor did not escape the dead sync"
        assert not errors, errors
        assert elapsed < 4
        assert result["success"] is False
        assert result["cleanup_confirmed"] is True
        # The real child tree has exited; absent durable click receipt proves
        # this explicit stop occurred before submission, not an unknown crash.
        assert result["submission_possible"] is submitted
        expected_code = "USER_CANCELLED" if stop_kind == "cancel" else worker.unconfirmed_code if submitted else "PRE_SUBMIT_TIMEOUT"
        assert result["error_code"] == expected_code
        assert descendant_exited(), "Cleanup returned before the descendant actually exited"
        assert processes[0].poll() is not None
        assert not worker.has_live_execution(task.id)
        attempt = Path(result["attempt_dir"])
        assert (attempt / "submission.json").exists() is submitted
        assert "real SyncBase._sync" in (attempt / "runner.log").read_text(encoding="utf8")
        assert not (worker.output_dir / (task.id + ".mp4")).exists()
        following = Task(id="task_after_dead_sync", prompt="complete fixture", engine=provider,
                         model="Omni (1080p)" if provider == "vids" else "veo", duration_sec=3, aspect_ratio="16:9")
        success = worker.execute_task(following, profile)
        assert success["success"] is True and success["cleanup_confirmed"] is True
        assert Path(success["output_video_path"]).is_file()
        assert not worker.has_live_execution(following.id)
    finally:
        worker.cancel_task(task.id)
        for proc in processes:
            proc.cleanup()
        thread.join(timeout=3)
        close_observer()
