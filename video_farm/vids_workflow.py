# -*- coding: utf-8 -*-
"""
Google Vids Workflow & Continuous Multi-Shot Generation Engine
"""
from __future__ import annotations
import re
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from . import db

PRESETS: Dict[str, Dict[str, Any]] = {
    "cyberpunk": {
        "id": "cyberpunk",
        "name": "赛博朋克科幻巨制",
        "description": "霓虹高楼、穿梭飞行器、全息数据、冷峻光影的未来都市科幻大片风格",
        "aspect_ratio": "16:9",
        "duration_per_shot": 10,
        "style_prompt": "Cinematic 8k, Unreal Engine 5 render, cyberpunk neon aesthetic, volumetric lighting, photorealistic, octane render, vivid colors, highly detailed",
        "sample_shots": [
            {
                "name": "镜头 1 · 霓虹天际线与飞行穿梭",
                "prompt": "Sweeping aerial drone shot gliding over a futuristic cyberpunk megalopolis at night, towering neon skyscrapers with glowing holographic billboards, flying transport vehicles smoothly cruising between high-rise sky bridges, reflections on rain-slicked surfaces, cinematic 8k.",
                "narration": "公元2088年，新天际城的夜幕降临，高悬的全息巨幕点亮了沉睡的钢铁森林。",
                "duration": 10
            },
            {
                "name": "镜头 2 · 赛博漫步与暗巷光影",
                "prompt": "Low-angle medium tracking shot of a mysterious figure in a dark cybernetic trench coat with glowing cyan lines walking through a crowded neon-lit alleyway in Neo-Tokyo, steam rising from underground grates, vivid neon reflections, cinematic depth of field.",
                "narration": "在这座由数据与记忆编织的迷宫中，每个人都在寻找丢失的真实。",
                "duration": 10
            },
            {
                "name": "镜头 3 · 量子机房与全息核心",
                "prompt": "Cinematic interior camera dolly inside an advanced quantum computing laboratory, massive transparent holographic spheres pulsing with golden and blue data particles, sleek server towers humming with energy, cinematic lighting.",
                "narration": "直到最底层的核心矩阵被唤醒，城市的心跳骤然加速。",
                "duration": 10
            }
        ]
    },
    "nature_epic": {
        "id": "nature_epic",
        "name": "国家地理大美自然纪录片",
        "description": "航拍雪山、金光云海、雄鹰展翅、原生生灵的史诗级自然纪录片画质",
        "aspect_ratio": "16:9",
        "duration_per_shot": 10,
        "style_prompt": "National Geographic 8k documentary style, photorealistic wildlife and nature, natural golden hour sunlight, RED digital cinema camera, 120fps slow motion, ultra sharp detail",
        "sample_shots": [
            {
                "name": "镜头 1 · 晨曦雪山云海漫卷",
                "prompt": "Sweeping aerial drone shot of majestic snow-capped Himalayan mountain peaks bathed in golden sunrise light, clouds rolling softly through deep glacier valleys, crystal clear 8k resolution, cinematic.",
                "narration": "第一缕晨曦刺破群峰的苍茫，唤醒了高原万载的静默。",
                "duration": 10
            },
            {
                "name": "镜头 2 · 苍鹰破空巡视高原",
                "prompt": "Dynamic telephoto tracking shot of a golden eagle soaring with outstretched wings above emerald alpine forests and sparkling crystal rivers, morning mist swirling below, cinematic 8k.",
                "narration": "双翼掠过风的脊背，它是这片旷野最敏锐的守望者。",
                "duration": 10
            },
            {
                "name": "镜头 3 · 暮光冰湖水天一色",
                "prompt": "Wide slow pan across a tranquil glacial lake reflecting the vibrant purple and orange sunset sky, gentle ripples on mirror water, towering pine trees along the rocky shoreline, cinematic.",
                "narration": "黄昏沉入澄澈的湖泊，将万物的倒影凝固在时间的长河里。",
                "duration": 10
            }
        ]
    },
    "oriental_myth": {
        "id": "oriental_myth",
        "name": "东方仙侠与国风神话",
        "description": "浮空仙岛、御剑凌霄、祥云缭绕、青绿山水的东方玄幻东方意境",
        "aspect_ratio": "16:9",
        "duration_per_shot": 10,
        "style_prompt": "Chinese traditional aesthetic, xianxia fantasy cinema, misty ethereal mountains, flowing silk garments, poetic lighting, 8k cinematic masterpiece, divine celestial glow",
        "sample_shots": [
            {
                "name": "镜头 1 · 浮空仙阁与云瀑倾泻",
                "prompt": "Wide panoramic shot of floating celestial mountains shrouded in ethereal swirling white mist, ancient taoist pavilions perched on cliff edges, waterfalls cascading into endless sea of clouds, 8k.",
                "narration": "九霄之上，仙山浮沉于云海之间，飞瀑垂落三千尺。",
                "duration": 10
            },
            {
                "name": "镜头 2 · 踏剑御风穿梭峰峦",
                "prompt": "Cinematic tracking shot of an immortal swordsman in flowing white and cyan robes gliding serenely through mountain peaks on a glowing jade sword, cherry blossom petals drifting in the wind, soft golden sunrise.",
                "narration": "青锋一鞘凌霄去，踏碎人间万重关。",
                "duration": 10
            },
            {
                "name": "镜头 3 · 天门浩荡万丈霞光",
                "prompt": "Grand majestic crane shot revealing a colossal heavenly palace with golden glazed roof tiles floating amidst rainbow clouds, divine beams of light radiating through ancient pine trees, cinematic epic scale.",
                "narration": "天门洞开处，万千祥瑞映照出不朽的东方仙境。",
                "duration": 10
            }
        ]
    },
    "tech_product": {
        "id": "tech_product",
        "name": "高端极简科技产品大片",
        "description": "微距光影、金属与磨砂质感、极简棚拍、Apple 级工业美学",
        "aspect_ratio": "16:9",
        "duration_per_shot": 10,
        "style_prompt": "Apple style studio product photography, clean minimalist aesthetic, dramatic rim lighting, macro focus, pristine glass and titanium materials, 8k commercial quality",
        "sample_shots": [
            {
                "name": "镜头 1 · 钛金属流光微距",
                "prompt": "Extreme macro studio shot slowly panning across the precision CNC machined titanium edge of a sleek futuristic device, subtle laser engraving reflecting specular highlights, pure dark studio background.",
                "narration": "每一微米的精密雕琢，只为呈现触手可及的未来质感。",
                "duration": 10
            },
            {
                "name": "镜头 2 · 悬浮光影与镜面晶体",
                "prompt": "Clean hero product shot of the device floating weightlessly against a smooth gradient backdrop, gentle 360 degree rotation showing the ultra-thin profile and seamless curved glass display.",
                "narration": "轻薄与性能的极致平衡，在无界视野中重塑感知。",
                "duration": 10
            }
        ]
    },
    "vertical_story": {
        "id": "vertical_story",
        "name": "9:16 竖屏短剧与高能短视频",
        "description": "竖屏构图、强视觉冲击、快节奏人物与场景转换，适配抖音/Reels/Shorts",
        "aspect_ratio": "9:16",
        "duration_per_shot": 10,
        "style_prompt": "Vertical 9:16 format, cinematic smartphone film, dynamic movement, vibrant color grading, high engagement visual hook, ultra detailed 4k",
        "sample_shots": [
            {
                "name": "镜头 1 · 逆光回眸视觉焦点",
                "prompt": "Vertical 9:16 portrait shot, dynamic gimbal push-in towards a charismatic protagonist standing at a rainy street corner, neon umbrella, intense emotional gaze into camera, cinematic lighting.",
                "narration": "在这个所有人都在向前跑的时代，她忽然停下了脚步。",
                "duration": 10
            },
            {
                "name": "镜头 2 · 破茧启程高能转场",
                "prompt": "Vertical 9:16 dynamic tracking shot following the protagonist stepping into a brightly lit modern glass elevator shooting upwards through city skyline at dusk, fast motion blur, cinematic.",
                "narration": "这一次，她决定按照自己的规则重新开始。",
                "duration": 10
            }
        ]
    }
}

