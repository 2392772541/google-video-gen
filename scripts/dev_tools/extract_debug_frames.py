import cv2, os
from PIL import Image

video_path = "video_farm_data/outputs/e0e64864-5c11-4566-a508-05db8e383754.mp4"
cap = cv2.VideoCapture(video_path)
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
fps = cap.get(cv2.CAP_PROP_FPS)

out_dir = "video_farm_data/debug_yougen"
os.makedirs(out_dir, exist_ok=True)

for sec in [0.0, 1.0, 2.0, 4.0, 6.0, 7.9]:
    frame_idx = int(sec * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if ret:
        cv2.imwrite(f"{out_dir}/frame_{sec:.1f}s.png", frame)
cap.release()
print(f"Extracted frames from {video_path} (total: {total_frames}, fps: {fps})")
