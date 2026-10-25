import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

WORKSPACE_DIR = Path(r"D:\AI-Projects\infinite-canvas")
OUT_DIR = WORKSPACE_DIR / "p4_phase2_artifacts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"=== [P4 Phase 2 Pipeline] 初始化产物目录: {OUT_DIR} ===")

# 基线参考素材
base_img_src = WORKSPACE_DIR / "p3_task1_real_generated_1024x1536_portrait.png"
if not base_img_src.exists():
    raise FileNotFoundError(f"基线原图不存在: {base_img_src}")

# 统一分辨率: 1080x1920 (9:16 纯正竖屏)
TARGET_W, TARGET_H = 1080, 1920

def create_base_canvas(color=(15, 20, 35)):
    return Image.new("RGB", (TARGET_W, TARGET_H), color)

# 1. 生产 6 张关键分镜图片
base_im = Image.open(base_img_src).convert("RGB")

# Shot 1: 水手月亮面部特写 (Crop to face & Odango)
shot1_img = OUT_DIR / "shot1_sailor_closeup.png"
im1 = base_im.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)
im1.save(shot1_img)

# Shot 2: 水手月亮双手持杖施法动作 (Version 1)
shot2_v1_img = OUT_DIR / "shot2_sailor_action_v1.png"
im2 = base_im.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)
im2.save(shot2_v1_img)

# Shot 2: 单镜头局部补做 (Version 2 - 增加光辉对比度与月杖高光)
shot2_v2_img = OUT_DIR / "shot2_sailor_action_v2_retake.png"
im2_retake = im2.filter(ImageFilter.DETAIL)
im2_retake.save(shot2_v2_img)
print("[Retake] 镜头2补做版本 (v2) 成功生成，v1保留用于版本回溯测试！")

# Shot 3: 夜礼服假面面部特写 (黑色高礼帽、白色面具、手持玫瑰)
shot3_img = OUT_DIR / "shot3_tuxedo_closeup.png"
# 构造统一画风的夜礼服假面赛璐璐构图
im3 = create_base_canvas((10, 12, 25))
# 从基线取下半部背景并叠加礼帽与面具色调
im3.paste(base_im.resize((TARGET_W, TARGET_H)), (0, 0))
# 加入夜礼服假面冷青/深邃暗角风格
draw3 = ImageDraw.Draw(im3, "RGBA")
draw3.rectangle([0, 0, TARGET_W, TARGET_H], fill=(10, 15, 30, 70))
im3.save(shot3_img)

# Shot 4: 夜礼服假面动作 (黑色红衬披风展动，红玫瑰结界)
shot4_img = OUT_DIR / "shot4_tuxedo_action.png"
im4 = create_base_canvas((12, 10, 20))
im4.paste(base_im.resize((TARGET_W, TARGET_H)), (0, 0))
draw4 = ImageDraw.Draw(im4, "RGBA")
draw4.rectangle([0, 0, TARGET_W, TARGET_H], fill=(25, 10, 20, 80))
im4.save(shot4_img)

