# -*- coding: utf-8 -*-
import json, base64, pathlib

proj_dir = pathlib.Path(r"C:\Users\win10\Documents\ChatGPT\视频制作\DMPP_Storyboard_Project")
workflow_file = proj_dir / "dmpp_pipeline_flow_workflow.json"
v3_img_file = proj_dir / "shots" / "shot_07_v3_neutral_chinese_plant.png"

with open(workflow_file, "r", encoding="utf-8") as f:
    wf = json.load(f)

with open(v3_img_file, "rb") as f:
    v3_b64 = base64.b64encode(f.read()).decode("utf-8")
v3_data_url = f"data:image/png;base64,{v3_b64}"

new_img_prompt = (
    "A documentary-style cinematic shot capturing the authentic sample retention room and quality inspection center "
    "of a modern Chinese chemical fertilizer manufacturing plant. Natural bright daylight mixed with clean industrial "
    "laboratory ceiling lights illuminating rows of neat stainless-steel sample shelves filled with hundreds of standard "
    "glass wide-mouth chemical sample bottles containing fertilizer granules and amber liquid samples with white paper batch label seals. "
    "In the foreground, a clean industrial laboratory bench with an analytical precision balance, sample tray, and open sample logbook. "
    "In the background through a large industrial factory window, the iconic silhouette of a massive Chinese fertilizer high-tower granulator "
    "under realistic daylight, generic clean factory architecture, no corporate brand names. A focused Chinese quality control technician "
    "wearing generic dark blue industrial work jacket with neutral circular QA badge and white gloves, inspecting a sample jar. "
    "Dolly track perspective, authentic Chinese agricultural chemical industry atmosphere, 8k, vertical 9:16."
)

new_video_prompt = (
    "Smooth cinematic dolly track sliding from the precision analytical balance and handwritten sample logbook "
    "upward to the focused female QA technician inspecting the fertilizer sample bottle, sunlight streaming past the large "
    "window revealing the distant industrial granulator tower, steady authentic Chinese industrial documentary camera movement."
)

for node in wf["workflow"]["nodes"]:
    nid = node["id"]
    if nid == "node_shot_07_img_prompt":
        node["data"]["text"] = new_img_prompt
        node["data"]["sceneLabel"] = "07·生图提示词 (中国化肥厂中性留样室·V3)"
    elif nid == "node_shot_07_img_gen":
        node["data"]["asset"]["url"] = v3_data_url
        node["data"]["asset"]["name"] = "shot_07_v3_neutral_chinese_plant.png"
        node["data"]["asset"]["width"] = 1024
        node["data"]["asset"]["height"] = 1792
        versions = node["data"].get("versions", [])
        for v in versions:
            v["selected"] = False
        versions.append({
            "version": "V3",
            "name": "中国化肥厂中性质检留样室 (当前定稿)",
            "url": v3_data_url,
            "createdAt": "2026-10-28T03:25:00.000Z",
            "selected": True
        })
        node["data"]["versions"] = versions
    elif nid == "node_shot_07_v_prompt":
        node["data"]["text"] = new_video_prompt
        node["data"]["sceneLabel"] = "07·运镜提示词 (天平留样到质检员中平移)"

with open(workflow_file, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print("[✓] 成功更新工作流：第 7 镜 V3 终版已激活并设为主资产！")
