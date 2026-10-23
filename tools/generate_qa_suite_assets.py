# -*- coding: utf-8 -*-
"""
generate_qa_suite_assets.py - 视频工坊与无限画布 14 大核心功能全套真实测试素材生成工具
"""
import os
import sys
import json
import base64
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
QA_DIR = ROOT / "qa_assets"

def ensure_dirs():
    for sub in ["prompts", "images", "videos", "scripts", "canvas"]:
        (QA_DIR / sub).mkdir(parents=True, exist_ok=True)

def create_image(filename: str, size: tuple, bg_color: tuple, text: str, shape_color: tuple = None, shape_pos: tuple = None):
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # 绘制参考几何图形（用于首尾帧变化与NCC差异）
    if shape_color and shape_pos:
        draw.ellipse(shape_pos, fill=shape_color, outline=(255, 255, 255), width=3)
    
    # 绘制文字与参考网格
    draw.rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(100, 100, 100), width=2)
    draw.text((30, 30), f"Video Farm QA Asset\n{text}\nSize: {size[0]}x{size[1]}", fill=(255, 255, 255))
    
    out_path = QA_DIR / "images" / filename
    img.save(out_path, format="PNG")
    print(f"Generated Image: {out_path.name} ({size[0]}x{size[1]})")
    return out_path

def create_video(filename: str, duration: int = 2, size: str = "1280x720"):
    out_path = QA_DIR / "videos" / filename
    # 使用 ffmpeg 生成自带颜色变化的合法 MP4 视频
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"testsrc=duration={duration}:size={size}:rate=30",
        "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(out_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    print(f"Generated Video: {out_path.name} ({duration}s, {size})")
    return out_path

