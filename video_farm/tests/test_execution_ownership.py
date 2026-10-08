"""Deterministic ownership/partial-stop/atomic-batch regressions; no live queue."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Profile, Task
from video_farm.scheduler import VideoScheduler

@pytest.fixture
def scheduler(tmp_path, monkeypatch):
    s = VideoScheduler(output_dir=tmp_path, qa_dir=tmp_path, max_workers=1)
    monkeypatch.setattr(web.mgr, 'scheduler', s)
    yield s
    s.executor.shutdown(wait=True)


def test_dispatch_reserves_claims_and_registers_under_shared_guard(scheduler, monkeypatch):
    p = Profile(id='p_guard', name='guard')
    db.add_profile(p)
    db.add_task(Task(id='t_guard', prompt='test'))
    original = db.acquire_idle_profile
    def acquire(*args, **kwargs):
        assert scheduler.lock.locked(), 'profile acquisition races account reset/close'
        return original(*args, **kwargs)
    monkeypatch.setattr(db, 'acquire_idle_profile', acquire)
    monkeypatch.setattr(scheduler.executor, 'submit', Mock())
    assert scheduler.dispatch_cycle() == 1
    assert 't_guard' in scheduler.active_tasks


@pytest.mark.parametrize('endpoint', ['reset-status', 'close-chrome', 'unlock', 'launch-chrome'])
def test_account_mutation_checks_inside_dispatch_guard(scheduler, monkeypatch, tmp_path, endpoint):
    p = Profile(id='p_guard', name='guard', profile_path=str(tmp_path / 'login'))
    db.add_profile(p)
    def check(profile):
        assert scheduler.lock.locked(), 'fresh profile read/check/mutation is not atomic'
    monkeypatch.setattr(web, 'require_profile_released', check)
    monkeypatch.setattr(web, 'close_chrome_for_profile', Mock(return_value=0))
    monkeypatch.setattr(web, 'check_chrome_running_for_profile', Mock(return_value=False))
    monkeypatch.setattr(web.subprocess, 'Popen', Mock())
    monkeypatch.setattr(web, 'watch_chrome_login_exit', Mock())
    res = TestClient(web.app, base_url="http://127.0.0.1:8088").post('/api/profiles/p_guard/' + endpoint)
    assert res.status_code == 200, res.text


def test_batch_stop_reports_retained_owner_and_failures(scheduler, monkeypatch):
    for name, status in [('queued','queued'),('active','running'),('done','completed')]:
        db.add_task(Task(id=name, prompt='test', status=status))
    scheduler.active_tasks['active'] = {'event': threading.Event(), 'task': db.get_task('active'), 'profile': Profile(id='p',name='p')}
    monkeypatch.setattr(scheduler.flow_worker, 'cancel_task', Mock(return_value=True))
    result = web.batch_cancel_tasks(web.BatchTasksReq(task_ids=['queued','active','done','missing','active']))
    assert result['success'] is False
    assert result['cancelled_ids'] == ['queued']
    assert result['stopping_ids'] == ['active']
    assert {e['task_id'] for e in result['errors']} == {'done','missing'}
    assert 'active' in scheduler.active_tasks


def test_rejected_executor_submission_releases_unstarted_owner(scheduler, monkeypatch):
    p = Profile(id='p_reject', name='reject')
    db.add_profile(p)
    db.add_task(Task(id='t_reject', prompt='test'))
    monkeypatch.setattr(scheduler.executor, 'submit', Mock(side_effect=RuntimeError('executor unavailable')))
    assert scheduler.dispatch_cycle() == 0
    assert 't_reject' not in scheduler.active_tasks
    assert db.get_profile(p.id).status == 'idle'
    assert db.get_task('t_reject').status == 'failed'


def test_atomic_enqueue_rolls_back_first_shot_when_second_changed():
    wf = db.create_vids_workflow('atomic')
    a = db.create_vids_shot(wf['id'],'a','test')
    b = db.create_vids_shot(wf['id'],'b','test',task_id='new-owner')
    with pytest.raises(db.TaskOperationConflict):
        db.enqueue_vids_shot_tasks(wf['id'], [(a['id'],Task(id='a',prompt='test'),''),(b['id'],Task(id='b',prompt='test'),'')])
    assert db.get_task('a') is None
    assert db.get_vids_shot(a['id'])['task_id'] == ''
    assert db.get_vids_workflow(wf['id'])['status'] == 'draft'


def test_atomic_reset_keeps_first_binding_when_second_is_running():
    wf = db.create_vids_workflow('reset')
    db.add_task(Task(id='old',prompt='test',status='completed'))
    db.add_task(Task(id='busy',prompt='test',status='running'))
    a = db.create_vids_shot(wf['id'],'a','test',task_id='old')
    b = db.create_vids_shot(wf['id'],'b','test',task_id='busy')
    with pytest.raises(db.TaskOperationConflict):
        db.reset_vids_workflow_shots(wf['id'], {a['id']:'old', b['id']:'busy'})
    assert db.get_vids_shot(a['id'])['task_id'] == 'old'
