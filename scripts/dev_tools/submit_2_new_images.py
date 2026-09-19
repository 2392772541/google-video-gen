import urllib.request, urllib.parse, json

tasks = [
    {
        'key': '11_促保利素',
        'ref': r'E:\公司素材\产品实景图\最新定稿图\福联\促保利素\促保利素.png',
        'prompt': 'A high-end cinematic commercial product advertising photo of this agricultural photosynthesis catalyst fertilizer pouch standing on a sleek warm amber stone circular pedestal, in the center of a sunlit lush green wheat field during golden morning sunrise, dramatic golden solar rays and lens flare cutting through the air, glowing golden photosynthetic energy particles floating softly around, ultra realistic commercial look, 8k'
    },
    {
        'key': '12_优根优苗',
        'ref': r'E:\公司素材\产品实景图\最新定稿图\福联\优根优苗\优根优苗__copy.png',
        'prompt': 'A premium commercial product photograph of this root stimulant fertilizer pouch on a clean modern dark stone pedestal, surrounded by vibrant healthy green sprout seedlings with dense white root systems visible in transparent glass, soft emerald greenhouse ambient lighting and gentle water mist, clean high-tech agricultural science showcase, 8k'
    }
]

submitted = {}
for t in tasks:
    data = urllib.parse.urlencode({
        'prompt': t['prompt'],
        'model': 'nano2',
        'aspect_ratio': '16:9',
        'ref_image_path': t['ref'],
        'priority': '10'
    }).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8088/api/tasks/create-image', data=data, method='POST')
    with urllib.request.urlopen(req) as res:
        resp = json.loads(res.read().decode('utf-8'))
        submitted[t['key']] = {
            'task_id': resp['id'],
            'ref': t['ref'],
            'prompt': t['prompt']
        }
        print(f"Submitted [{t['key']}]: {resp['id']}")

with open('video_farm_data/submitted_2_images.json', 'w', encoding='utf-8') as f:
    json.dump(submitted, f, ensure_ascii=False, indent=2)

print('Both image tasks submitted successfully!')
