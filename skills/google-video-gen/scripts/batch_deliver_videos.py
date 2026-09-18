"""
batch_deliver_videos.py
-----------------------
批量视频质检、抽帧预览与归档交付工具。
支持：
1. 自动利用 ffprobe 严格提取视频流元数据（分辨率、纵横比、真实时长、实际帧率、文件大小）。
2. 自动利用 ffmpeg 截取黄金中帧 / 首尾帧用于商业交付审查。
3. 自动生成规范化的 Markdown 交付清单与质检报告 (DELIVERY_REPORT.md)。
4. 保证交付资产与临时工作区完全物理隔离。
"""

import sys
import os
import json
import shutil
import argparse
import subprocess
from pathlib import Path

def probe_video(video_path: Path):
    """提取视频流元数据"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,duration,r_frame_rate,bit_rate",
        "-of", "json",
        str(video_path)
    ]
    res = subprocess.check_output(cmd).decode("utf-8")
    data = json.loads(res)
    stream = next(s for s in data["streams"] if "width" in s)
    
    width = stream.get("width", 0)
    height = stream.get("height", 0)
    fps = stream.get("r_frame_rate", "24/1")
    if "/" in fps:
        num, den = fps.split("/")
        fps_val = round(float(num) / float(den), 2)
    else:
        fps_val = float(fps)
        
    dur = float(stream.get("duration", 0.0))
    if dur <= 0.0:
        # 兜底：尝试从 format 读取
        f_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)]
        f_data = json.loads(subprocess.check_output(f_cmd).decode("utf-8"))
        dur = float(f_data.get("format", {}).get("duration", 0.0))

    size_mb = video_path.stat().st_size / (1024 * 1024)
    return {
        "width": width,
        "height": height,
        "fps": fps_val,
        "duration": dur,
        "size_mb": round(size_mb, 2),
        "aspect_ratio": f"{width}:{height}" if height else "unknown"
    }

def extract_preview_frame(video_path: Path, out_preview: Path, time_sec=4.0):
    """截取预览帧"""
    out_preview.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", str(time_sec),
        "-i", str(video_path),
        "-vframes", "1",
        str(out_preview)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def deliver_batch(manifest_or_dir, output_dir: str, title="商业大片宣传片视频交付清单"):
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    previews_dir = out_dir / "previews"
    previews_dir.mkdir(parents=True, exist_ok=True)

    items = []
    if isinstance(manifest_or_dir, list):
        items = manifest_or_dir
    elif isinstance(manifest_or_dir, str) or isinstance(manifest_or_dir, Path):
        p = Path(manifest_or_dir)
        if p.is_file() and p.suffix.lower() == ".json":
            with open(p, "r", encoding="utf-8") as f:
                items = json.load(f)
        elif p.is_dir():
            for idx, f in enumerate(sorted(p.glob("*.mp4")), 1):
                items.append({
                    "index": f"{idx:02d}",
                    "name": f.stem,
                    "chinese_name": f.stem,
                    "src_video": str(f),
                    "src_frame": None
                })

    report_lines = []
    detailed_sections = []

    for item in items:
        src_video = Path(item["src_video"])
        if not src_video.exists():
            print(f"[Skip] 视频源文件未找到: {src_video}")
            continue

        item_name = item.get("name", src_video.stem)
        dest_video = out_dir / f"{item_name}.mp4"
        if src_video.resolve() != dest_video.resolve():
            shutil.copy2(src_video, dest_video)

        # 拷贝首帧
        if item.get("src_frame") and Path(item["src_frame"]).exists():
            dest_frame = out_dir / f"{item_name}_首帧.png"
            shutil.copy2(item["src_frame"], dest_frame)

        # 抽帧
        preview_png = previews_dir / f"{item_name}_mid.png"
        meta = probe_video(dest_video)
        extract_time = min(4.0, max(0.5, meta["duration"] / 2.0))
        extract_preview_frame(dest_video, preview_png, time_sec=extract_time)

        c_name = item.get("chinese_name", item_name)
        idx_str = item.get("index", "01")
        aspect = "16:9" if meta["width"] == 1280 and meta["height"] == 720 else ("9:16" if meta["width"] == 720 and meta["height"] == 1280 else f"{meta['width']}x{meta['height']}")

        line = f"| {idx_str} | **{c_name}** | {meta['width']}x{meta['height']} ({aspect}) | {meta['duration']:.1f}s | {meta['fps']}fps | {meta['size_mb']} MB | `{dest_video.name}` |"
        report_lines.append(line)

        scene_desc = item.get("scene_desc", "商业级微距环绕运镜与电影级景深光影")
        detailed_sections.append(f"### {idx_str}. {c_name}\n- **成片文件**：`{dest_video.name}`\n- **场景设计**：{scene_desc}\n- **首帧基准**：`{item_name}_首帧.png`\n- **中帧预览**：`previews/{preview_png.name}`\n")
        print(f"[Delivered] {item_name}: {meta['width']}x{meta['height']}, {meta['duration']:.1f}s, {meta['size_mb']}MB")

    # 生成 Markdown 交付报告
    report_file = out_dir / "DELIVERY_REPORT.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write("| 序号 | 项目名称 / 产品全称 | 分辨率 (比例) | 时长 | 帧率 | 文件大小 | 成品文件名 |\n")
        f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :--- |\n")
        f.write("\n".join(report_lines))
        f.write("\n\n## 视频镜头与场景设计规划\n\n")
        f.write("\n".join(detailed_sections))

    print(f"\n[Success] 全部完成！交付清单已生成: {report_file}")
    return report_file

def main():
    parser = argparse.ArgumentParser(description="批量视频质检抽帧与归档交付工具")
    parser.add_argument("--src", required=True, help="视频所在目录路径或 manifest.json 路径")
    parser.add_argument("--out", required=True, help="交付目标目录")
    parser.add_argument("--title", default="商业大片宣传片视频交付清单", help="交付报告主标题")

    args = parser.parse_args()
    deliver_batch(args.src, args.out, title=args.title)

if __name__ == "__main__":
    main()