def main():
    ensure_dirs()
    print("=== 开始生成 14 项功能专属测试素材 ===")
    
    # 1. V01 文生视频提示词 (中文 & 英文)
    (QA_DIR / "prompts" / "v01_cn_cinematic.txt").write_text(
        "电影级微距航拍，金色麦浪在晨光中微微摇曳，镜头缓慢拉升展现远方破晓的朝霞，逆光丁达尔效应，8k写实，极具质感", encoding="utf-8"
    )
    (QA_DIR / "prompts" / "v01_en_dynamic.txt").write_text(
        "Cinematic slow-motion tracking shot of a glowing futuristic sports car speeding along a neon highway at midnight, rain reflections, 4k", encoding="utf-8"
    )
    
    # 2. V02 图生视频参考图 (横屏 16:9 与 竖屏 9:16)
    img_v02_16_9 = create_image("v02_start_16_9.png", (1280, 720), (24, 32, 54), "V02 Start Image 16:9", (230, 80, 50), (100, 150, 300, 350))
    img_v02_9_16 = create_image("v02_start_9_16.png", (720, 1280), (32, 24, 48), "V02 Start Image 9:16", (50, 180, 220), (200, 300, 520, 620))
    
    # 3. V03 首尾帧成对素材 (起止帧位移测试)
    img_v03_first = create_image("v03_first_frame.png", (1280, 720), (20, 30, 40), "V03 FIRST FRAME (Stationary)", (0, 200, 255), (150, 200, 350, 400))
    img_v03_last = create_image("v03_last_frame.png", (1280, 720), (20, 30, 40), "V03 LAST FRAME (Shifted & Glowing)", (255, 120, 0), (750, 200, 950, 400))
    
    # 4. V04 视频参考与延展素材 (合法 MP4)
    vid_v04_ref = create_video("v04_ref_video.mp4", duration=2, size="1280x720")
    
    # 5. I01 文生图提示词
    (QA_DIR / "prompts" / "i01_photorealistic.txt").write_text(
        "极简工业设计，黑曜石材质无线耳机置于温润原木托盘上，极简柔和棚拍侧光，哈苏景深，质感真实", encoding="utf-8"
    )
    (QA_DIR / "prompts" / "i01_poster_design.txt").write_text(
        "科幻电影概念艺术海报，巨大的戴森球环绕发光恒星，极具视觉冲击力的平面几何排版，未来主义", encoding="utf-8"
    )
    
    # 6. I02 图生图与多图参考 (主体图与风格图)
    img_i02_sub = create_image("i02_subject_ref.png", (1024, 1024), (45, 55, 72), "I02 Subject Character", (246, 173, 85), (300, 300, 724, 724))
    img_i02_sty = create_image("i02_style_ref.png", (1024, 1024), (90, 20, 60), "I02 Style Palette", (180, 50, 210), (100, 100, 924, 924))
    
    # 7. I03 批量生图参数配置
    i03_spec = {
        "batch_name": "批量概念生成验证",
        "tasks": [
            {"prompt": "未来都市飞行器 A", "aspect_ratio": "16:9", "count": 2},
            {"prompt": "赛博机甲装配车间 B", "aspect_ratio": "9:16", "count": 2},
            {"prompt": "深空探测器着陆火星 C", "aspect_ratio": "1:1", "count": 1}
        ]
    }
    (QA_DIR / "prompts" / "i03_batch_prompts.json").write_text(json.dumps(i03_spec, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 8. S01 剧本自然语言解析素材
    (QA_DIR / "scripts" / "s01_storyboard_script.txt").write_text("""
镜头01: 全景远眺。蔚蓝海面上孤岛灯塔静静矗立，晨雾缭绕。
旁白: 当清晨的第一道微光穿透海雾，守塔人又开始了新的一天。
时长: 5秒 | 16:9

镜头02: 特写镜头。黄铜航海罗盘的指针缓缓摆动并最终定格。
旁白: 在浩瀚无垠的航道中，方向比速度更加珍贵。
时长: 5秒 | 16:9

镜头03: 中景运镜。机械发条齿轮精密咬合，灯塔巨型透镜缓缓旋转发出光芒。
旁白: 每一个精准齿轮的转动，都在守护着远方归人的航线。
时长: 8秒 | 16:9
""".strip(), encoding="utf-8")
    
    # 9. S02 批量分镜导入 JSON 结构
    s02_json = {
        "title": "灯塔晨曦守望者",
        "doc_url": "",
        "engine": "flow",
        "aspect_ratio": "16:9",
        "duration_per_shot": 5,
        "resolution": "1080p",
        "shots": [
            {
                "name": "镜头 01",
                "scene_num": 1,
                "prompt": "全景远眺，蔚蓝海面上孤岛灯塔静静矗立，晨雾缭绕",
                "narration": "当清晨的第一道微光穿透海雾，守塔人又开始了新的一天。",
                "duration": 5,
                "mode": "text2video"
            },
            {
                "name": "镜头 02",
                "scene_num": 2,
                "prompt": "特写镜头，黄铜航海罗盘的指针缓缓摆动并最终定格",
                "narration": "在浩瀚无垠的航道中，方向比速度更加珍贵。",
                "duration": 5,
                "mode": "text2video"
            },
            {
                "name": "镜头 03",
                "scene_num": 3,
                "prompt": "中景运镜，机械发条齿轮精密咬合，灯塔透镜旋转发光",
                "narration": "每一个精准齿轮的转动，都在守护着远方归人的航线。",
                "duration": 5,
                "mode": "text2video"
            }
        ]
    }
    (QA_DIR / "scripts" / "s02_vids_batch_import.json").write_text(json.dumps(s02_json, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 10. C01 无限画布模型通道请求素材
    (QA_DIR / "canvas" / "c01_chat_request.json").write_text(json.dumps({
        "model": "gpt-6-astra",
        "messages": [
            {"role": "system", "content": "You are a creative visual art director."},
            {"role": "user", "content": "Suggest a compelling concept for an interactive sci-fi storyboard."}
        ]
    }, indent=2), encoding="utf-8")
    
    # 11. C03 画布导出回传素材 (Base64 与图像文件)
    c03_img = create_image("c03_export_image.png", (512, 512), (70, 40, 110), "Canvas Created Art", (0, 240, 160), (120, 120, 392, 392))
    c03_b64 = "data:image/png;base64," + base64.b64encode(c03_img.read_bytes()).decode()
    (QA_DIR / "canvas" / "c03_export_image_dataurl.txt").write_text(c03_b64, encoding="utf-8")
    
    print(f"\n全套测试素材已成功生成于: {QA_DIR.resolve()}")

if __name__ == "__main__":
    main()
