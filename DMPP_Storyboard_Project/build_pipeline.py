# -*- coding: utf-8 -*-
import json, base64, pathlib

proj_dir = pathlib.Path(r"C:\Users\win10\Documents\ChatGPT\视频制作\DMPP_Storyboard_Project")
shots_dir = proj_dir / "shots"
out_file = proj_dir / "dmpp_pipeline_flow_workflow.json"

shot_titles = [
    "01·黄金钩子·警报暴雷",
    "02·破题总论·高塔穿障",
    "03·关卡一·探针报告核验",
    "04·关卡二·混料结块痛点",
    "05·形态一·纳铠甲包晶解聚",
    "06·形态二·捷邦油剂雾化附着",
    "07·关卡三·恒温留样并轨",
    "08·法则升维·合金盾牌咬合",
    "09·品牌底气·车队破晓启程"
]

shot_image_prompts = [
    "Moody industrial quality inspection office bathed in spinning red warning alarm light, low-price chemical quotation paper vibrating in panic air, gloved hands of an engineer slamming an emergency stop lever for the granulating line, cinematic dramatic lighting, vertical 9:16.",
    "Grand 100m high-tower granulating plant, massive industrial pipes and steam vents in cold steel blue lighting, epic perspective, three holographic industrial inspection laser gates emerging, vertical 9:16.",
    "Macro probe camera view on chemical lab desk, ultraviolet light illuminating sample vials and inspection documents, sharp contrast, batch number verification with green laser scanner, vertical 9:16.",
    "Inside a heavy double-screw industrial mixer, dry chemical powder clumping into thick hard lumps jamming the spinning steel paddles under intense dust storm, vertical 9:16.",
    "Microscopic particle view of Naikaijia crystalline powder with nanometer crystal shell cleanly dissolving and dispersing uniformly into fertilizer matrix without clumping, glowing cyan particles, vertical 9:16.",
    "1000fps high-speed fluid cinematography of high-pressure atomizing nozzle spraying amber DMPX oil mist adhering as a microscopic smooth film over rolling spherical fertilizer granules, clean chamber walls, vertical 9:16.",
    "Infinite dolly track perspective down a futuristic blue-lit sample retention corridor with hundreds of sealed chemical bottles and green laser scanner lines, 30-batch overlapping absorption curves, vertical 9:16.",
    "Dynamic industrial mechanical interlocking composition merging spectrometer data, fluid streamlines, and barcode matrix into a solid titanium shield crest, glowing energy lines, vertical 9:16.",
    "Wide aerial view of a colossal modern agricultural chemical logistics park bathed in golden dawn light, convoys of heavy trucks carrying branded fertilizer packages driving out, vertical 9:16."
]

shot_video_prompts = [
    "FPV crash zoom diving rapidly toward the inspection desk, dramatic red rotating beacon flash, sudden dolly zoom vertigo effect expanding the background factory floor, abrupt mechanical stop, intense dramatic motion blur.",
    "Rapid FPV flight piercing through steel pipelines and rising steam plumes, ascending with a 360-degree Dutch roll out above the granulating towers, smooth downward crane descent, grand scale.",
    "Probe lens skimming micro-millimeters above paper texture, swift 180-degree orbital sweep around the chemical test vial, sharp rack focus to ultraviolet fluorescence glow.",
    "Low-angle dynamic upward spiral tracking alongside the rotating mixer paddle, turbulent powder vortex rushing directly into lens, sudden whip pan to clumped paddle blade.",
    "Hyper-macro particle fly-through entering the crystalline core, bullet time slow-motion deceleration as the nanometer coating ruptures and disperses in all directions.",
    "Fluid particle tracking locked onto an atomized amber droplet, 1000fps high-speed slow motion following the droplet impact and smooth spreading into an ultra-thin adhesive film.",
    "Smooth infinite forward dolly push down the central aisle, synchronized high-speed space contraction, green laser planar sweep moving across sample bottles.",
    "Dynamic 3-axis gimbal orbit rotating rapidly, three industrial components slamming together with a high-impact snap, shockwave ripple and spark emission settling into locked shield.",
    "Extreme aerial jib crane lifting smoothly upward into a massive wide pull-back shot, golden sunlight bursting past industrial silhouetted towers, serene convoy motion below."
]

shot_durations = [4, 4, 5, 4, 4, 4, 5, 4, 4]

nodes = []
edges = []
y_spacing = 620

