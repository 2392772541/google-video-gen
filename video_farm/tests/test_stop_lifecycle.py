"""Cancellation cannot reuse resources or turn cancelled work into failure."""
import threading
from unittest.mock import MagicMock
import pytest
from video_farm import db
from video_farm.models import Profile, Task
from video_farm.scheduler import VideoScheduler, classify_failure
from video_farm.vids_worker import VidsWorker
from video_farm.gemini_worker import GeminiWebWorker


@pytest.mark.parametrize("worker_cls", [VidsWorker, GeminiWebWorker])
def test_cancel_signals_owner_without_cross_thread_browser_calls(worker_cls, tmp_path):
    worker = worker_cls(output_dir=tmp_path)
    browser = MagicMock()
    worker._active_sessions['job'] = {'browser': browser, 'cancelled': False,
                                     'cancel_event': threading.Event()}
    assert worker.cancel_task('job')
    assert worker._active_sessions['job']['cancelled']
    browser.close.assert_not_called()


@pytest.mark.parametrize('state', ['running', 'dispatching', 'verifying'])
def test_stop_keeps_profile_busy_until_execution_exits(state):
    profile = Profile(id='p_stop', name='stop test', status='busy')
    db.add_profile(profile)
    task = Task(id='t_stop', prompt='stop', status=state, assigned_profile_id=profile.id)
    db.add_task(task)
    db.transition_task(task.id, 'stop')
    assert db.get_task(task.id).status == 'cancelled'
    assert db.get_profile(profile.id).status == 'busy'


def test_scheduler_cancel_retains_slot_and_cancelled_on_late_exception(tmp_path):
    profile = Profile(id='p_late', name='late', status='busy')
    task = Task(id='t_late', prompt='late', engine='flow', status='running', assigned_profile_id=profile.id)
    db.add_profile(profile)
    db.add_task(task)
    scheduler = VideoScheduler(output_dir=tmp_path, qa_dir=tmp_path, max_workers=1)
    entered, release = threading.Event(), threading.Event()
    def execute(*args):
        entered.set()
        assert release.wait(3)
        raise RuntimeError('browser closed after user stop')
    scheduler.flow_worker.execute_task = execute
    scheduler.flow_worker.cancel_task = MagicMock(return_value=True)
    scheduler.vids_worker.cancel_task = MagicMock(return_value=False)
    scheduler.gemini_worker.cancel_task = MagicMock(return_value=False)
    scheduler.active_tasks[task.id] = {'event': threading.Event(), 'task': task, 'profile': profile}
    thread = threading.Thread(target=scheduler.process_task_execution, args=(task, profile))
    thread.start()
    try:
        assert entered.wait(2)
        db.transition_task(task.id, 'stop')
        scheduler.cancel_task(task.id)
        assert task.id in scheduler.active_tasks
        assert db.get_profile(profile.id).status == 'busy'
    finally:
        release.set()
        thread.join(3)
        scheduler.executor.shutdown(wait=True)
    assert not thread.is_alive()
    assert db.get_task(task.id).status == 'cancelled'
    assert db.get_profile(profile.id).status == 'idle'
    assert task.id not in scheduler.active_tasks


def test_wire_missing_record_does_not_claim_frames_were_dropped():
    category, message, _, _ = classify_failure('EXIT_7', 'WireFormatError: no generation record in the reply', '')
    assert category == 'FLOW_RESPONSE_UNREADABLE'
    assert '未满足首尾帧' not in message
    assert '勿直接重新生成' in message


def test_vids_invalid_frames_rejected_before_launch(tmp_path, monkeypatch):
    worker = VidsWorker(output_dir=tmp_path)
    task = Task(id='invalid', prompt='animate', engine='vids', start_image_path=str(tmp_path/'missing.png'))
    def forbidden(*args):
        pytest.fail('invalid input reached browser setup')
    monkeypatch.setattr(worker, '_resolve_profile_dir', forbidden)
    result = worker.execute_task(task, Profile(id='p', name='unused'))
    assert not result['success']
    assert result['error_code'] == 'INVALID_VIDEO_REQUEST'


