import os
import sys
import cv2
import numpy as np
from pathlib import Path

def calculate_similarity(img1, img2):
    # Resize img2 to match img1 if dimensions differ
    h, w = img1.shape[:2]
    if img2.shape[:2] != (h, w):
        img2 = cv2.resize(img2, (w, h), interpolation=cv2.INTER_AREA)
    
    # Grayscale
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    # Normalized Cross-Correlation
    corr = cv2.matchTemplate(gray1, gray2, cv2.TM_CCORR_NORMED)[0][0]
    
    # Mean Squared Error
    mse = np.mean((gray1.astype(float) - gray2.astype(float)) ** 2)
    
    # Peak Signal to Noise Ratio
    psnr = 10 * np.log10(255**2 / (mse + 1e-10)) if mse > 0 else 100.0
    
    return {"ncc": float(corr), "mse": float(mse), "psnr": float(psnr)}

def verify_video(video_path, start_path, end_path, out_dir="qa_output"):
    video_path = Path(video_path)
    start_path = Path(start_path)
    end_path = Path(end_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        return False
        
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"Error: Cannot open video: {video_path}")
        return False
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps if fps > 0 else 0
    
    print(f"=== 视频元数据 ===")
    print(f"路径: {video_path}")
    print(f"分辨率: {w}x{h} (宽高比: {w/h:.4f})")
    print(f"总帧数: {total_frames} | 帧率: {fps:.2f} | 时长: {duration:.2f}s")
    
    # Read first frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret, first_frame = cap.read()
    if not ret or first_frame is None:
        print("Error: Failed to read first frame")
        return False
        
    # Read last frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 1))
    ret, last_frame = cap.read()
    if not ret or last_frame is None:
        print("Error: Failed to read last frame")
        return False
        
    cap.release()
    
    first_frame_path = out_dir / "extracted_first_frame.png"
    last_frame_path = out_dir / "extracted_last_frame.png"
    cv2.imwrite(str(first_frame_path), first_frame)
    cv2.imwrite(str(last_frame_path), last_frame)
    print(f"已抽帧: 首帧 -> {first_frame_path}, 尾帧 -> {last_frame_path}")
    
    # Load original images
    orig_start = cv2.imread(str(start_path))
    orig_end = cv2.imread(str(end_path))
    
    if orig_start is None:
        print(f"Error: Cannot read start image: {start_path}")
        return False
    if orig_end is None:
        print(f"Error: Cannot read end image: {end_path}")
        return False
        
    # Comparisons
    first_vs_start = calculate_similarity(first_frame, orig_start)
    last_vs_end = calculate_similarity(last_frame, orig_end)
    last_vs_start = calculate_similarity(last_frame, orig_start) # check if last is just start
    
    print("\n=== 首尾帧相似度比对 ===")
    print(f"[首帧 vs start.png] NCC(归一化相关): {first_vs_start['ncc']:.4f} | PSNR: {first_vs_start['psnr']:.2f} dB")
    print(f"[尾帧 vs end.png]   NCC(归一化相关): {last_vs_end['ncc']:.4f} | PSNR: {last_vs_end['psnr']:.2f} dB")
    print(f"[尾帧 vs start.png] NCC(防重复参照): {last_vs_start['ncc']:.4f} | PSNR: {last_vs_start['psnr']:.2f} dB")
    
    # Judgment
    first_matched = first_vs_start['ncc'] > 0.80
    end_matched = last_vs_end['ncc'] > 0.75 and last_vs_end['ncc'] > last_vs_start['ncc']
    
    print("\n=== 判定结果 ===")
    print(f"首帧匹配: {'通过' if first_matched else '失败'}")
    print(f"尾帧匹配: {'通过' if end_matched else '失败'}")
    
    # Watermark inspection (bottom right 15%)
    corner_h, corner_w = int(h * 0.15), int(w * 0.15)
    corner = last_frame[h - corner_h : h, w - corner_w : w]
    corner_path = out_dir / "bottom_right_corner.png"
    cv2.imwrite(str(corner_path), corner)
    print(f"右下角裁剪保存至: {corner_path} (请人工确认是否有 ✦ 可见水印)")
    
    return first_matched and end_matched

if __name__ == "__main__":
    if len(sys.argv) >= 4:
        v_path = sys.argv[1]
        s_path = sys.argv[2]
        e_path = sys.argv[3]
        out = sys.argv[4] if len(sys.argv) > 4 else "qa_output"
        verify_video(v_path, s_path, e_path, out)
    else:
        print("Usage: python verify_frames.py <video.mp4> <start.png> <end.png> [out_dir]")