for i in range(1, 10):
    shot_id = f"{i:02d}"
    base_y = (i - 1) * y_spacing + 50
    
    img_prompt_id = f"node_shot_{shot_id}_img_prompt"
    img_gen_id = f"node_shot_{shot_id}_img_gen"
    v_prompt_id = f"node_shot_{shot_id}_v_prompt"
    v_node_id = f"node_shot_{shot_id}_video"
    
    # 读取切片底图并编码为 Base64 嵌入初始资产
    img_path = shots_dir / f"shot_{shot_id}.png"
    data_url = ""
    if img_path.exists():
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            data_url = f"data:image/png;base64,{b64}"
            
    # 1. 生图提示词节点 (左上)
    nodes.append({
        "id": img_prompt_id,
        "type": "prompt",
        "x": 80,
        "y": base_y,
        "data": {
            "text": shot_image_prompts[i-1],
            "sceneLabel": f"{shot_id}·生图提示词 ({shot_titles[i-1]})"
        }
    })
    
    # 2. 生成图片节点 (中上) —— 内置九宫格裁剪底图作为初始切片主图资产与版本 V1
    nodes.append({
        "id": img_gen_id,
        "type": "generateImage",
        "x": 460,
        "y": base_y,
        "data": {
            "model": "gpt-image-2.5",
            "size": "9:16",
            "status": "completed",
            "qualityGate": "passed",
            "targetCount": 4,
            "asset": {
                "kind": "image",
                "name": f"shot_{shot_id}_base.png",
                "url": data_url,
                "width": 512,
                "height": 341
            },
            "versions": [
                {
                    "version": "V1",
                    "name": f"九宫格切片初始底图-V1",
                    "url": data_url,
                    "createdAt": "2026-10-28T02:30:00.000Z"
                }
            ],
            "sceneLabel": f"{shot_id}·生成图片资产"
        }
    })
    
    # 3. 运镜提示词节点 (左下)
    nodes.append({
        "id": v_prompt_id,
        "type": "prompt",
        "x": 80,
        "y": base_y + 260,
        "data": {
            "text": shot_video_prompts[i-1],
            "sceneLabel": f"{shot_id}·运镜提示词 (动感参数)"
        }
    })
    
    # 4. 生成视频节点 (右侧直通) —— 启用尾帧递归传递锁
    nodes.append({
        "id": v_node_id,
        "type": "generateVideo",
        "x": 900,
        "y": base_y + 110,
        "data": {
            "model": "muse-video",
            "size": "9:16",
            "duration": shot_durations[i-1],
            "continuity": (i > 1),
            "endFrameLock": True,
            "status": "idle",
            "sceneLabel": f"{shot_id}·生成视频 (直通流)"
        }
    })
    
    # 连线 1: 生图提示词 ──> 生成图片
    edges.append({
        "id": f"edge_prompt_to_img_{shot_id}",
        "source": img_prompt_id,
        "sourcePort": "text",
        "target": img_gen_id,
        "targetPort": "prompt"
    })
    
    # 连线 2: 生成图片 ──(直通贯穿)──> 生成视频的参考图端口
    edges.append({
        "id": f"edge_img_to_video_{shot_id}",
        "source": img_gen_id,
        "sourcePort": "image",
        "target": v_node_id,
        "targetPort": "reference"
    })
    
    # 连线 3: 运镜提示词 ──> 生成视频
    edges.append({
        "id": f"edge_prompt_to_video_{shot_id}",
        "source": v_prompt_id,
        "sourcePort": "text",
        "target": v_node_id,
        "targetPort": "prompt"
    })

# 5. 第 37 节点：时间线保序节点 (锁定 1~9 顺序)
video_ids = [f"node_shot_{k:02d}_video" for k in range(1, 10)]
durations_map = {vid: shot_durations[idx] for idx, vid in enumerate(video_ids)}

nodes.append({
    "id": "node_timeline",
    "type": "timeline",
    "x": 1450,
    "y": 500,
    "data": {
        "label": "全片时间线 (严格九镜锁定播放序)",
        "clipOrder": video_ids,
        "durations": durations_map,
        "clips": [
            {
                "nodeId": vid,
                "shotNumber": idx + 1,
                "title": shot_titles[idx],
                "duration": shot_durations[idx]
            }
            for idx, vid in enumerate(video_ids)
        ],
        "aspectRatio": "9:16",
        "totalDuration": sum(shot_durations)
    }
})

workflow_json = {
    "appVersion": "0.5.0",
    "format": "26flow-workflow",
    "version": 1,
    "project": "DMPP肥料采购排障指南",
    "aspectRatio": "9:16",
    "exportedAt": "2026-10-28T02:35:00.000Z",
    "workflow": {
        "nodes": nodes,
        "edges": edges,
        "settings": {
            "totalShots": 9,
            "pipelineFlow": True,
            "lockedSequence": True,
            "endFrameContinuity": True
        }
    }
}

with open(out_file, "w", encoding="utf-8") as f:
    json.dump(workflow_json, f, ensure_ascii=False, indent=2)

file_mb = out_file.stat().st_size / (1024 * 1024)
print(f"[✓] 成功构建 26Flow/MuseFlow 直通流水线工作流！")
print(f"    - 总节点数: {len(nodes)} (36 镜头核心节点 + 1 时间线保序节点)")
print(f"    - 总连线条数: {len(edges)} (27 条直通连线，零悬空)")
print(f"    - 总时长: {sum(shot_durations)} 秒")
print(f"    - 工程导出路径: {out_file} ({file_mb:.2f} MB)")