def test_unreaped_process_quarantines_profile_not_entire_queue(tmp_path):
    scheduler = VideoScheduler(output_dir=tmp_path, qa_dir=tmp_path, max_workers=1)
    profile = Profile(id="p_orphan", name="orphan", status="busy")
    task = Task(id="t_orphan", prompt="test", status="running", engine="flow")
    db.add_profile(profile)
    db.add_task(task)
    scheduler.active_tasks[task.id] = {"event": threading.Event(), "task": task, "profile": profile}
    scheduler.flow_worker.execute_task = MagicMock(return_value={
        "success": False, "error_code": "USER_CANCELLED", "cleanup_confirmed": False})
    scheduler.flow_worker.has_live_execution = MagicMock(return_value=True)
    db.transition_task(task.id, "stop")
    scheduler.process_task_execution(task, profile)
    assert db.get_profile(profile.id).status == "busy"
    assert scheduler.active_tasks[task.id]["cleanup_failed"]
    db.add_profile(Profile(id="p_free", name="free"))
    db.add_task(Task(id="t_next", prompt="next", engine="flow"))
    scheduler.executor.submit = MagicMock()
    assert scheduler.dispatch_cycle() == 1
    assert scheduler.executor.submit.call_args.args[2].id == "p_free"
    scheduler.flow_worker.has_live_execution.return_value = False
    scheduler.dispatch_cycle()
    assert task.id not in scheduler.active_tasks
    assert db.get_profile(profile.id).status == "idle"
    scheduler.executor.shutdown(wait=True)


def test_retry_of_started_cancelled_job_requires_result_reconciliation():
    started = Task(id="stopped-running", prompt="test", status="running")
    db.add_task(started)
    db.transition_task(started.id, "stop")
    with pytest.raises(db.TaskOperationConflict):
        db.transition_task(started.id, "retry")
    queued = Task(id="cancelled-queued", prompt="test", status="queued")
    db.add_task(queued)
    db.transition_task(queued.id, "cancel")
    assert db.transition_task(queued.id, "retry")["status"] == "queued"



def test_pre_submit_timeout_is_terminal_even_when_logs_contain_quota():
    from video_farm.scheduler import TERMINAL_FAILURES
    category, message, cooldown, retries = classify_failure("PRE_SUBMIT_TIMEOUT", "未提交超时", "quota exhausted")
    assert category == "PRE_SUBMIT_TIMEOUT"
    assert category in TERMINAL_FAILURES and cooldown == 0 and retries is False


@pytest.mark.parametrize("provider", ["vids", "gemini"])
@pytest.mark.parametrize("possible,cleaned,known_safe", [(False, True, True), (True, True, False), (None, True, False), (False, False, False)])
def test_stopped_scheduler_unlocks_retry_only_with_confirmed_pre_submit_evidence(tmp_path, provider, possible, cleaned, known_safe):
    scheduler = VideoScheduler(output_dir=tmp_path, qa_dir=tmp_path, max_workers=1)
    profile = Profile(id="p_proven_stop", name="proven stop", status="busy")
    task = Task(id="t_proven_stop", prompt="stop", status="running", engine=provider, assigned_profile_id=profile.id)
    db.add_profile(profile)
    db.add_task(task)
    worker = scheduler.vids_worker if provider == "vids" else scheduler.gemini_worker
    entered, release = threading.Event(), threading.Event()
    def execute(*args):
        entered.set()
        assert release.wait(3)
        result = {"success": False, "error_code": "USER_CANCELLED", "cleanup_confirmed": cleaned}
        if possible is not None:
            result["submission_possible"] = possible
        return result
    worker.execute_task = execute
    worker.cancel_task = MagicMock(return_value=True)
    scheduler.active_tasks[task.id] = {"event": threading.Event(), "task": task, "profile": profile}
    thread = threading.Thread(target=scheduler.process_task_execution, args=(task, profile))
    thread.start()
    try:
        assert entered.wait(2)
        db.transition_task(task.id, "stop")
        scheduler.cancel_task(task.id)
        with pytest.raises(db.TaskOperationConflict):
            db.transition_task(task.id, "retry")
    finally:
        release.set()
        thread.join(3)
        scheduler.executor.shutdown(wait=True)
    assert not thread.is_alive()
    stopped = db.get_task(task.id)
    assert stopped.status == "cancelled"
    assert stopped.error_code == ("USER_CANCELLED" if known_safe else "STOP_RESULT_UNCONFIRMED")
    if known_safe:
        assert db.transition_task(task.id, "retry")["status"] == "queued"
    else:
        with pytest.raises(db.TaskOperationConflict):
            db.transition_task(task.id, "retry")
