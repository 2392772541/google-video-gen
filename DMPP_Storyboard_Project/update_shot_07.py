# -*- coding: utf-8 -*-
import json, base64, pathlib

proj_dir = pathlib.Path(r"C:\Users\win10\Documents\ChatGPT\视频制作\DMPP_Storyboard_Project")
workflow_file = proj_dir / "dmpp_pipeline_flow_workflow.json"
v2_img_file = proj_dir / "shots" / "shot_07_v2_chinese_plant.png"

with open(workflow_file, "r", encoding="utf-8") as f:
    wf = json.load(f)

with open(v2_img_file, "rb") as f:
    v2_b64 = base64.b64encode(f.read()).decode("utf-8")
v2_data_url = f"data:image/png;base64,{v2_b64}"

new_img_prompt = (
    "A documentary-style cinematic shot capturing the authentic sample retention room and quality inspection center "
    "of a modern Chinese chemical fertilizer manufacturing plant. Natural bright daylight mixed with clean industrial "
    "laboratory ceiling lights illuminating rows of neat stainless-steel sample shelves filled with hundreds of standard "
    "glass wide-mouth chemical sample bottles containing fertilizer granules and liquid samples with white paper label seals. "
    "In the foreground, a clean industrial laboratory bench with testing instruments and sample logbook. In the background "
    "through a large factory window, the iconic silhouette of a massive Chinese fertilizer high-tower granulator under realistic daylight. "
    "A Chinese quality control technician wearing standard dark blue industrial chemical work jacket meticulously inspecting a sample bottle. "
    "Dolly track perspective, highly authentic, professional industrial realism, 8k, vertical 9:16."
)

new_video_prompt = (
    "Smooth cinematic dolly track sliding across the stainless-steel sample shelf in a modern Chinese fertilizer plant, "
    "camera focus shifting smoothly from the handwritten sample logbook and analytical balance to the technician holding "
    "a glass sample jar, wide factory window revealing high-tower granulators bathed in clear daylight, natural steady industrial camera move."
)

# 遍历节点并更新第 7 镜
for node in wf["workflow"]["nodes"]:
    nid = node["id"]
    if nid == "node_shot_07_img_prompt":
        node["data"]["text"] = new_img_prompt
        node["data"]["sceneLabel"] = "07·生图提示词 (中国化肥厂规范留样室)"
    elif nid == "node_shot_07_img_gen":
        node["data"]["asset"]["url"] = v2_data_url
        node["data"]["asset"]["name"] = "shot_07_v2_chinese_plant.png"
        node["data"]["asset"]["width"] = 1024
        node["data"]["asset"]["height"] = 1792
        # 更新版本记录
        versions = node["data"].get("versions", [])
        versions.append({
            "version": "V2",
            "name": "中国化肥厂实景质检留样室 (主选)",
            "url": v2_data_url,
            "createdAt": "2026-10-28T03:15:00.000Z",
            "selected": True
        })
        node["data"]["versions"] = versions
    elif nid == "node_shot_07_v_prompt":
        node["data"]["text"] = new_video_prompt
        node["data"]["sceneLabel"] = "07·运镜提示词 (化肥厂实景平移变焦)"

with open(workflow_file, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print("[✓] 成功更新第 7 镜资产与版本记录：V2 中国化肥厂实景版已激活！")
