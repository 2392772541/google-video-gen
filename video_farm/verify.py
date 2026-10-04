from __future__ import annotations
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional

def imread_unicode(file_path: str | Path) -> Optional[np.ndarray]:
    """Reads an image from a path that may contain non-ASCII (e.g. Chinese) characters on Windows."""
    try:
        p = Path(file_path).resolve()
        if not p.exists():
            return None
        data = np.fromfile(str(p), dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None

def imwrite_unicode(file_path: str | Path, img: np.ndarray) -> bool:
    """Writes an image to a path that may contain non-ASCII characters on Windows."""
    try:
        p = Path(file_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        ext = p.suffix or ".png"
        res, buf = cv2.imencode(ext, img)
        if res:
            buf.tofile(str(p))
            return True
        return False
    except Exception:
        return False

def calculate_similarity(img1: np.ndarray, img2: np.ndarray) -> Dict[str, float]:
    h, w = img1.shape[:2]
    if img2.shape[:2] != (h, w):
        img2 = cv2.resize(img2, (w, h), interpolation=cv2.INTER_AREA)
    
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    corr = cv2.matchTemplate(gray1, gray2, cv2.TM_CCORR_NORMED)[0][0]
    mse = np.mean((gray1.astype(float) - gray2.astype(float)) ** 2)
    psnr = 10 * np.log10(255**2 / (mse + 1e-10)) if mse > 0 else 100.0
    
    return {"ncc": float(corr), "mse": float(mse), "psnr": float(psnr)}

def detect_watermark_in_corner(corner_img: np.ndarray) -> bool:
    """
    Heuristic detection of the translucent 'Veo' or spark watermark in bottom-right corner.
    Returns True if watermark is detected, False otherwise.
    """
    if corner_img is None or corner_img.size == 0:
        return False
    
    gray = cv2.cvtColor(corner_img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.count_nonzero(edges) / edges.size
    return bool(edge_density > 0.02 and np.max(gray) > 160)

def verify_task_video(
    video_path: str | Path,
    start_image_path: Optional[str | Path] = None,
    end_image_path: Optional[str | Path] = None,
    qa_dir: str | Path = "video_farm_data/qa"
) -> Dict[str, Any]:
    video_path = Path(video_path).resolve()
    qa_dir = Path(qa_dir).resolve()
    qa_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        "success": False,
        "first_ncc": 0.0,
        "last_ncc": 0.0,
        "last_vs_start_ncc": 0.0,
        "first_matched": False,
        "last_matched": False,
        "watermark_status": "unknown",
        "qa_dir": str(qa_dir),
        "error": None
    }
    
    if not video_path.exists():
        result["error"] = f"视频文件未找到: {video_path}"
        return result
        
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        result["error"] = f"无法解码打开视频: {video_path}"
        return result
        
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if total_frames <= 0:
        cap.release()
        result["error"] = "视频帧数为0"
        return result
        
    # 读取视频第一帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    ret, first_frame = cap.read()
    if not ret or first_frame is None:
        cap.release()
        result["error"] = "读取首帧失败"
        return result
        
    # 读取视频最后一帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames - 1))
    ret, last_frame = cap.read()
    if not ret or last_frame is None:
        cap.release()
        result["error"] = "读取最终帧失败"
        return result
        
    cap.release()
    
    first_frame_path = qa_dir / "first_frame.png"
    last_frame_path = qa_dir / "last_frame.png"
    imwrite_unicode(first_frame_path, first_frame)
    imwrite_unicode(last_frame_path, last_frame)
    
    # 水印分析 (右下角 15% 区域)
    corner_h, corner_w = int(h * 0.15), int(w * 0.15)
    corner = last_frame[h - corner_h : h, w - corner_w : w]
    corner_path = qa_dir / "watermark_corner.png"
    imwrite_unicode(corner_path, corner)
    has_wm = detect_watermark_in_corner(corner)
    result["watermark_status"] = "visible_veo" if has_wm else "clean"

    # 首帧比对 (针对 AI 生成模型的真实动态插值，放宽至合理自然阈值 0.60)
    if start_image_path and Path(start_image_path).exists():
        orig_start = imread_unicode(start_image_path)
        if orig_start is not None:
            first_sim = calculate_similarity(first_frame, orig_start)
            result["first_ncc"] = round(first_sim["ncc"], 4)
            result["first_matched"] = result["first_ncc"] >= 0.60
        else:
            result["first_matched"] = True
    else:
        # 纯文生视频无首图输入，首帧默认有效
        result["first_matched"] = True
        result["first_ncc"] = 1.0

    # 尾帧比对 (如果存在尾帧输入，如 Google Flow 模式)
    if end_image_path and Path(end_image_path).exists():
        orig_end = imread_unicode(end_image_path)
        if orig_end is not None:
            last_sim = calculate_similarity(last_frame, orig_end)
            result["last_ncc"] = round(last_sim["ncc"], 4)
            orig_start = imread_unicode(start_image_path) if (start_image_path and Path(start_image_path).exists()) else None
            if orig_start is not None:
                last_vs_start_sim = calculate_similarity(last_frame, orig_start)
                result["last_vs_start_ncc"] = round(last_vs_start_sim["ncc"], 4)
                start_end_sim = calculate_similarity(orig_start, orig_end)
                start_end_ncc = round(start_end_sim["ncc"], 4)
                if start_end_ncc >= 0.85:
                    result["last_matched"] = result["last_ncc"] >= 0.75
                else:
                    result["last_matched"] = (result["last_ncc"] >= 0.75) and (result["last_ncc"] > result["last_vs_start_ncc"] + 0.005)
            else:
                result["last_matched"] = result["last_ncc"] >= 0.75
        else:
            result["error"] = f"无法读取尾帧图片: {end_image_path}"
            return result
    else:
        # 无尾帧输入（如 Gemini 网页版模式），尾帧不强求比对
        result["last_matched"] = True
        result["last_ncc"] = 1.0

    result["success"] = result["first_matched"] and result["last_matched"]
    return result