def parse_script_to_shots(raw_text: str, default_duration: int = 10, style_preset: str = "") -> List[Dict[str, Any]]:
    """
    将用户输入的剧本文案智能拆分为多个结构化分镜卡片
    """
    lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
    if not lines:
        return []

    # 尝试按镜头标识、数字序号、或空行段落切分
    shot_blocks: List[str] = []
    current_block: List[str] = []

    pattern = re.compile(r"^(?:镜头|分镜|shot|scene|第[0-9一二三四五六七八九十]+[幕场镜]|(?:[0-9]{1,2}[、.：:\s]))", re.IGNORECASE)

    for line in lines:
        if pattern.match(line) and current_block:
            shot_blocks.append("\n".join(current_block))
            current_block = [line]
        else:
            current_block.append(line)
    if current_block:
        shot_blocks.append("\n".join(current_block))

    # 如果无法按标记切分，且只有一段很长的话，按句号或段落均分为3-4个镜头
    if len(shot_blocks) == 1:
        text = shot_blocks[0]
        sentences = [s.strip() for s in re.split(r"[。！？!?\n]+", text) if s.strip()]
        if len(sentences) >= 3:
            shot_blocks = []
            chunk_size = max(1, len(sentences) // 3)
            for i in range(0, len(sentences), chunk_size):
                shot_blocks.append("。".join(sentences[i:i+chunk_size]) + "。")

    results: List[Dict[str, Any]] = []
    for idx, block in enumerate(shot_blocks, start=1):
        block_clean = re.sub(r"^(?:镜头|分镜|shot|scene|第[0-9一二三四五六七八九十]+[幕场镜]|(?:[0-9]{1,2}[、.：:\s]))+[:：\s]*", "", block, flags=re.IGNORECASE).strip()
        
        # 提取提示词与旁白
        # 如果包含英文和中文混排，智能分离
        has_english = bool(re.search(r"[a-zA-Z]{4,}", block_clean))
        
        if has_english and not re.search(r"[一-龥]", block_clean):
            # 纯英文提示词
            prompt = block_clean
            narration = f"分镜 {idx} 画面生成"
            name = f"Shot {idx}"
        else:
            # 包含中文，生成高质量英文视频提示词
            narration = block_clean
            name = f"分镜 {idx} · " + (narration[:12] + ("..." if len(narration) > 12 else ""))
            # 智能映射关键词
            prompt = _enhance_chinese_to_vids_prompt(narration, idx)

        results.append({
            "sequence": idx,
            "scene_index": idx,
            "name": name,
            "prompt": prompt,
            "narration": narration,
            "duration": default_duration
        })

    return results

def _enhance_chinese_to_vids_prompt(cn_text: str, idx: int) -> str:
    """
    将中文分镜描述增强为符合 Google Vids / Veo 视频生成引擎偏好的英文提示词
    """
    keywords_map = [
        ("雪山", "majestic snow-capped mountain peaks bathed in golden sunlight"),
        ("山", "dramatic mountain landscape, misty peaks"),
        ("海", "vast ocean waves with turquoise water splashing against coastal cliffs"),
        ("湖", "tranquil crystal clear lake reflecting sky"),
        ("森林", "lush green pine forest with morning sun rays filtering through mist"),
        ("城市", "sweeping panoramic view of a bustling modern metropolis"),
        ("夜景", "vibrant night cityscape with glowing lights and reflections"),
        ("赛博", "futuristic cyberpunk city with neon holograms and flying cars"),
        ("霓虹", "neon lighting, glowing holographic billboards"),
        ("鸟", "wild bird soaring gracefully in sky, cinematic 8k"),
        ("鹰", "majestic eagle soaring over peaks, ultra detailed feathers"),
        ("人", "cinematic character in thoughtful expression"),
        ("走", "tracking shot of character walking with determination"),
        ("跑", "dynamic high speed camera following movement"),
        ("科技", "sleek futuristic technology laboratory with quantum holographic interfaces"),
        ("古风", "traditional ancient oriental palace, ethereal misty mountains, flowing silk"),
        ("仙侠", "xianxia fantasy, floating celestial islands, glowing ethereal sword"),
        ("星空", "breathtaking galaxy night sky with swirling stars and nebulae"),
        ("雨", "cinematic raindrops falling on city pavement, neon reflections"),
        ("夕阳", "spectacular golden hour sunset with rich orange and violet hues"),
        ("日出", "dramatic sunrise with golden light breaking through clouds"),
    ]

    matched_en: List[str] = []
    for cn, en in keywords_map:
        if cn in cn_text:
            matched_en.append(en)

    angles = [
        "Cinematic sweeping camera shot",
        "Dramatic medium tracking shot",
        "Wide majestic panoramic view",
        "Dynamic low-angle camera glide",
        "Intimate shallow depth-of-field close-up"
    ]
    angle = angles[(idx - 1) % len(angles)]

    if matched_en:
        core_visual = ", ".join(matched_en)
    else:
        core_visual = "visually stunning scene with rich cinematic composition, natural depth and movement"

    return f"{angle} of {core_visual}, cinematic 8k, photorealistic lighting, Unreal Engine 5 render, award winning cinematography."


SAMPLE_BATCH_IMPORT_DATA = {
    'title': '电影级多模态镜头资产包 (1080p)',
    'doc_url': '',
    'style_prompt': 'Cinematic 8k, photorealistic lighting, Unreal Engine 5 render, anamorphic lens, highly detailed masterpiece',
    'aspect_ratio': '16:9',
    'resolution': '1080p',
    'model_name': 'Omni',
    'duration_per_shot': 10,
    'shots': [
        {
            'name': '镜头 1 · 晨曦雪山起飞 (首帧参考图)',
            'mode': 'image2video',
            'image_url': 'video_farm_data/uploads/scenes/prod_01_first_frame.png',
            'end_image_url': '',
            'prompt': 'Dynamic cinematic camera pushing forward over majestic snow-capped peaks in golden morning sunrise light, clouds rolling softly through alpine valleys, 8k resolution, photorealistic.',
            'narration': '朝阳穿透重云，第一缕晨光洒在巍峨的雪山之巅。',
            'resolution': '1080p',
            'model_name': 'Omni',
            'duration': 10
        },
        {
            'name': '镜头 2 · 苍鹰掠过峡谷 (首尾帧平滑过渡)',
            'mode': 'first_last_frame',
            'image_url': 'video_farm_data/uploads/scenes/prod_01_first_frame.png',
            'end_image_url': 'video_farm_data/uploads/scenes/prod_02_first_frame.png',
            'prompt': 'Smooth cinematic aerial transition from snow mountain peaks down to emerald green pine valley, golden eagle soaring gracefully across the frame, highly detailed.',
            'narration': '苍鹰展翅掠过幽深的山谷，引领视线坠入无垠的碧绿深处。',
            'resolution': '1080p',
            'model_name': 'Omni',
            'duration': 10
        },
        {
            'name': '镜头 3 · 赛博未来都市全景 (文生视频)',
            'mode': 'text2video',
            'image_url': '',
            'end_image_url': '',
            'prompt': 'Sweeping panoramic night view of a futuristic cyberpunk megacity, towering skyscrapers with glowing neon holographic advertisements, flying vehicles streaming along sky highways, cinematic 8k.',
            'narration': '夜幕下的未来都市，霓虹与数据流交织成永不熄灭的繁华。',
            'resolution': '1080p',
            'model_name': 'Omni',
            'duration': 10
        }
    ]
}

def normalize_imported_workflow_json(raw_input: Any, default_workflow: Optional[Dict[str, Any]] = None, default_engine: Optional[str] = None) -> Dict[str, Any]:
    import json
    if isinstance(raw_input, str):
        cleaned = raw_input.strip()
        if cleaned.startswith('`'):
            lines = cleaned.splitlines()
            if lines[0].startswith('`'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '`':
                lines = lines[:-1]
            cleaned = chr(10).join(lines).strip()
        parsed = json.loads(cleaned)
    else:
        parsed = raw_input

    base_wf = default_workflow or {}
    
    title = base_wf.get('title') or '批量导入工作流'
    doc_url = base_wf.get('doc_url') or ''
    style_prompt = base_wf.get('style_prompt') or ''
    aspect_ratio = base_wf.get('aspect_ratio') or '16:9'
    resolution = base_wf.get('resolution') or '1080p'
    model_name = base_wf.get('model_name') or 'Omni'
    duration_per_shot = base_wf.get('duration_per_shot') or 10

    # 引擎途径判定：优先使用前端UI传入的 default_engine；否则优先读base_wf，再次默认'vids'
    engine = (default_engine or base_wf.get('engine') or 'vids').strip().lower()
    if engine not in ('vids', 'flow', 'gemini'):
        engine = 'vids'

    raw_shots: List[Dict[str, Any]] = []

    if isinstance(parsed, list):
        raw_shots = parsed
    elif isinstance(parsed, dict):
        if 'title' in parsed and parsed['title']:
            title = str(parsed['title']).strip()
        if 'doc_url' in parsed and parsed['doc_url']:
            doc_url = str(parsed['doc_url']).strip()
        if 'style_prompt' in parsed and parsed['style_prompt']:
            style_prompt = str(parsed['style_prompt']).strip()
        if 'aspect_ratio' in parsed and parsed['aspect_ratio']:
            aspect_ratio = str(parsed['aspect_ratio']).strip()
        if 'resolution' in parsed and parsed['resolution']:
            resolution = str(parsed['resolution']).strip()
        elif 'quality' in parsed and parsed['quality']:
            resolution = str(parsed['quality']).strip()
        if 'model_name' in parsed and parsed['model_name']:
            model_name = str(parsed['model_name']).strip()
        elif 'model' in parsed and parsed['model']:
            model_name = str(parsed['model']).strip()
        if not default_engine and 'engine' in parsed and parsed['engine']:
            cand_eng = str(parsed['engine']).strip().lower()
            if cand_eng in ('vids', 'flow', 'gemini'):
                engine = cand_eng
        if 'duration_per_shot' in parsed:
            try:
                duration_per_shot = int(parsed['duration_per_shot'])
            except Exception:
                pass

        if 'shots' in parsed and isinstance(parsed['shots'], list):
            raw_shots = parsed['shots']
        elif 'tasks' in parsed and isinstance(parsed['tasks'], list):
            raw_shots = parsed['tasks']
        elif 'scenes' in parsed and isinstance(parsed['scenes'], list):
            raw_shots = parsed['scenes']

    normalized_shots: List[Dict[str, Any]] = []
    for idx, s in enumerate(raw_shots, start=1):
        if not isinstance(s, dict):
            continue

        prompt = s.get('prompt') or s.get('prompt_en') or s.get('text') or s.get('content') or ''
        narration = s.get('narration') or s.get('prompt_cn') or s.get('caption') or s.get('script') or ''
        if not prompt and narration:
            prompt = _enhance_chinese_to_vids_prompt(narration, idx)

        name = s.get('name') or s.get('title') or s.get('shot_name') or f'镜头 {idx}'

        duration = s.get('duration') or duration_per_shot
        try:
            duration = int(duration)
        except Exception:
            duration = 10

        img_url = (
            s.get('image_url') or
            s.get('start_image_path') or
            s.get('start_image') or
            s.get('start_frame') or
            s.get('first_frame') or
            s.get('first_image') or
            s.get('first_image_path') or
            s.get('reference_image') or
            s.get('ref_image') or
            ''
        )
        end_img_url = (
            s.get('end_image_url') or
            s.get('end_image_path') or
            s.get('end_image') or
            s.get('end_frame') or
            s.get('last_frame') or
            s.get('last_image') or
            s.get('last_image_path') or
            ''
        )
        if isinstance(img_url, str):
            img_url = img_url.strip().strip('"\'')
        if isinstance(end_img_url, str):
            end_img_url = end_img_url.strip().strip('"\'')

        mode = s.get('mode') or ''
        if not mode:
            if img_url and end_img_url:
                mode = 'first_last_frame'
            elif img_url:
                mode = 'image2video'
            else:
                mode = 'text2video'

        shot_res = s.get('resolution') or s.get('quality') or resolution or '1080p'
        shot_model = s.get('model_name') or s.get('model') or model_name or 'Omni'

        seq = s.get('sequence') or idx
        scene_idx = s.get('scene_index') or idx

        # 分镜级引擎：优先 default_engine；若无，且未在UI显式锁定时允许单项engine覆盖；最后回退至全局engine
        shot_engine = default_engine
        if not shot_engine and s.get('engine'):
            cand_s_eng = str(s.get('engine')).strip().lower()
            if cand_s_eng in ('vids', 'flow', 'gemini'):
                shot_engine = cand_s_eng
        if not shot_engine:
            if (end_img_url and img_url) or mode == 'first_last_frame':
                shot_engine = 'flow'
            else:
                shot_engine = engine

        normalized_shots.append({
            'name': name,
            'prompt': prompt,
            'narration': narration,
            'duration': duration,
            'sequence': seq,
            'scene_index': scene_idx,
            'mode': mode,
            'image_url': str(img_url).strip(),
            'end_image_url': str(end_img_url).strip(),
            'resolution': shot_res,
            'model_name': shot_model,
            'engine': shot_engine
        })

    return {
        'title': title,
        'doc_url': doc_url,
        'style_prompt': style_prompt,
        'aspect_ratio': aspect_ratio,
        'resolution': resolution,
        'model_name': model_name,
        'duration_per_shot': duration_per_shot,
        'engine': engine,
        'shots': normalized_shots
    }
