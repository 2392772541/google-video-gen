import urllib.request, urllib.parse, json

tasks = [
    {
        'key': '07',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/07_30%褐藻寡糖液剂.png',
        'prompt': 'A luxury commercial product advertisement photo of this liquid fertilizer bottle on a sleek black granite circular podium in the center of a calm reflective water pool with gentle ripples, soft morning sunlight, lush green water garden background, cinematic commercial lighting, 8k'
    },
    {
        'key': '08',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/08_基因产物超免蛋白_效果图.png',
        'prompt': 'A futuristic high-tech commercial advertising photo of this biotechnology protein fertilizer pouch on a sleek frosted dark glass and titanium pedestal, soft purple and gold ambient studio lighting, blurred modern biotechnology laboratory background, ultra clean commercial aesthetic, 8k'
    },
    {
        'key': 'kui',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/69088909-1db8-4fac-92aa-fa362732683b.png',
        'prompt': 'A warm cinematic commercial advertising photo of this tuber yield enhancer fertilizer pouch standing on a natural rustic dark wood pedestal, surrounded by rich fertile soil and golden wheat heads, warm sunset golden hour lighting, cinematic agricultural commercial film, 8k'
    },
    {
        'key': '02',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/02_纳铠甲80%DMP-X.png',
        'prompt': 'A high-tech cinematic commercial photo of this nano-encapsulated fertilizer pouch on a modern geometric hexagonal crystal glass pedestal, subtle icy blue and emerald green ambient glow, floating microscopic crystal particles, premium agricultural science showcase, 8k'
    },
    {
        'key': '03',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/03_捷邦50%DMPX油剂.png',
        'prompt': 'A powerful commercial product photograph of this 5L heavy-duty agricultural jug on a solid brushed metallic and concrete pedestal, cinematic modern agricultural engineering laboratory background, clean professional studio lighting, 8k'
    },
    {
        'key': '01',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/01_98%DMPP原粉.png',
        'prompt': 'A minimalist modern commercial photo of this pure chemical nitrogen inhibitor fertilizer pouch on a clean white circular marble podium with subtle blue rim lighting, softly blurred green field and sky in background, bright crisp advertising lighting, 8k'
    },
    {
        'key': '09',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/09_土壤疏松调理剂_效果图.png',
        'prompt': 'A grand cinematic agricultural commercial photo of this 25kg kraft paper fertilizer sack standing on a solid natural timber platform in the middle of vast fertile farmland at sunrise, soft golden morning light, rolling green crops in background, epic cinematic commercial look, 8k'
    },
    {
        'key': '04',
        'ref': 'E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/04_90%氨基寡糖素粉剂.png',
        'prompt': 'A high-end luxury dark-themed commercial photo of this organic oligosaccharide fertilizer pouch on a dark emerald marble cylindrical pedestal, single dramatic spotlight from above creating soft warm shadows, elegant golden bokeh particles in dark background, 8k'
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

with open('video_farm_data/submitted_images.json', 'w', encoding='utf-8') as f:
    json.dump(submitted, f, ensure_ascii=False, indent=2)

print('All 8 image tasks submitted successfully!')
