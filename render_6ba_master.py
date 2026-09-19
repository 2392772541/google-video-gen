import os
import sys
import subprocess
import json
from pathlib import Path

BASE_DIR = Path(r"C:\Users\win10\Documents\ChatGPT\视频制作")
CROPS_DIR = BASE_DIR / "temp_crops_16x9"
BUILD_DIR = BASE_DIR / "build_6ba"
AUDIO_DIR = BUILD_DIR / "audio"
SHOTS_DIR = BUILD_DIR / "shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

VO_FILE = AUDIO_DIR / "full_narration.mp3"
BGM_FILE = Path(r"E:\公司素材\音乐素材\未来先行 音乐\纪录片配乐-完整版.mp3")
OUTPUT_DIR = Path(r"E:\IDM下载\压缩\6BA_45s_science_video_package\6BA_45s_video_package\output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MASTER_MP4 = OUTPUT_DIR / "6BA_45s_科学纪录片_成片_1080p.mp4"
LOCAL_MASTER_MP4 = BUILD_DIR / "6BA_45s_科学纪录片_成片_1080p.mp4"

# 18 镜头配置
SHOTS_CONFIG = [
    # Section A
    {"id": "A1", "file": "A1_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.07},
    {"id": "A2", "file": "A2_1080p.png", "type": "pan_left", "scale": 1.05, "x_start": 0.54, "x_end": 0.46},
    {"id": "A3", "file": "A3_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.04},
    {"id": "A4", "file": "A4_1080p.png", "type": "pan_up", "scale": 1.05, "y_start": 0.54, "y_end": 0.46},
    {"id": "A5", "file": "A5_1080p.png", "type": "pan_right", "scale": 1.05, "x_start": 0.46, "x_end": 0.54},
    {"id": "A6", "file": "A6_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.08},
    # Section B
    {"id": "B1", "file": "B1_1080p.png", "type": "zoom_in", "s_start": 1.01, "s_end": 1.05},
    {"id": "B2", "file": "B2_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.06},
    {"id": "B3", "file": "B3_1080p.png", "type": "pan_right", "scale": 1.05, "x_start": 0.47, "x_end": 0.53},
    {"id": "B4", "file": "B4_1080p.png", "type": "pan_diag", "scale": 1.06, "x_start": 0.53, "x_end": 0.47, "y_start": 0.47, "y_end": 0.53},
    {"id": "B5", "file": "B5_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.06},
    {"id": "B6", "file": "B6_1080p.png", "type": "zoom_out", "s_start": 1.07, "s_end": 1.00},
    # Section C
    {"id": "C1", "file": "C1_1080p.png", "type": "pan_right", "scale": 1.05, "x_start": 0.46, "x_end": 0.54},
    {"id": "C2", "file": "C2_1080p.png", "type": "pan_zoom", "s_start": 1.02, "s_end": 1.06, "x_start": 0.48, "x_end": 0.52},
    {"id": "C3", "file": "C3_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.04},
    {"id": "C4", "file": "C4_1080p.png", "type": "pan_left", "scale": 1.05, "x_start": 0.53, "x_end": 0.47},
    {"id": "C5", "file": "C5_1080p.png", "type": "zoom_in", "s_start": 1.00, "s_end": 1.07},
    {"id": "C6", "file": "C6_1080p.png", "type": "zoom_out", "s_start": 1.06, "s_end": 1.00},
]

print("[1/4] 渲染 18 个 2.5 秒独立运镜切片...")
concat_list = []
# 45s * 25fps = 1125 帧。前9个镜头62帧，后9个镜头63帧：9*62 + 9*63 = 558 + 567 = 1125 帧 = 45.000s
for idx, cfg in enumerate(SHOTS_CONFIG):
    sid = cfg["id"]
    in_img = CROPS_DIR / cfg["file"]
    out_mp4 = SHOTS_DIR / f"shot_{idx:02d}_{sid}.mp4"
    num_frames = 62 if idx < 9 else 63
    dur_sec = num_frames / 25.0
    
    stype = cfg["type"]
    if stype == "zoom_in":
        s0, s1 = cfg["s_start"], cfg["s_end"]
        vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)/2',fps=25"
    elif stype == "zoom_out":
        s0, s1 = cfg["s_start"], cfg["s_end"]
        vf = f"scale='iw*({s0}-({s0}-{s1})*t/{dur_sec})':'ih*({s0}-({s0}-{s1})*t/{dur_sec})':eval=frame,crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)/2',fps=25"
    elif stype == "pan_left":
        sc = cfg["scale"]
        x0, x1 = cfg["x_start"], cfg["x_end"]
        vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)/2',fps=25"
    elif stype == "pan_right":
        sc = cfg["scale"]
        x0, x1 = cfg["x_start"], cfg["x_end"]
        vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)/2',fps=25"
    elif stype == "pan_up":
        sc = cfg["scale"]
        y0, y1 = cfg["y_start"], cfg["y_end"]
        vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)*({y0}+({y1}-{y0})*t/{dur_sec})',fps=25"
    elif stype == "pan_diag":
        sc = cfg["scale"]
        x0, x1 = cfg["x_start"], cfg["x_end"]
        y0, y1 = cfg["y_start"], cfg["y_end"]
        vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)*({y0}+({y1}-{y0})*t/{dur_sec})',fps=25"
    elif stype == "pan_zoom":
        s0, s1 = cfg["s_start"], cfg["s_end"]
        x0, x1 = cfg["x_start"], cfg["x_end"]
        vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)/2',fps=25"
    else:
        vf = "scale=1920:1080,fps=25"
        
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", str(dur_sec),
        "-i", str(in_img),
        "-vf", vf,
        "-frames:v", str(num_frames),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", "-crf", "18",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[Error] 镜头 {sid} 渲染失败: {res.stderr}")
        sys.exit(1)
    concat_list.append(out_mp4)
    print(f"  - 镜头 {sid} ({num_frames} 帧, {dur_sec:.2f}s) 渲染完成")

