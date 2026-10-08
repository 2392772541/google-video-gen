"""API-level fault injection: failure must never leave an executable half-batch."""
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Task

@pytest.fixture
def client(monkeypatch):
    conn = db.get_db_connection()
    actual = Path(conn.execute('PRAGMA database_list').fetchone()['file'])
    conn.close()
    monkeypatch.setattr(web, 'DB_PATH', actual)
    monkeypatch.setattr(web.mgr, 'scheduler', SimpleNamespace(lock=threading.Lock(), active_tasks={}))
    return TestClient(web.app, base_url='http://127.0.0.1:8088', raise_server_exceptions=False)

def snapshot():
    conn = db.get_db_connection()
    try:
        return {table: [dict(r) for r in conn.execute('SELECT * FROM ' + table + ' ORDER BY id')]
                for table in ('tasks', 'task_events', 'vids_workflows', 'vids_shots')}
    finally:
        conn.close()

def reject_insert(table, condition='1'):
    conn = db.get_db_connection()
    with conn:
        conn.execute(f"CREATE TRIGGER reject_insert BEFORE INSERT ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'injected write failure'); END")
    conn.close()

def import_payload(mode, auto_start):
    payload = {'import_mode': mode, 'auto_start': auto_start, 'engine': 'flow', 'data': {
        'title': 'incoming', 'engine': 'flow', 'aspect_ratio': '16:9', 'resolution': '720p',
        'model_name': 'veo-lite', 'shots': [
            {'name': 'good', 'prompt': 'good', 'duration': 8},
            {'name': 'bad', 'prompt': 'bad', 'duration': 8}]}}
    if mode != 'new':
        wf = db.create_vids_workflow('original', engine='flow', resolution='1080p')
        db.create_vids_shot(wf['id'], 'original shot', 'original prompt')
        payload['workflow_id'] = wf['id']
    return payload

def test_main_batch_event_failure_rolls_back_tasks(client):
    before = snapshot()
    reject_insert('task_events')
    response = client.post('/api/tasks/batch', json=[{'engine': 'flow', 'prompt': 'one'}, {'engine': 'flow', 'prompt': 'two'}])
    assert response.status_code == 500
    assert snapshot() == before

@pytest.mark.parametrize('mode', ['new', 'append', 'replace'])
@pytest.mark.parametrize('auto_start', [False, True])
def test_vids_import_shot_failure_keeps_previous_batch(client, mode, auto_start):
    payload = import_payload(mode, auto_start)
    before = snapshot()
    reject_insert('vids_shots', "NEW.name = 'bad'")
    response = client.post('/api/vids/batch_import', json=payload)
    assert response.status_code == 500, response.text
    assert snapshot() == before

@pytest.mark.parametrize('mode', ['new', 'append', 'replace'])
def test_vids_import_event_failure_rolls_back_whole_operation(client, mode):
    payload = import_payload(mode, True)
    before = snapshot()
    reject_insert('task_events')
    response = client.post('/api/vids/batch_import', json=payload)
    assert response.status_code == 500, response.text
    assert snapshot() == before

def test_existing_workflow_enqueue_event_failure_keeps_pending_shot(client):
    wf = db.create_vids_workflow('existing', engine='flow')
    shot = db.create_vids_shot(wf['id'], 'existing', 'test', engine='flow', duration=8)
    before = snapshot()
    reject_insert('task_events')
    response = client.post('/api/vids/shots/' + shot['id'] + '/generate')
    assert response.status_code == 500, response.text
    assert snapshot() == before


@pytest.mark.parametrize('mode', ['new', 'append', 'replace'])
@pytest.mark.parametrize('auto_start', [False, True])
def test_successful_vids_import_keeps_order_bindings_and_events(client, mode, auto_start):
    payload = import_payload(mode, auto_start)
    response = client.post('/api/vids/batch_import', json=payload)
    assert response.status_code == 200, response.text
    state = snapshot()
    assert len(state['vids_workflows']) == 1
    wf = state['vids_workflows'][0]
    assert wf['resolution'] == '720p'
    assert wf['status'] == ('generating' if auto_start else 'draft')
    shots = sorted(state['vids_shots'], key=lambda shot: shot['sequence'])
    expected = ['original shot', 'good', 'bad'] if mode == 'append' else ['good', 'bad']
    assert [shot['name'] for shot in shots] == expected
    assert [shot['sequence'] for shot in shots] == list(range(1, len(shots)+1))
    tasks = {task['id']: task for task in state['tasks']}
    assert len(tasks) == (2 if auto_start else 0)
    assert len(state['task_events']) == len(tasks)
    incoming = [shot for shot in shots if shot['name'] in ('good', 'bad')]
    for shot in incoming:
        assert shot['status'] == ('queued' if auto_start else 'pending')
        if auto_start:
            task = tasks[shot['task_id']]
            assert task['prompt'] == shot['prompt']
            assert task['engine'] == 'flow'
            assert task['assigned_profile_id'] is None
            assert any(event['task_id'] == task['id'] and event['event_type'] == 'TASK_CREATED_VIDS'
                       for event in state['task_events'])
        else:
            assert not shot['task_id']


def test_replace_conflicts_if_original_shots_changed_after_preflight(client, monkeypatch):
    payload = import_payload('replace', True)
    original = db.import_vids_batch
    expected = {}
    def raced(*args, **kwargs):
        db.create_vids_shot(payload['workflow_id'], 'concurrent shot', 'do not delete')
        expected.update(snapshot())
        return original(*args, **kwargs)
    monkeypatch.setattr(db, 'import_vids_batch', raced)
    response = client.post('/api/vids/batch_import', json=payload)
    assert response.status_code == 409, response.text
    assert snapshot() == expected


def test_main_batch_success_commits_events_with_every_task(client):
    response = client.post('/api/tasks/batch', json=[{'engine':'flow','prompt':'one'}, {'engine':'flow','prompt':'two'}])
    assert response.status_code == 200, response.text
    state = snapshot()
    assert len(state['tasks']) == len(state['task_events']) == 2
    assert {event['task_id'] for event in state['task_events']} == {task['id'] for task in state['tasks']}
