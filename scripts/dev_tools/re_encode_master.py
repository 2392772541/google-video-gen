import subprocess
from pathlib import Path
import shutil

BASE_DIR = Path(r"C:\Users\win10\Documents\ChatGPT\视频制作")
BUILD_DIR = BASE_DIR / "build_6ba"
RAW_VIDEO = BUILD_DIR / "raw_visual_45s.mp4"
MIXED_AUDIO = BUILD_DIR / "test_mixed_audio.m4a"
ASS_FILE = BUILD_DIR / "subtitles.ass"

LOCAL_MASTER = BUILD_DIR / "6BA_45s_科学纪录片_成片_1080p.mp4"
DELIVERY_MASTER = Path(r"E:\IDM下载\压缩\6BA_45s_science_video_package\6BA_45s_video_package\output\6BA_45s_科学纪录片_成片_1080p.mp4")

ass_path = str(ASS_FILE).replace("\\", "/").replace(":", "\\:")
cmd = [
    "ffmpeg", "-y",
    "-i", str(RAW_VIDEO),
    "-i", str(MIXED_AUDIO),
    "-vf", f"subtitles='{ass_path}'",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18",
    "-c:a", "copy",
    "-t", "45.0",
    str(LOCAL_MASTER)
]

print("Rendering final master...")
res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode != 0:
    print("Error:", res.stderr)
    exit(1)

shutil.copy2(LOCAL_MASTER, DELIVERY_MASTER)
print(f"Master successfully updated: {LOCAL_MASTER} and {DELIVERY_MASTER}")
