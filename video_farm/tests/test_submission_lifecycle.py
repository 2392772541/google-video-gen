import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from video_farm import db, web
from video_farm.models import Profile, Task

@pytest.fixture
def client(tmp_path, monkeypatch):
    path=tmp_path/'test.db'
    db.init_db(path)
    monkeypatch.setattr(web,'DB_PATH',path)
    monkeypatch.setattr(web,'UPLOADS_DIR',tmp_path/'uploads')
    monkeypatch.setattr(web.subprocess,'Popen',Mock(side_effect=AssertionError('No browser launch in unit tests')))
    monkeypatch.setattr(web.mgr,'scheduler',SimpleNamespace(lock=threading.Lock(),active_tasks={}))
    return TestClient(web.app,base_url='http://127.0.0.1:8088')

@pytest.mark.parametrize('fields',[
    {'engine':'vids','model':'Omni (1080p)','end_image_path':'missing.png'},
    {'engine':'vids','model':'Omni (1080p)','start_image_path':'missing.png'},
    {'engine':'typo','model':'veo-lite'},
    {'engine':'gemini','model':'auto','input_video_path':'missing.mp4'},
    {'engine':'flow','task_type':'image'},
])
def test_create_video_cannot_bypass_capability_or_asset_validation(client,fields):
    res=client.post('/api/tasks/create',data={'prompt':'test',**fields})
    assert res.status_code in (400,422),res.text
    assert db.list_tasks(db_path=web.DB_PATH)==[]


def test_auto_profile_is_not_pinned_by_single_create(client):
    db.add_profile(Profile(id='p-test',name='test'),web.DB_PATH)
    res=client.post('/api/tasks/create',data={'prompt':'test','engine':'flow','model':'veo-lite'})
    assert res.status_code==200,res.text
    assert db.get_task(res.json()['id'],web.DB_PATH).assigned_profile_id is None


def test_invalid_second_batch_item_creates_no_partial_queue(client):
    res=client.post('/api/tasks/batch',json=[{'prompt':'valid','engine':'flow'}, {'prompt':'bad','engine':'vids','model':'Omni','start_image_path':'missing.png'}])
    assert res.status_code in (400,422),res.text
    assert not db.list_tasks(db_path=web.DB_PATH)

@pytest.mark.parametrize('operation',['retry','delete','unlock','launch-chrome','close-chrome'])
def test_resources_owned_by_stopping_worker_cannot_be_reused(client,monkeypatch,operation):
    profile=Profile(id='p-owned',name='owned',status='busy')
    task=Task(id='task-owned',prompt='test',engine='vids',status='cancelled',assigned_profile_id=profile.id)
    db.add_profile(profile,web.DB_PATH)
    db.add_task(task,web.DB_PATH)
    web.mgr.scheduler.active_tasks[task.id]={'task':task,'profile':profile,'event':threading.Event()}
    close=Mock()
    monkeypatch.setattr(web,'close_chrome_for_profile',close)
    if operation=='delete':
        res=client.delete('/api/tasks/'+task.id)
    elif operation=='retry':
        res=client.post('/api/tasks/'+task.id+'/retry')
    else:
        res=client.post('/api/profiles/'+profile.id+'/'+operation)
    assert res.status_code==409,res.text
    close.assert_not_called()
    assert db.get_task(task.id,web.DB_PATH).status=='cancelled'

def test_cancelled_shot_keeps_owner_link(client):
    wf=db.create_vids_workflow('owner',db_path=web.DB_PATH)
    shot=db.create_vids_shot(wf['id'],'one',prompt='test',db_path=web.DB_PATH)
    task=Task(id='owner-link',prompt='test',engine='vids',status='cancelled')
    db.add_task(task,web.DB_PATH)
    db.update_vids_shot(shot['id'],{'task_id':task.id,'status':'running'},db_path=web.DB_PATH)
    synced=db.get_vids_shot(shot['id'],web.DB_PATH)
    assert synced['task_id']==task.id
    assert synced['status']=='cancelled'


def test_sync_queued_shot_does_not_write_on_every_poll(client):
    wf=db.create_vids_workflow('poll',db_path=web.DB_PATH)
    shot=db.create_vids_shot(wf['id'],'one',prompt='test',db_path=web.DB_PATH)
    task=Task(id='poll-task',prompt='test')
    db.enqueue_vids_shot_task(shot['id'],task,db_path=web.DB_PATH)
    first=db.get_vids_shot(shot['id'],web.DB_PATH)
    second=db.get_vids_shot(shot['id'],web.DB_PATH)
    assert second['updated_at']==first['updated_at']

@pytest.mark.parametrize('operation',['generate','delete','delete-workflow','reset'])
def test_vids_stopping_owner_blocks_mutations(client,operation):
    # Router defaults are isolated by conftest; use its same DB for both surfaces.
    conn=db.get_db_connection()
    actual=conn.execute('PRAGMA database_list').fetchone()['file'];conn.close()
    web.DB_PATH=__import__('pathlib').Path(actual)
    wf=db.create_vids_workflow('owner')
    shot=db.create_vids_shot(wf['id'],'one',prompt='test',duration=3)
    task=Task(id='task-vids-owner',prompt='test',engine='vids',status='cancelled')
    db.add_task(task)
    db.update_vids_shot(shot['id'],{'task_id':task.id,'status':'running'})
    web.mgr.scheduler.active_tasks[task.id]={'task':task,'event':threading.Event()}
    if operation=='generate':
        res=client.post('/api/vids/shots/'+shot['id']+'/generate')
    elif operation=='delete':
        res=client.delete('/api/vids/shots/'+shot['id'])
    elif operation=='delete-workflow':
        res=client.delete('/api/vids/workflows/'+wf['id'])
    else:
        res=client.post('/api/vids/workflows/'+wf['id']+'/reset_status')
    assert res.status_code==409,res.text
    assert db.get_vids_shot(shot['id'])['task_id']==task.id


def test_restart_never_resubmits_unknown_running_request(tmp_path):
    from video_farm.scheduler import VideoScheduler
    task=Task(id='orphan',prompt='submitted',status='running',engine='vids')
    db.add_task(task)
    scheduler=VideoScheduler(output_dir=tmp_path,qa_dir=tmp_path)
    try:
        scheduler.recover_orphans()
        assert db.get_task(task.id).status=='failed'
        assert db.get_task(task.id).error_code=='RESULT_UNCONFIRMED'
        with pytest.raises(db.TaskOperationConflict):
            db.transition_task(task.id,'retry')
    finally:
        scheduler.executor.shutdown(wait=True)
