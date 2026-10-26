"""Never confuse a post-submit response parse failure with invalid frame input."""
import json
from unittest.mock import patch

import pytest
from starlette.responses import Response

from video_farm import db, web
from video_farm.models import Task, Profile
from video_farm.scheduler import classify_failure
from video_farm.worker import VideoWorker

DETAIL = "batchexecute nprQif: no generation record ([uuid, uuid, uuid, 'CAE', ...]) in the reply"
LOGS = json.dumps({"error": {"class": "WireFormatError", "detail": DETAIL, "route": "batchexecute:nprQif"}})


def emit_process(process):
    def launch(command, **kwargs):
        for name in ("stdout", "stderr"):
            stream = kwargs[name]
            stream.write(getattr(process, name).encode("utf-8"))
            stream.flush()
        return process
    return launch


@pytest.mark.parametrize("code", ["EXIT_7", "WIRE_FORMAT_MISMATCH", "FLOW_RESPONSE_UNREADABLE"])
def test_missing_record_classification_is_terminal_without_blame_on_frames(code):
    category, message, cooldown, retry = classify_failure(code, "Process exited", LOGS + " credits quota exceeded")
    assert category == "FLOW_RESPONSE_UNREADABLE"
    assert cooldown == 0 and retry is False
    assert "首尾帧约束" not in message and "扣" in message
    assert "原 Flow 项目" in message


def test_pre_submit_frame_guard_remains_distinct():
    category, _, cooldown, retry = classify_failure("EXIT_7", "Process exited", 'WireFormatError: expected interpolation; blocked before network')
    assert category == "WIRE_FORMAT_MISMATCH" and cooldown == 0 and retry is False


def test_worker_maps_record_parse_error_before_other_log_tokens(tmp_path):
    class FakeProcess:
        pid = 123
        returncode = 7
        def poll(self):
            return self.returncode
        def cleanup(self):
            return True
        def is_alive(self):
            return False
        stdout = LOGS
        stderr = "earlier status 4; unusual_activity; credits"
        def wait(self, timeout=None):
            return self.returncode
    worker = VideoWorker(gflow_dir=tmp_path, output_dir=tmp_path / "outputs")
    task = Task(id="test-response-worker", prompt="safe test", project_id="test-project")
    profile = Profile(id="test-profile", name="test-profile")
    with patch.object(worker, "_ensure_profile_marker"), patch("video_farm.worker.VideoWorker._launch_cli", side_effect=emit_process(FakeProcess())) as popen:
        result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert result["error_code"] == "FLOW_RESPONSE_UNREADABLE"
    assert "原 Flow 项目" in result["error_message"]
    assert popen.call_count == 1


@pytest.mark.parametrize("code", ["FLOW_RESPONSE_UNREADABLE", "WIRE_FORMAT_MISMATCH"])
def test_manual_retry_blocks_possible_duplicate_generation(isolated_task_database, code):
    task = Task(id="test-response-retry", prompt="safe test", status="failed", error_code=code, logs=LOGS)
    db.add_task(task)
    db.update_task_status(task.id, "failed", error_code=task.error_code, error_message=task.error_message, logs=task.logs)
    with pytest.raises(db.TaskOperationConflict, match="原 Flow 项目"):
        db.transition_task(task.id, "retry")
    stored = db.get_task_by_id(task.id)
    assert stored.status == "failed" and stored.retry_count == 0


def test_list_projects_legacy_failure_as_response_error_without_editing_history(isolated_task_database):
    task = Task(id="test-response-display", prompt="safe test", status="failed", error_code="WIRE_FORMAT_MISMATCH", error_message="Flow 实际提交未满足首尾帧约束", logs=LOGS)
    db.add_task(task)
    db.update_task_status(task.id, "failed", error_code=task.error_code, error_message=task.error_message, logs=task.logs)
    rows = web.get_tasks(Response(), limit=10, offset=0)
    row = next(row for row in rows if row["id"] == task.id)
    assert row["error_code"] == "FLOW_RESPONSE_UNREADABLE"
    assert "原 Flow 项目" in row["error_message"]
    stored = db.get_task_by_id(task.id)
    assert stored.error_code == "WIRE_FORMAT_MISMATCH" and stored.logs == LOGS


@pytest.mark.parametrize("stderr", ['401 Unauthorized', 'project not found'])
def test_flow_never_onboards_and_resubmits_after_failed_attempt(tmp_path, stderr):
    class FakeProcess:
        pid = 123
        returncode = 1
        def poll(self):
            return self.returncode
        def cleanup(self):
            return True
        def is_alive(self):
            return False
        stdout = ""
        def wait(self, timeout=None):
            return self.returncode
    worker = VideoWorker(gflow_dir=tmp_path, output_dir=tmp_path / "outputs")
    task = Task(id="no-transparent-retry", prompt="safe test", project_id="project")
    profile = Profile(id="p", name="p")
    FakeProcess.stderr = stderr
    with patch.object(worker, "_ensure_profile_marker"), patch("video_farm.worker.VideoWorker._launch_cli", side_effect=emit_process(FakeProcess())) as popen, patch("video_farm.onboard.auto_onboard_profile", return_value={"success": True, "project_id": "new-project"}) as onboard:
        result = worker.execute_task(task, profile)
    assert result["success"] is False
    assert popen.call_count == 1
    onboard.assert_not_called()


def test_flow_preserves_requested_duration_in_command(tmp_path):
    class FakeProcess:
        pid = 123
        returncode = 11
        def poll(self):
            return self.returncode
        def cleanup(self):
            return True
        def is_alive(self):
            return False
        stdout = ""
        stderr = "ConfigurationError: renders no duration control"
        def wait(self, timeout=None):
            return self.returncode
    worker = VideoWorker(gflow_dir=tmp_path, output_dir=tmp_path / "outputs")
    task = Task(id="preserve-duration", prompt="safe test", project_id="project", model="omni-flash", duration_sec=10)
    with patch.object(worker, "_ensure_profile_marker"), patch("video_farm.worker.VideoWorker._launch_cli", side_effect=emit_process(FakeProcess())) as popen:
        result = worker.execute_task(task, Profile(id="p", name="p"))
    command = popen.call_args.args[0]
    assert command[command.index("--duration") + 1] == "10"
    assert result["error_code"] in ("CONFIG_ERROR", "DURATION_CONTROL_ABSENT")
    assert classify_failure(result["error_code"], result["error_message"], result["logs"])[3] is False