concat_txt = BUILD_DIR / "concat_shots.txt"
with open(concat_txt, "w", encoding="utf-8") as f:
    for p in concat_list:
        # 转义并格式化
        f.write(f"file '{p.as_posix()}'\n")

raw_video = BUILD_DIR / "raw_visual_45s.mp4"
print("[2/4] 无损拼接 18 镜头画面轨道...")
cmd_concat = [
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", str(concat_txt),
    "-c", "copy",
    str(raw_video)
]
subprocess.run(cmd_concat, check=True)

# 验证画面总长
res = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(raw_video)], capture_output=True, text=True)
info = json.loads(res.stdout)
dur = float(info["format"]["duration"])
nb_frames = info["streams"][0].get("nb_frames")
print(f"  - 拼接画面总时长: {dur:.3f} 秒 (总帧数: {nb_frames})")

print("[3/4] 准备纪录片 ASS 风格字幕...")
ass_content = """[Script Info]
Title: 6-BA Science Documentary
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,38,&H00FFFFFF,&H000000FF,&H80151815,&H80000000,-1,0,0,0,100,100,1,0,1,2.0,1.2,2,60,60,55,1
Style: TopicTag,Microsoft YaHei,28,&H004ED2FF,&H000000FF,&H80151815,&H80000000,-1,0,0,0,100,100,1.5,0,1,1.5,1.0,7,80,60,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.80,0:00:06.10,Default,,0,0,0,,6BA不以膨果速度见长，\\N但配方要的，不是单项冠军。
Dialogue: 0,0:00:06.10,0:00:13.80,Default,,0,0,0,,它是第一代合成腺嘌呤型细胞分裂素之一，\\N能促进细胞分裂、芽体分化并延缓叶片衰老。
Dialogue: 0,0:00:13.80,0:00:18.55,Default,,0,0,0,,进入细胞后，6BA与受体结合，\\N启动多步磷酸接力。
Dialogue: 0,0:00:18.55,0:00:25.40,Default,,0,0,0,,信号逐级传入细胞核，激活转录因子，\\N开启分裂、分化和保绿相关基因。
Dialogue: 0,0:00:25.40,0:00:29.00,Default,,0,0,0,,相比氯吡脲，6BA更偏综合调控。
Dialogue: 0,0:00:29.00,0:00:34.50,Default,,0,0,0,,制剂表现还取决于纯度、杂质谱、\\N稳定性和批次一致性。
Dialogue: 0,0:00:34.50,0:00:43.20,Default,,0,0,0,,河南粮保99%含量6BA原药，为制剂开发提供稳定起点。\\N要6BA原药，找粮保。
"""

ass_file = BUILD_DIR / "subtitles.ass"
with open(ass_file, "w", encoding="utf-8") as f:
    f.write(ass_content)

print("[4/4] 智能混音 (VO + BGM) 并烧录字幕，生成最终母片...")
# 音频混音：
# 旁白：full_narration.mp3，前置延时 800ms，音量 1.0 (峰值约 -6dB)
# 背景音乐：未来先行 纪录片配乐，0~45s，淡入 2s，淡出 2.5s (42.5~45.0s)，音量 0.16
# 滤镜图同时渲染 ass 字幕
ass_filter_path = str(ass_file).replace("\\", "/").replace(":", "\\:")
complex_filter = (
    f"[0:v]subtitles='{ass_filter_path}'[vout];"
    f"[1:a]adelay=800|800,volume=1.0[vo];"
    f"[2:a]atrim=0:45.0,afade=t=in:ss=0:d=2.0,afade=t=out:st=42.5:d=2.5,volume=0.16[bgm];"
    f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
)

cmd_master = [
    "ffmpeg", "-y",
    "-i", str(raw_video),
    "-i", str(VO_FILE),
    "-i", str(BGM_FILE),
    "-filter_complex", complex_filter,
    "-map", "[vout]",
    "-map", "[aout]",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18",
    "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
    "-t", "45.0",
    str(LOCAL_MASTER_MP4)
]

print("Executing master FFmpeg build...")
res = subprocess.run(cmd_master, capture_output=True, text=True)
if res.returncode != 0:
    print(f"[Error] 母片合成失败:\n{res.stderr}")
    sys.exit(1)

# 复制到目标交付目录
import shutil
shutil.copy2(LOCAL_MASTER_MP4, MASTER_MP4)
print(f"\n[Success] 45秒商业科学纪录片母片成功生成!")
print(f"本地构建产物: {LOCAL_MASTER_MP4}")
print(f"交付专区产物: {MASTER_MP4}")
