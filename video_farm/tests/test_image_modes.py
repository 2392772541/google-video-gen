"""Image provider regressions. No production DB, browser or paid calls."""
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from video_farm import db, web
from video_farm.models import Profile, Task
from video_farm.scheduler import VideoScheduler

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    path=tmp_path/'test.db'
    db.init_db(path)
    monkeypatch.setattr(web,'DB_PATH',path)
    monkeypatch.setattr(web,'UPLOADS_DIR',tmp_path/'uploads')
    return path

@pytest.fixture
def client(sandbox):
    # Do not enter the context manager: app lifespan must never start real workers.
    return TestClient(web.app,base_url='http://127.0.0.1:8088')

@pytest.mark.parametrize('engine,model',[
    ('flow','nano-pro'),('flow','nano2-lite'),('flow','nano2.1'),
    ('gemini','gemini-flash'),('gemini','gemini-pro'),
])
def test_create_preserves_image_provider(client,sandbox,engine,model):
    response=client.post('/api/tasks/create-image',data={
        'prompt':'test image','engine':engine,'model':model,'aspect_ratio':'1:1',
    })
    assert response.status_code==200,response.text
    task=db.get_task(response.json()['id'],sandbox)
    assert task.engine==engine
    assert task.model==model
    assert task.assigned_profile_id is None
    assert response.json()['engine']==engine

@pytest.mark.parametrize('engine,model',[
    ('vids','nano-pro'),('flow','imagen4'),('flow','nano2'),
    ('gemini','nano-pro'),('flow','gemini-flash'),
])
def test_reject_wrong_model_before_queuing(client,sandbox,engine,model):
    response=client.post('/api/tasks/create-image',data={'prompt':'test','engine':engine,'model':model})
    assert response.status_code==400
    assert db.list_tasks(db_path=sandbox)==[]

def test_gemini_image_dispatch(sandbox,tmp_path):
    profile=Profile(id='test-profile',name='test-only')
    db.add_profile(profile,sandbox)
    task=Task(id='test-gemini-image',prompt='test',engine='gemini',task_type='image',model='gemini-flash',aspect_ratio='1:1',status='running')
    db.add_task(task,sandbox)
    attempt_dir=tmp_path/task.id/'attempt_test'
    attempt_dir.mkdir(parents=True)
    image=attempt_dir/'generated.png'
    Image.new('RGB',(1024,1024),'blue').save(image)
    scheduler=VideoScheduler(db_path=sandbox,output_dir=tmp_path,qa_dir=tmp_path/'qa',max_workers=1)
    scheduler.flow_worker=Mock()
    scheduler.flow_worker.execute_image_task.side_effect=AssertionError('Gemini image must not use Flow')
    scheduler.gemini_worker=Mock()
    scheduler.gemini_worker.execute_image_task.return_value={'success':True,'output_image_paths':[str(image)],'attempt_dir':str(attempt_dir),'logs':''}
    try:
        scheduler.process_task_execution(task,profile)
        scheduler.gemini_worker.execute_image_task.assert_called_once()
        stored=db.get_task(task.id,sandbox)
        assert stored.status=='completed'
        assert json.loads(stored.output_image_paths)==[str(image)]
    finally:
        scheduler.executor.shutdown(wait=True)

def test_flow_dropdown_matches_web():
    html=(Path(__file__).parents[1]/'static'/'index.html').read_text('utf-8')
    section=html.split('id="select-image-model"',1)[1].split('</select>',1)[0]
    for label in ('Nano Banana Pro','Nano Banana 2 Lite','Nano Banana 2.1'):
        assert label in section
    assert 'imagen4' not in section
    assert 'id="select-image-engine"' in html
