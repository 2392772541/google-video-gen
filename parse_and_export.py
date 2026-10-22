import re
import json
import os

with open(r'C:\Users\win10\Downloads\超免蛋白_首尾帧脚本\storyboard.md', encoding='utf-8') as f:
    text = f.read()

# 1. 提取运动描述
motion_prompts = {}
motion_pattern = re.compile(r'\*\*镜(\d+)\*\*.*?-->?.*?\n\n>\s*(.*?)\n', re.DOTALL)
# 也可以更宽容地提取
for block in text.split('**镜')[1:]:
    shot_num = block[:2]
    # 找第一个引用块
    m = re.search(r'>\s*([^\n]+)', block)
    if m:
        motion_prompts[shot_num] = m.group(1).strip()

print('Motion prompts extracted:', list(motion_prompts.keys()))

# 2. 提取表格行
# | 01 | 0–10s | 对应文案 | ...
table_rows = {}
for line in text.splitlines():
    if line.strip().startswith('|') and re.match(r'\|\s*\d{2}\s*\|', line.strip()):
        parts = [p.strip() for p in line.strip().split('|')[1:-1]]
        shot_id = parts[0]
        # 去掉文案末尾的字数统计，如（58字）
        narration_raw = parts[2]
        narration = re.sub(r'（\d+字）$', '', narration_raw).strip()
        table_rows[shot_id] = {
            'time': parts[1],
            'narration': narration,
            'motion_table': parts[5]
        }

print('Table rows extracted:', list(table_rows.keys()))

shot_names = {
    '01': '镜头01·产品悬念',
    '02': '镜头02·颠覆逻辑',
    '03': '镜头03·路线对比',
    '04': '镜头04·源起梨火疫',
    '05': '镜头05·国际认可',
    '06': '镜头06·植物疫苗',
    '07': '镜头07·分子机理',
    '08': '镜头08·协同增产',
    '09': '镜头09·防效与叶喷',
    '10': '镜头10·滴灌混配'
}

base_img_dir = 'E:/IDM下载/压缩/超免蛋白_首尾帧素材包_1080x1920/超免蛋白_首尾帧素材包_20261016'

frame_map = {
    '01': ('F01_start.png', 'F01_end.png'),
    '02': ('F02_start.png', 'F02_end.png'),
    '03': ('F03_start.png', 'F03_end.png'),
    '04': ('F04_start.png', 'F04_end.png'),
    '05': ('F05_start.png', 'F05_end.png'),
    '06': ('F05_end.png', 'F06_end.png'),
    '07': ('F07_start.png', 'F07_end.png'),
    '08': ('F07_end.png', 'F08_end.png'),
    '09': ('F09_start.png', 'F09_end.png'),
    '10': ('F09_end.png', 'F10_end.png'),
}

result = []
for i in range(1, 11):
    sid = f'{i:02d}'
    start_f, end_f = frame_map[sid]
    motion = motion_prompts.get(sid, table_rows[sid]['motion_table'])
    # 清理并精炼 prompt
    # 替换写实/扁平风格字样为清晰描述，加上 9:16 竖屏，1080p高质量
    clean_motion = motion.replace('写实/扁平风格保持一致，', '')
    prompt = f'镜头{sid}: 9:16竖屏，{clean_motion}，1080p高质量'
    
    shot_obj = {
        'name': shot_names[sid],
        'mode': 'first_last_frame',
        'aspect_ratio': '9:16',
        'image_url': f'{base_img_dir}/{start_f}',
        'end_image_url': f'{base_img_dir}/{end_f}',
        'prompt': prompt,
        'narration': table_rows[sid]['narration'],
        'duration': 10,
        'resolution': '1080p',
        'model_name': 'Omni'
    }
    result.append(shot_obj)

# 验证存在
for s in result:
    assert os.path.exists(s['image_url']), f'Missing {s[\ image_url\]}'
    assert os.path.exists(s['end_image_url']), f'Missing {s[\end_image_url\]}'

out_path_1 = os.path.join(base_img_dir, '超免蛋白_9x16_首尾帧分镜.json')
out_path_2 = 'C:/Users/win10/Downloads/超免蛋白_首尾帧脚本/超免蛋白_9x16_首尾帧分镜.json'

with open(out_path_1, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

with open(out_path_2, 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print('Successfully parsed and generated JSON!')
