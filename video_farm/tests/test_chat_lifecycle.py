"""HTTP chat ownership, timeout cancellation and stop; no real provider calls."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Profile


def test_clean_thread_timeout_cancels_but_finishes_only_after_exit():
    entered, release, exited = threading.Event(), threading.Event(), threading.Event()
    cancel = Mock()
    def run():
        entered.set()
        release.wait(2)
        return {'success': True}
    try:
        result = web.run_in_clean_thread(run, wait_timeout=.02, on_timeout=cancel, on_finish=exited.set)
        assert entered.is_set()
        assert result['error_code'] == 'EXECUTION_TIMEOUT'
        cancel.assert_called_once()
        assert not exited.is_set(), 'timeout released a still-running owner'
    finally:
        release.set()
        assert exited.wait(2)


class WaitingWorker:
    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.events = {}
    def prepare_task(self, execution_id, event):
        self.events[execution_id] = event
    def cancel_task(self, execution_id):
        self.events[execution_id].set()
        return True
    def execute_multimodal_interaction(self, **kwargs):
        self.execution_id = kwargs['execution_id']
        self.profile = kwargs['profile']
        self.entered.set()
        self.release.wait(2)
        return {'success': False, 'error_code': 'USER_CANCELLED', 'error_message': 'stopped'}


def test_chat_stop_retains_owner_until_exit_and_rejects_duplicate_clear(tmp_path, monkeypatch):
    worker = WaitingWorker()
    scheduler = SimpleNamespace(lock=threading.Lock(), gemini_worker=worker, active_tasks={})
    monkeypatch.setattr(web.mgr, 'scheduler', scheduler)
    db.add_profile(Profile(id='chat_p', name='chat-p', profile_path=str(tmp_path)))
    client = TestClient(web.app, base_url='http://127.0.0.1:8088')
    responses = []
    th = threading.Thread(target=lambda: responses.append(client.post('/api/gemini/chat',data={'message':'hello','session_id':'lifecycle'})))
    th.start()
    try:
        assert worker.entered.wait(2)
        assert db.get_profile('chat_p').status == 'busy'
        status = client.get('/api/gemini/sessions/lifecycle/status')
        assert status.status_code == 200
        assert status.json()['state'] == 'running'
        assert client.post('/api/gemini/chat',data={'message':'duplicate','session_id':'lifecycle'}).status_code == 409
        assert client.delete('/api/gemini/messages?session_id=lifecycle').status_code == 409
        stop = client.post('/api/gemini/sessions/lifecycle/stop')
        assert stop.status_code == 200
        assert worker.events[worker.execution_id].is_set()
        assert client.get('/api/gemini/sessions/lifecycle/status').json()['state'] == 'stopping'
        assert db.get_profile('chat_p').status == 'busy'
    finally:
        worker.release.set()
        th.join(3)
    assert not th.is_alive()
    assert responses[0].status_code == 200, responses[0].text
    assert not client.get('/api/gemini/sessions/lifecycle/status').json()['active']
    assert db.get_profile('chat_p').status == 'idle'


def test_new_chat_never_picks_disabled_or_busy_account(tmp_path, monkeypatch):
    worker = WaitingWorker()
    worker.release.set()
    monkeypatch.setattr(web.mgr,'scheduler',SimpleNamespace(lock=threading.Lock(),gemini_worker=worker,active_tasks={}))
    for id, enabled, status in [('disabled',False,'idle'),('busy',True,'busy'),('ready',True,'idle')]:
        db.add_profile(Profile(id=id,name=id,enabled=enabled,status=status,profile_path=str(tmp_path/id)))
    r = TestClient(web.app,base_url='http://127.0.0.1:8088').post('/api/gemini/chat',data={'message':'hello','session_id':'selection'})
    assert r.status_code == 200, r.text
    assert worker.profile.id == 'ready'
    assert db.get_profile('busy').status == 'busy'


def test_database_failure_before_chat_start_discards_prepared_owner(tmp_path, monkeypatch):
    from video_farm.gemini_worker import GeminiWebWorker
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    monkeypatch.setattr(web.mgr, 'scheduler', SimpleNamespace(
        lock=threading.Lock(), gemini_worker=worker, active_tasks={}))
    db.add_profile(Profile(id='db_fail_p', name='db-fail', profile_path=str(tmp_path/'p')))
    def fail(*args, **kwargs):
        raise RuntimeError('isolated DB write failure')
    monkeypatch.setattr(db, 'add_gemini_message', fail)
    client = TestClient(web.app, base_url='http://127.0.0.1:8088', raise_server_exceptions=False)
    response = client.post('/api/gemini/chat', data={'message':'hello', 'session_id':'db-fail-test'})
    assert response.status_code == 500
    assert not worker._active_sessions
    assert db.get_profile('db_fail_p').status == 'idle'
    assert not client.get('/api/gemini/sessions/db-fail-test/status').json()['active']