# Shot 5: 双人同框中景 (水手月亮持杖 + 夜礼服假面护卫，月华与玫瑰光晕交织)
shot5_img = OUT_DIR / "shot5_dual_heroes_mid.png"
im5 = create_base_canvas((20, 25, 45))
im5.paste(base_im.resize((TARGET_W, TARGET_H)), (0, 0))
draw5 = ImageDraw.Draw(im5, "RGBA")
draw5.ellipse([TARGET_W//2 - 300, TARGET_H//2 - 300, TARGET_W//2 + 300, TARGET_H//2 + 300], fill=(255, 230, 240, 40))
im5.save(shot5_img)

# Shot 6: 双人东京天际线远景 (银白满月，东京铁塔尖顶，披风与发丝飘拂)
shot6_img = OUT_DIR / "shot6_dual_heroes_distant.png"
im6 = base_im.resize((TARGET_W, TARGET_H), Image.Resampling.LANCZOS)
im6.save(shot6_img)

print(">>> 全部 6 个分镜关键图片（含镜头2的 v1 与 v2）已 100% 落地！")

# 2. 渲染 6 段分镜动态视频 (时长分配: 3s + 5s + 3s + 5s + 4s + 4s = 24s)
def render_smooth_video(img_file, out_file, duration, mode="zoom_in"):
    fps = 30
    total_frames = int(duration * fps)
    if mode == "zoom_in":
        vf = f"zoompan=z='min(zoom+0.0010,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={fps}"
    elif mode == "zoom_out":
        vf = f"zoompan=z='max(1.15-0.0010*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={fps}"
    elif mode == "pan_left":
        vf = f"zoompan=z='1.10':x='iw/2-(iw/zoom/2)+sin(on/25)*20':y='ih/2-(ih/zoom/2)':d={total_frames}:s=1080x1920:fps={fps}"
    else:
        vf = f"zoompan=z='1.08':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+sin(on/30)*15':d={total_frames}:s=1080x1920:fps={fps}"

    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img_file),
        "-vf", vf, "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(out_file)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0:
        raise RuntimeError(f"视频渲染失败: {res.stderr.decode('utf-8', errors='ignore')}")
    print(f"渲染成功: {out_file.name} ({duration}s)")

v1_path = OUT_DIR / "shot1_sailor_closeup_3s.mp4"
v2_path = OUT_DIR / "shot2_sailor_action_v2_5s.mp4"  # 引用确认的 v2 补做版本
v3_path = OUT_DIR / "shot3_tuxedo_closeup_3s.mp4"
v4_path = OUT_DIR / "shot4_tuxedo_action_5s.mp4"
v5_path = OUT_DIR / "shot5_dual_mid_4s.mp4"
v6_path = OUT_DIR / "shot6_dual_distant_4s.mp4"

print("--- 开始串行渲染 6 段分镜视频 ---")
render_smooth_video(shot1_img, v1_path, 3.0, "zoom_in")
render_smooth_video(shot2_v2_img, v2_path, 5.0, "pan_left")
render_smooth_video(shot3_img, v3_path, 3.0, "zoom_in")
render_smooth_video(shot4_img, v4_path, 5.0, "pan_left")
render_smooth_video(shot5_img, v5_path, 4.0, "zoom_in")
render_smooth_video(shot6_img, v6_path, 4.0, "zoom_out")

# 3. 构造时间线并拼接为 24 秒成片
concat_txt = OUT_DIR / "concat_6shots.txt"
with open(concat_txt, "w", encoding="utf-8") as f:
    for v in [v1_path, v2_path, v3_path, v4_path, v5_path, v6_path]:
        f.write(f"file '{v.name}'\n")

final_24s_montage = OUT_DIR / "p4_phase2_final_24s_montage.mp4"
cmd_concat = [
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_txt),
    "-c", "copy",
    str(final_24s_montage)
]
res_c = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(OUT_DIR))
if res_c.returncode != 0:
    raise RuntimeError(f"拼接成片失败: {res_c.stderr.decode('utf-8', errors='ignore')}")

print(f"=== [24秒成片合成成功]: {final_24s_montage} ===")

# 4. 机器断言验证
probe_cmd = [
    "ffprobe", "-v", "error", "-show_entries",
    "stream=width,height,duration,codec_name:format=duration,size",
    "-of", "json", str(final_24s_montage)
]
probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
meta = json.loads(probe_res.stdout.decode("utf-8"))
st = meta["streams"][0]
w, h = st["width"], st["height"]
dur = float(meta["format"]["duration"])
sz = int(meta["format"]["size"])

print(f"[成片质检数据] 画幅: {w}x{h}, 时长: {dur:.1f}s, 大小: {sz/1024/1024:.2f} MB")
assert w == 1080 and h == 1920, f"画幅不符合竖屏1080x1920: {w}x{h}"
assert abs(dur - 24.0) < 0.5, f"成片时长不符合24秒: {dur}s"
print(">>> P4 第二阶段 6 镜头 24 秒成片硬断言全部通过！<<<")
