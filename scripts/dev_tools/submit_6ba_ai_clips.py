import sys
sys.path.append('C:/Users/win10/.codex/skills/google-video-gen/scripts')
import api_client
from pathlib import Path

prompts = {
    'Section_A': (
        'A1_1080p.png',
        '16:9 cinematic agricultural documentary. A glowing 6-BA ball-and-stick molecule floats stably between two natural fresh fruits in bright warm daylight studio, smooth slow camera push in, professional macro cinematography, clean natural light, highly detailed.'
    ),
    'Section_B': (
        'B1_1080p.png',
        '16:9 bright scientific documentary of plant cell. Extreme close-up of 6-BA molecule approaching cytokinin receptor on the translucent green cell membrane, warm golden phosphate signal pulse appears, clean scientific visualization, smooth macro tracking, cinematic lighting.'
    ),
    'Section_C': (
        'C1_1080p.png',
        '16:9 high-end agricultural technology documentary. Smooth tracking shot across fresh flower buds, young green shoots and vibrant leaves in soft natural sunlight, professional agriculture research, crisp focus, cinematic depth of field.'
    )
}

print('[*] Submitting 3 AI video tasks to Video Farm...')
for sec, (img_name, prompt) in prompts.items():
    img_path = str(Path('temp_crops_16x9') / img_name)
    res = api_client.submit_video_task(
        prompt=prompt,
        start_frame=img_path,
        aspect='16:9',
        duration=8,
        model='veo-lite',
        priority=10
    )
    tid = res.get('id') if res else 'None'
    st = res.get('status') if res else 'Error'
    print(f'Submitted {sec}: task_id={tid} status={st}')
