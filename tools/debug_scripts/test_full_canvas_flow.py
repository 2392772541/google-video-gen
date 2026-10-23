import urllib.request, json, base64, subprocess
from pathlib import Path

qa_dir = Path('C:/Users/win10/Documents/ChatGPT/视频制作/video_farm_data/qa')
qa_dir.mkdir(parents=True, exist_ok=True)
img_file = qa_dir / 'test_suite_cat.png'

print('Step 1: Testing Image Generation via 8088 adapter...')
req = urllib.request.Request(
    'http://127.0.0.1:8088/v1/images/generations',
    data=json.dumps({
        'model': 'gpt-image-1.5',
        'prompt': '一只赛博朋克风格的机械小猫在未来科技城市雨夜中闪烁奔跑，高精度CG写实，电影光影',
        'n': 1,
        'response_format': 'b64_json'
    }).encode(),
    headers={'Content-Type': 'application/json'}
)

with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode())
    b64 = data['data'][0]['b64_json']
    img_bytes = base64.b64decode(b64)
    with open(img_file, 'wb') as f:
        f.write(img_bytes)
    print(f'Image generated successfully! Saved to {img_file} (bytes: {len(img_bytes)})')

print('Step 2: Testing Flow Image-to-Video Task Submission...')
flow_cmd = [
    'curl.exe', '-s', '-X', 'POST', 'http://127.0.0.1:8088/v1/videos',
    '-F', 'model=video-farm-8088::flow',
    '-F', 'prompt=赛博机械小猫向前奔跑，电影级动态跟随摄影，霓虹倒影飞速掠过',
    '-F', 'seconds=6',
    '-F', 'size=1280x720',
    '-F', 'ratio=16:9',
    '-F', f'first_frame=@{img_file.resolve()}'
]
res_flow = subprocess.check_output(flow_cmd).decode()
flow_task = json.loads(res_flow)
print('Flow Task:', flow_task)

print('Step 3: Testing Vids Start-Frame Video Task Submission...')
vids_cmd = [
    'curl.exe', '-s', '-X', 'POST', 'http://127.0.0.1:8088/v1/videos',
    '-F', 'model=video-farm-8088::vids',
    '-F', 'prompt=未来科技城市全景运镜，雨夜霓虹街道视角延展',
    '-F', 'seconds=5',
    '-F', 'size=1280x720',
    '-F', f'first_frame=@{img_file.resolve()}'
]
res_vids = subprocess.check_output(vids_cmd).decode()
vids_task = json.loads(res_vids)
print('Vids Task:', vids_task)

print('Step 4: Querying Task Status...')
flow_id = flow_task['id']
with urllib.request.urlopen(f'http://127.0.0.1:8088/v1/videos/{flow_id}') as resp:
    print('Flow Status:', json.loads(resp.read().decode()))

vids_id = vids_task['id']
with urllib.request.urlopen(f'http://127.0.0.1:8088/v1/videos/{vids_id}') as resp:
    print('Vids Status:', json.loads(resp.read().decode()))
