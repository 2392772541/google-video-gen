import shutil
import subprocess
from pathlib import Path

OUT_ROOT = Path(r"E:\IDM下载\压缩\6BA_45s_science_video_package\6BA_45s_video_package\output")
AI_CLIPS_DIR = OUT_ROOT / "AI_Generated_Clips"
AI_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

ai_clips = [
    ("Section_A_身份与综合能力_Veo_8s.mp4", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\e945854d-dd57-48a4-be40-1c748432e27f.mp4"),
    ("Section_B_信号机制与磷酸接力_Veo_8s.mp4", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\dfdb819b-7528-4dea-a3ca-b79002c2ce7f.mp4"),
    ("Section_C_制剂应用与纯度质检_Veo_8s.mp4", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\738469ab-5dc5-4eae-b585-7ddc5c3e2a9d.mp4"),
]

for dst_name, src_path in ai_clips:
    dst_file = AI_CLIPS_DIR / dst_name
    shutil.copy2(src_path, dst_file)
    # 抽取 4.0s 预览图
    preview_img = AI_CLIPS_DIR / f"{dst_file.stem}_preview.png"
    subprocess.run(["ffmpeg", "-y", "-ss", "4.0", "-i", str(dst_file), "-vframes", "1", str(preview_img)], capture_output=True)
    print(f"Copied AI Clip -> {dst_file}")
    print(f"Generated Preview -> {preview_img}")

print("All AI clips archived successfully.")
