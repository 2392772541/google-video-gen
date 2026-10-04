"""Audit regressions. Temporary DB/files only; no scheduler lifespan, login or credit use.
Run: python -m unittest video_farm.tests.test_system_audit -v
"""
import asyncio
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from PIL import Image
from video_farm import db, web, pipeline, vids_router, maintenance
from video_farm.models import Task, Profile
from video_farm.local_security import LocalBrowserBoundary, local_file
from video_farm.timeline_spec import TimelineSpec, TracksSpec, ShotSpec

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='video_farm_audit_')
        self.root = Path(self.temp.name)
        self.data = self.root / 'video_farm_data'
        self.database = self.data / 'tasks.db'
        db.init_db(self.database)
        self.client = TestClient(web.app, base_url='http://127.0.0.1:8088')  # deliberately no lifespan
        self.patchdb = patch.object(web, 'DB_PATH', self.database)
        self.patchdb.start()
    def tearDown(self):
        self.patchdb.stop(); self.client.close(); self.temp.cleanup()
    def add(self, id='task_test', **kwargs):
        t=Task(id=id,prompt='审核隔离样例',**kwargs)
        db.add_task(t,self.database)
        # add_task intentionally writes submission fields only. Seed result fields
        # separately to model tasks after worker completion.
        conn=db.get_db_connection(self.database)
        try:
            columns={r[1] for r in conn.execute('PRAGMA table_info(tasks)')}
            values={k:v for k,v in kwargs.items() if k in columns}
            if values:
                with conn:
                    conn.execute('UPDATE tasks SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),id])
        finally: conn.close()
        return t
    def test_local_get_and_pagination(self):
        for i in range(105): self.add(f'task_{i:03d}',status='completed')
        r=self.client.get('/api/tasks?limit=100'); self.assertEqual(r.status_code,200)
        self.assertEqual(r.headers['x-total-count'],'105'); self.assertEqual(len(r.json()),100)
        r2=self.client.get('/api/tasks?limit=100&offset=100'); self.assertEqual(len(r2.json()),5)
        self.assertFalse(set(t['id'] for t in r.json()) & set(t['id'] for t in r2.json()))
        self.assertEqual(self.client.get('/api/overview').json()['tasks']['completed'],105)
    def test_invalid_pagination(self):
        for q in ('limit=-1','limit=501','offset=-1'):
            self.assertEqual(self.client.get('/api/tasks?'+q).status_code,422)
    def test_statistics_over_500(self):
        for i in range(520): self.add(f'task_{i:03d}', status='completed')
        self.assertEqual(self.client.get('/api/overview').json()['tasks']['total'],520)
    def test_bad_origin_get_preflight_and_simple_post(self):
        self.add()
        for method,path in [('GET','/api/tasks'),('POST','/api/tasks/task_test/cancel'),('OPTIONS','/api/tasks/create')]:
            r=self.client.request(method,path,headers={'Origin':'https://untrusted.example','Access-Control-Request-Method':'POST'})
            self.assertEqual(r.status_code,403)
            self.assertNotIn('access-control-allow-origin',r.headers)
        self.assertEqual(db.get_task('task_test',self.database).status,'queued')
    def test_local_origin_works(self):
        self.add();r=self.client.post('/api/tasks/task_test/cancel',headers={'Origin':'http://127.0.0.1:8088'})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get('/api/tasks',headers={'Origin':'http://127.0.0.1:9999'}).status_code,403)
    def test_host_fetch_metadata_referer(self):
        for headers in ({'Host':'evil.example:8088'},{'Sec-Fetch-Site':'cross-site'},{'Referer':'https://evil.example/'},{'Origin':'null'},{'Host':'127.0.0.1:bad'}):
            self.assertEqual(self.client.get('/api/tasks',headers=headers).status_code,403)
    def test_security_response_headers(self):
        r=self.client.get('/api/tasks');self.assertEqual(r.headers['x-content-type-options'],'nosniff')
        self.assertEqual(r.headers['cross-origin-resource-policy'],'same-origin')
    def test_body_limit_content_length(self):
        r=self.client.post('/api/tasks/batch-delete',headers={'Content-Length':str(513*1024**2)},content='{}');self.assertEqual(r.status_code,413)
    def test_chunked_body_limit(self):
        a=FastAPI();a.add_middleware(LocalBrowserBoundary,max_body_bytes=16)
        @a.post('/api/read')
        async def read(req:Request): return {'n':len(await req.body())}
        c=TestClient(a,base_url='http://127.0.0.1:8088')
        r=c.post('/api/read',content=iter([b'x'*10,b'y'*10]));self.assertEqual(r.status_code,413)
        self.assertEqual(c.post('/api/read',content=b'x'*10).status_code,200); c.close()
    def test_internal_secrets_and_network_paths_denied(self):
        for path in (str(self.database),'\\\\server\\share\\x.mp4',str(Path(web.BASE_DIR)/'requirements.txt')):
            for route in ('/media/file','/api/pipeline/file-preview','/api/pipeline/download'):
                self.assertEqual(self.client.get(route,params={'path':path}).status_code,403)
    def test_external_image_mime_and_range(self):
        file=self.root/'素材.jpg'; Image.new('RGB',(20,20),'red').save(file)
        r=self.client.get('/media/file',params={'path':str(file)});self.assertEqual(r.status_code,200);self.assertIn('image/jpeg',r.headers['content-type'])
        r=self.client.get('/media/file',params={'path':str(file)},headers={'Range':'bytes=0-9'});self.assertEqual(r.status_code,206);self.assertEqual(len(r.content),10)
        self.assertEqual(self.client.get('/media/file',params={'path':str(file)},headers={'Range':'bytes=99999-'}).status_code,416)
    def test_directory_denied(self):
        p=self.root/'fake.mp4';p.mkdir();self.assertEqual(self.client.get('/media/file',params={'path':str(p)}).status_code,404)
    def test_audio_quarantine_and_manifest(self):
        p=self.data/'outputs'/'audio.wav';p.parent.mkdir();p.write_bytes(b'RIFFtest')
        self.add(status='completed',output_audio_path=str(p),task_type='audio')
        r=db.delete_task('task_test',db_path=self.database);self.assertTrue(r['deleted']);self.assertFalse(p.exists())
        m=json.loads((Path(r['trash_path'])/'manifest.json').read_text('utf8'));self.assertEqual(Path(m['moved_files'][0]['target']).read_bytes(),b'RIFFtest')
        self.assertEqual(m['task']['task_type'],'audio')
    def test_external_output_and_original_input_retained(self):
        file=self.root/'original.mp4';file.write_bytes(b'x')
        self.add(status='completed',output_video_path=str(file),start_image_path=str(file))
        r=db.delete_task('task_test',db_path=self.database);self.assertTrue(file.exists());self.assertTrue(r['skipped_files'])
    def test_shared_task_output_retained(self):
        p=self.data/'outputs'/'shared.png';p.parent.mkdir();p.write_bytes(b'x')
        self.add(status='completed',output_image_paths=json.dumps([str(p)]))
        self.add('task_other',start_image_path=str(p))
        r=db.delete_task('task_test',db_path=self.database);self.assertTrue(p.exists());self.assertTrue(r['skipped_files'])
    def test_workflow_reference_retained(self):
        p=self.data/'outputs'/'shared.mp4';p.parent.mkdir();p.write_bytes(b'x');self.add(status='completed',output_video_path=str(p))
        c=db.get_db_connection(self.database)
        with c: c.execute("INSERT INTO vids_shots(id,workflow_id,name,prompt,created_at,updated_at,local_video_path) VALUES('shot_test','wf','x','x','now','now',?)",(str(p),))
        c.close();db.delete_task('task_test',db_path=self.database);self.assertTrue(p.exists())
    def test_active_delete_retry_cancel_all_conflict(self):
        self.add(status='running')
        for method,path in [('DELETE','/api/tasks/task_test'),('POST','/api/tasks/task_test/retry'),('POST','/api/tasks/task_test/cancel')]:
            self.assertEqual(self.client.request(method,path).status_code,409)
        self.assertEqual(db.get_task('task_test',self.database).status,'running')
    def test_batch_partial_truthful_and_deduplicated(self):
        self.add(status='running');self.add('task_done',status='completed')
        r=self.client.post('/api/tasks/batch-delete',json={'task_ids':['task_test','task_done','task_done','missing']}).json()
        self.assertFalse(r['success']);self.assertEqual(r['deleted_count'],1);self.assertEqual(len(r['results']),3)
    def test_move_failure_rolls_back(self):
        p=self.data/'outputs'/'out.mp4';p.parent.mkdir();p.write_bytes(b'x');self.add(status='completed',output_video_path=str(p))
        with patch('shutil.move',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError): db.delete_task('task_test',db_path=self.database)
        self.assertIsNotNone(db.get_task('task_test',self.database));self.assertTrue(p.exists())
    def test_cancel_then_claim_does_not_resurrect(self):
        self.add();db.transition_task('task_test','cancel',self.database)
        self.assertFalse(db.claim_task('task_test','profile',self.database))
        self.assertEqual(db.get_task('task_test',self.database).status,'cancelled')
    def test_claim_only_once(self):
        self.add();self.assertTrue(db.claim_task('task_test','profile',self.database));self.assertFalse(db.claim_task('task_test','profile',self.database))
    def test_retry_resets_times_preserves_binding(self):
        self.add(status='failed',assigned_profile_id='pinned',start_time='old',finish_time='old',retry_count=2)
        r=self.client.post('/api/tasks/task_test/retry');self.assertEqual(r.status_code,200)
        t=db.get_task('task_test',self.database);self.assertEqual(t.status,'queued');self.assertIsNone(t.start_time);self.assertIsNone(t.finish_time);self.assertEqual(t.assigned_profile_id,'pinned')
    def test_retry_unsupported_rejected(self):
        self.add(status='failed',error_code='WIRE_FORMAT_MISMATCH');self.assertEqual(self.client.post('/api/tasks/task_test/retry').status_code,409)
    def test_terminal_cancel_rejected(self):
        self.add(status='completed');self.assertEqual(self.client.post('/api/tasks/task_test/cancel').status_code,409)
    def test_task_id_traversal(self):
        for id in ('..','../outputs','x\\y','C:'):
            with self.assertRaises(db.TaskOperationConflict): db.delete_task(id,db_path=self.database)
    def test_spec_does_not_mutate_input(self):
        data={'project_name':'test','tracks':{'video':[{'id':'one','prompt':'x','duration':1}]}}
        before=json.dumps(data);TimelineSpec.from_job_spec(data);self.assertEqual(json.dumps(data),before)
    def test_pipeline_snapshots_and_bounded_history(self):
        m=pipeline.PipelineJobManager()
        for _ in range(120):
            id=m.create_job('test',{});m.complete_job(id,'out.mp4')
        self.assertLessEqual(len(m.list_jobs()),100)
        for _ in range(250):m.update_job(id,'test',1,'line')
        snapshot=m.get_job(id);self.assertEqual(len(snapshot['logs']),200);snapshot['params']['evil']=True
        self.assertNotIn('evil',m.get_job(id)['params'])
    def test_pipeline_queue_limit_without_real_render(self):
        class HoldExecutor:
            def __init__(self):self.callbacks=[]
            def submit(self,fn):self.callbacks.append(fn)
        hold=HoldExecutor();slots=threading.BoundedSemaphore(4);manager=pipeline.PipelineJobManager();spec=TimelineSpec(project_name='audit',tracks=TracksSpec(video_track=[ShotSpec(id='one')]))
        with patch.object(pipeline,'PIPELINE_EXECUTOR',hold),patch.object(pipeline,'PIPELINE_SLOTS',slots),patch.object(pipeline,'PIPELINE_MANAGER',manager):
            ids=[pipeline.start_timeline_pipeline_async(spec,self.root) for _ in range(4)]
            with self.assertRaises(pipeline.PipelineCapacityError):pipeline.start_timeline_pipeline_async(spec,self.root)
            self.assertTrue(all(manager.get_job(i)['status']=='queued' for i in ids))
            with patch.object(pipeline.TimelineEngine,'execute',return_value=self.root/'tiny.mp4'):
                for fn in hold.callbacks:fn()
            self.assertTrue(all(manager.get_job(i)['status']=='completed' for i in ids))
    def test_ffmpeg_command_thread_and_timeout_limits(self):
        with patch('video_farm.pipeline.subprocess.run') as run:
            pipeline._run_media_process(['ffmpeg','-y','-i','input.mp4','out.mp4'],capture_output=True)
            args,kw=run.call_args;self.assertIn('-filter_threads',args[0]);self.assertEqual(args[0][-3:],['-threads','2','out.mp4']);self.assertEqual(kw['timeout'],1200)
    def test_vids_filename_and_disk_zip(self):
        file=self.root/'clip.mp4';file.write_bytes(b'tiny test clip')
        wf={'id':'wf_audit','title':'审核 / 工程','shots':[{'id':'shot','sequence':1,'name':'测试镜头','local_video_path':str(file),'prompt':'x','narration':'你好'}]}
        self.assertEqual(vids_router.sanitize_filename_part('测试 / shot'),'测试_shot')
        with patch.object(db,'get_vids_workflow',return_value=wf),patch.object(vids_router,'DATA_ROOT',self.data):
            r=self.client.get('/api/vids/workflows/wf_audit/package_zip');self.assertEqual(r.status_code,200)
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                self.assertEqual(len([n for n in z.namelist() if n.startswith('videos/')]),1);self.assertIn('project_workflow.json',z.namelist());self.assertIsNone(z.testzip())
            self.assertEqual(list((self.data/'exports').glob('*.zip')),[])
    def test_restore_preview_apply_and_conflict(self):
        file=self.data/'outputs'/'audio.wav';file.parent.mkdir();file.write_bytes(b'original')
        self.add(status='completed',output_audio_path=str(file));db.log_task_event('task_test','done','x',self.database)
        result=db.delete_task('task_test',db_path=self.database);manifest=Path(result['trash_path'])/'manifest.json'
        self.assertFalse(maintenance.restore(manifest,self.database)['applied']);self.assertFalse(file.exists())
        self.assertTrue(maintenance.restore(manifest,self.database,True)['applied']);self.assertEqual(file.read_bytes(),b'original')
        self.assertEqual(db.get_task('task_test',self.database).status,'completed');self.assertTrue(db.list_task_events('task_test',self.database))
        with self.assertRaises(ValueError):maintenance.restore(manifest,self.database,True)
    def test_restore_does_not_restart_deleted_queue(self):
        self.add();r=db.delete_task('task_test',db_path=self.database)
        maintenance.restore(Path(r['trash_path'])/'manifest.json',self.database,True)
        self.assertEqual(db.get_task('task_test',self.database).status,'cancelled')
    def test_restore_refuses_overwrite_and_path_escape(self):
        file=self.data/'outputs'/'audio.wav';file.parent.mkdir();file.write_bytes(b'original')
        self.add(status='completed',output_audio_path=str(file));r=db.delete_task('task_test',db_path=self.database);manifest=Path(r['trash_path'])/'manifest.json'
        file.write_bytes(b'user new file')
        with self.assertRaises(ValueError):maintenance.restore(manifest,self.database,True)
        self.assertEqual(file.read_bytes(),b'user new file');file.unlink()
        data=json.loads(manifest.read_text(encoding='utf-8'));data['moved_files'][0]['source']=str(self.root/'outside.wav');manifest.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaises(ValueError):maintenance.restore(manifest,self.database,True)
        self.assertIsNone(db.get_task('task_test',self.database))
    def test_restore_move_failure_rolls_back(self):
        file=self.data/'outputs'/'audio.wav';file.parent.mkdir();file.write_bytes(b'original')
        self.add(status='completed',output_audio_path=str(file));r=db.delete_task('task_test',db_path=self.database)
        with patch('video_farm.maintenance.shutil.move',side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):maintenance.restore(Path(r['trash_path'])/'manifest.json',self.database,True)
        self.assertIsNone(db.get_task('task_test',self.database));self.assertFalse(file.exists())
    def test_pipeline_input_resource_and_path_limits(self):
        good=TimelineSpec(project_id='audit',tracks=TracksSpec(video_track=[ShotSpec(id='one')]))
        pipeline.validate_pipeline_spec(good)
        for updates in ({'resolution':[99999,99999]},{'fps':1000},{'project_id':'../escape'},{'output_master_path':str(self.database)}):
            candidate=good.model_copy(update=updates)
            with self.assertRaises(pipeline.PipelineInputError):pipeline.validate_pipeline_spec(candidate)
        bad=good.model_copy(deep=True);bad.tracks.video_track[0].id='../escape'
        with self.assertRaises(pipeline.PipelineInputError):pipeline.validate_pipeline_spec(bad)
        self.assertEqual(self.client.post('/api/pipeline/timeline/run',json=bad.model_dump()).status_code,422)
    def test_pipeline_duplicate_output_rejected(self):
        m=pipeline.PipelineJobManager();m.create_job('timeline',{'output_path':str(self.root/'same.mp4')})
        with self.assertRaises(pipeline.PipelineCapacityError):m.create_job('timeline',{'output_path':str(self.root/'same.mp4')})
    def test_vids_stream_upload_validation(self):
        folder=self.root/'vids_uploads';folder.mkdir()
        b=io.BytesIO();Image.new('RGB',(20,20),'blue').save(b,'PNG')
        with patch.object(vids_router,'UPLOADS_VIDS_DIR',folder):
            good=self.client.post('/api/vids/upload_asset',files={'file':('test.png',b.getvalue(),'image/png')});self.assertEqual(good.status_code,200)
            bad=self.client.post('/api/vids/upload_asset',files={'file':('test.png',b'not an image','image/png')});self.assertEqual(bad.status_code,400)
            self.assertEqual(len(list(folder.iterdir())),1)
            self.assertEqual(self.client.post('/api/vids/upload_asset',files={'file':('file.exe',b'x')}).status_code,400)

    def test_maintenance_rejects_non_list_image_metadata(self):
        for index, value in enumerate(('{}', 'null', '1', '"image.png"')):
            self.add(f'task_invalid_{index}', status='completed', output_image_paths=value)
        result=maintenance.inspect(self.database)
        invalid=[r for r in result['missing_completed_outputs'] if r.get('reason')=='invalid image list']
        self.assertEqual(len(invalid),4)
        self.assertEqual(result['integrity'],'ok')

if __name__=='__main__':unittest.main()
