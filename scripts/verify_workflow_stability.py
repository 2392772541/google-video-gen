import urllib.request
import json
import uuid
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = 'http://127.0.0.1:8088'

def run_verification():
    print('=== 1. 验证尾帧提取接口 ===')
    sample_mp4 = Path('video_farm_data/outputs/0e0c3bdd-0dce-4bc6-98b3-74cd7cc85363.mp4').resolve()
    assert sample_mp4.is_file(), f'Sample not found: {sample_mp4}'

    req_data = json.dumps({'video_url': str(sample_mp4)}).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/api/canvas/v1/video/extract-last-frame',
        data=req_data,
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode())
        print('Tail frame result:', res)
        assert res['ok'] is True
        assert 'frame_url' in res
        assert res['width'] > 0 and res['height'] > 0

    print('=== 2. 验证提示词去噪去污染接口 (POST /videos) ===')
    boundary = '----WebKitFormBoundary' + uuid.uuid4().hex[:16]
    dirty_prompt = '''图片1、图片2、【文本1】\n\n【文本1】\n【镜头 08 首尾过渡指令｜00:47–00:54｜7 秒】晨曦穿越古老密林，光束倾泻在林间溪流上\n\n晨曦穿越古老密林，光束倾泻在林间溪流上'''

    body_parts = []
    def add_field(name, val):
        body_parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n'.encode('utf-8'))

    req_id = f'req_test_{uuid.uuid4().hex[:8]}'
    add_field('request_id', req_id)
    add_field('prompt', dirty_prompt)
    add_field('model', 'flow::veo-lite')
    add_field('seconds', '6')
    add_field('project_id', 'proj_stab_001')
    add_field('shot_id', 'shot_08')

    png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00 \x00\x00\x00 \x08\x02\x00\x00\x00\xfc\x18\xed\xa3\x00\x00\x00\x19IDATx\x9cc\xf8\xff\xff?\x03\x05\x00\x07\xfe\x02\xfe\xa7T\xb7\x18\x00\x00\x00\x00IEND\xaeB`\x82'
    file_header = f'--{boundary}\r\nContent-Disposition: form-data; name=\"first_frame\"; filename=\"start.png\"\r\nContent-Type: image/png\r\n\r\n'.encode('utf-8')
    body_parts.append(file_header + png_bytes + b'\r\n')
    body_parts.append(f'--{boundary}--\r\n'.encode('utf-8'))

    payload = b''.join(body_parts)

    video_req = urllib.request.Request(
        f'{BASE}/videos',
        data=payload,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    with urllib.request.urlopen(video_req, timeout=10) as resp:
        create_res = json.loads(resp.read().decode())
        print('Create video task response:', create_res)
        task_id = create_res['id']
        assert task_id.startswith('task_')

    from video_farm import db
    t_obj = db.get_task(task_id, Path('video_farm_data/tasks.db'))
    assert t_obj is not None
    print('Sanitized task prompt in DB:', repr(t_obj.prompt))
    assert '【文本1】' not in t_obj.prompt
    assert '图片1' not in t_obj.prompt
    assert '图片2' not in t_obj.prompt
    assert '晨曦穿越古老密林，光束倾泻在林间溪流上' in t_obj.prompt
    assert t_obj.prompt.count('晨曦穿越古老密林') == 1

    print('=== 3. 验证复合幂等性拦截 (防重复扣费提交) ===')
    video_req2 = urllib.request.Request(
        f'{BASE}/videos',
        data=payload,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'}
    )
    with urllib.request.urlopen(video_req2, timeout=10) as resp2:
        create_res2 = json.loads(resp2.read().decode())
        print('Idempotent second request response:', create_res2)
        assert create_res2['id'] == task_id
        assert create_res2.get('reused') is True

    print('=== 4. 验证细粒度任务阶段反馈 (GET /videos/{task_id}) ===')
    with urllib.request.urlopen(f'{BASE}/videos/{task_id}', timeout=5) as resp3:
        status_res = json.loads(resp3.read().decode())
        print('Task status query response:', status_res)
        assert 'stage' in status_res
        assert 'stage_text' in status_res
        assert status_res['status'] in ('pending', 'queued', 'running', 'completed', 'needs_reconciliation')

    print('\nALL 4 WORKFLOW STABILITY CRITICAL CHECKS PASSED!')

if __name__ == '__main__':
    run_verification()
