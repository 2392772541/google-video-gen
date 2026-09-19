import urllib.request, urllib.parse, json, os

tasks_to_submit = {
    '01': {
        'title': '添添向上 98%DMPP原粉 (1kg)',
        'img': 'video_farm_data/uploads/scenes/prod_01_first_frame.png',
        'prompt': 'Commercial advertising shot, slow cinematic macro dolly push-in toward the package on the glowing marble circular pedestal, wheat field swaying gently in the background breeze under golden morning sun, subtle lens flare and dust motes, 4k ultra realistic, high-end product commercial.'
    },
    '02': {
        'title': '添添向上 纳铠甲 80% DMP-X (1kg)',
        'img': 'video_farm_data/uploads/scenes/prod_02_first_frame.png',
        'prompt': 'High-end tech commercial showcase, slow cinematic camera orbit around the package resting on the faceted crystal glass pedestal, glowing cyan and blue nano particles floating gently in the air, refraction of light through the crystal base, 4k 60fps luxury aesthetic.'
    },
    '03': {
        'title': '添添向上 捷邦 50% DMPX油剂 (5L)',
        'img': 'video_farm_data/uploads/scenes/prod_03_first_frame.png',
        'prompt': 'Cinematic corporate product reveal, smooth slow forward tracking camera movement toward the container on the industrial steel pedestal, modern agricultural bio-lab environment, subtle reflections on metal surface, clean soft studio lighting, professional commercial video.'
    },
    '04': {
        'title': '添添向上 90%氨基寡糖素粉剂 (1kg)',
        'img': 'video_farm_data/uploads/scenes/prod_04_first_frame.png',
        'prompt': 'Luxury brand advertising shot, cinematic low-angle slow push-in toward the product bag on the polished dark green marble pedestal, golden sparkles and light particles drifting softly downwards in the dramatic spotlight, elegant moody lighting, 4k ultra high definition.'
    },
    '06': {
        'title': '添添向上 90%褐藻寡糖粉剂 (1kg)',
        'img': 'video_farm_data/uploads/scenes/prod_06_first_frame.png',
        'prompt': 'Epic cinematic commercial shot, slow dramatic push-in on the product package standing on wet volcanic basalt rock, gentle ocean spray and sea mist rolling across the surface, ethereal teal god rays cutting through sea mist, photorealistic 8k commercial aesthetic.'
    },
    '07': {
        'title': '添添向上 30%褐藻寡糖液剂 (1L)',
        'img': 'video_farm_data/uploads/scenes/prod_07_first_frame.png',
        'prompt': 'Zen luxury commercial shot, slow cinematic pan and push-in toward the bottle on the floating obsidian disc, concentric water ripples expanding slowly across the glassy lake, morning golden hour backlight on water lilies, tranquil and pristine, 4k advertising film.'
    },
    '08': {
        'title': '基因产物超免蛋白 (1000g)',
        'img': 'video_farm_data/uploads/scenes/prod_08_first_frame.png',
        'prompt': 'Futuristic biotech commercial, slow robotic camera arc movement around the package on the illuminated glass pedestal, gentle blue and purple ambient glow, blurred holographic data and laboratory glassware in background, sleek high-tech corporate showcase, 4k.'
    },
    '09': {
        'title': '福联生物 土壤疏松调理剂 (25kg)',
        'img': 'video_farm_data/uploads/scenes/prod_09_first_frame.png',
        'prompt': 'Cinematic agricultural documentary commercial, slow smooth crane-down and push-in toward the kraft paper sack on the weathered timber platform, golden sunrise over lush green corn fields and fertile soil, gentle morning breeze, warm cinematic atmosphere.'
    },
    'kui': {
        'title': '添添向上 块茎王 (1000g)',
        'img': 'video_farm_data/uploads/scenes/prod_kui_first_frame.png',
        'prompt': 'Warm harvest commercial advertisement, slow cinematic dolly-in on the product package on the rustic tree trunk pedestal, golden wheat ears swaying in late afternoon sunset light, warm dust motes floating in backlight, rich fertile earth and harvested crops, 4k film quality.'
    },
}

all_records = {
    '05': {
        'title': '添添向上 10%氨基寡糖素液剂 (1L)',
        'task_id': 'task_f0b2f4bf9473',
        'img': 'video_farm_data/uploads/scenes/prod_05_first_frame.png',
        'prompt': 'Breathtaking commercial product showcase, slow macro camera glide over the rippling water towards the bottle on the marble column, soft morning sunlight filtering through greenhouse glass, lush orchids and green foliage softly swaying, serene morning mist, 4k cinematic video.',
        'video_path': 'C:/Users/win10/Documents/ChatGPT/视频制作/video_farm_data/outputs/15ecbd05-29ab-4bf9-a5bb-dce8650b90c1.mp4',
        'status': 'completed'
    }
}

api_url = 'http://127.0.0.1:8088/api/tasks/create'

for k, item in tasks_to_submit.items():
    data = urllib.parse.urlencode({
        'prompt': item['prompt'],
        'engine': 'flow',
        'model': 'veo-lite',
        'start_image_path': os.path.abspath(item['img']),
        'aspect_ratio': '16:9',
        'duration_sec': 8,
        'priority': 10
    }).encode('utf-8')
    req = urllib.request.Request(api_url, data=data, method='POST')
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        tid = res['id']
        item['task_id'] = tid
        item['status'] = res['status']
        all_records[k] = item
        print(f'[{k}] Submitted -> Task ID: {tid}')

with open('video_farm_data/submitted_10_videos.json', 'w', encoding='utf-8') as f:
    json.dump(all_records, f, ensure_ascii=False, indent=2)

print('All 9 remaining tasks submitted successfully!')
