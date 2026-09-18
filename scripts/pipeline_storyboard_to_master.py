# -*- coding: utf-8 -*-
"""
pipeline_storyboard_to_master.py
一键将分镜素材包转换为 1080p 商业级科学纪录片/故事板成片。
"""
import os
import sys
import argparse
from pathlib import Path

# 引入项目引擎
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from video_farm.pipeline import run_storyboard_pipeline_sync

def main():
    parser = argparse.ArgumentParser(description="分镜素材包一键全自动成片流水线")
    parser.add_argument("--dir", type=str, required=True, help="分镜素材文件夹路径")
    parser.add_argument("--duration", type=float, default=45.0, help="成片总时长（秒，默认45.0）")
    parser.add_argument("--bgm", type=str, default=r"E:\公司素材\音乐素材\未来先行 音乐\纪录片配乐-完整版.mp3", help="背景音乐路径")
    parser.add_argument("--output-name", type=str, default="科学纪录片_成片_1080p.mp4", help="成片文件名")
    parser.add_argument("--script", type=str, default=None, help="指定旁白文案（留空则自动从目录中的文本文件读取）")

    args = parser.parse_args()
    mat_dir = Path(args.dir).resolve()
    if not mat_dir.exists():
        print(f"[Error] 素材目录不存在: {mat_dir}")
        sys.exit(1)

    # 扫描图片：自适应根目录与常见子目录
    img_list = []
    scan_dirs = [mat_dir]
    for sub in ("images", "storyboard", "storyboards", "素材", "分镜"):
        if (mat_dir / sub).exists():
            scan_dirs.append(mat_dir / sub)

    for cdir in scan_dirs:
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            for p in cdir.glob(ext):
                ps = str(p).lower()
                if "output" not in ps and "temp" not in ps and "build" not in ps:
                    img_list.append(p)
        if img_list:
            break

    # 如果有 Storyboard_ 前缀的图片，优先作为分镜大图
    sb_imgs = [x for x in img_list if "storyboard" in x.name.lower()]
    if sb_imgs:
        img_list = sorted(sb_imgs)
    else:
        img_list = sorted(list(set(img_list)))

    if not img_list:
        print(f"[Error] 素材目录中未找到分镜图片: {mat_dir}")
        sys.exit(1)

    # 扫描或读取旁白
    script_text = args.script
    if not script_text:
        for txt_name in ("Narration_VO.txt", "voice.txt", "script.txt", "旁白.txt", "台词.txt", "文案.txt", "Narration.txt"):
            tf = mat_dir / txt_name
            if tf.exists():
                try:
                    script_text = tf.read_text(encoding="utf-8")
                    print(f"[Pipeline] 成功自动加载旁白文案: {tf.name}")
                    break
                except Exception as e:
                    print(f"[Warn] 读取 {tf.name} 失败: {e}")
        if not script_text:
            for tf in mat_dir.glob("*.txt"):
                if "output" not in str(tf).lower():
                    try:
                        script_text = tf.read_text(encoding="utf-8")
                        print(f"[Pipeline] 自动匹配文本文件作为旁白: {tf.name}")
                        break
                    except Exception:
                        pass

    if not script_text:
        print("[Warn] 未提供且未找到旁白文案，使用默认占位文案")
        script_text = "科学纪录片视觉呈现\n微观机制与应用效果解析"

    script_lines = [line.strip() for line in script_text.splitlines() if line.strip()]

    output_dir = mat_dir / "output"
    work_dir = mat_dir / "pipeline_temp"
    output_mp4 = output_dir / args.output_name

    print("=" * 60)
    print(" 🚀 启动分镜故事板全自动成片流水线")
    print(f" 📁 素材目录: {mat_dir}")
    print(f" 🖼️ 发现分镜底图: {len(img_list)} 张")
    print(f" 🎙️ 旁白句数: {len(script_lines)} 句")
    print(f" ⏱️ 目标时长: {args.duration} 秒")
    print(f" 🎯 目标成片: {output_mp4}")
    print("=" * 60)

    res_mp4 = run_storyboard_pipeline_sync(
        grid_images=img_list,
        script_sentences=script_lines,
        bgm_path=args.bgm if (args.bgm and Path(args.bgm).exists()) else None,
        output_master_mp4=output_mp4,
        work_dir=work_dir,
        total_duration=args.duration
    )

    print("=" * 60)
    print(f" 🎉 流水线执行完毕！最终成片已输出至:\n 👉 {res_mp4}")
    print("=" * 60)

if __name__ == "__main__":
    main()
