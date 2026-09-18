# -*- coding: utf-8 -*-
"""
video_farm.pipeline - 全自动视频生产管线引擎
整合分镜包自动化制作与产品包装大片制作，支持后台异步作业与状态追踪。
"""
from __future__ import annotations
import os
import sys
import time
import json
import math
import uuid
import shutil
import asyncio
import threading
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

import cv2
import numpy as np
from PIL import Image

try:
    import edge_tts
except ImportError:
    edge_tts = None


def get_media_duration(file_path: Path | str) -> float:
    file_path = str(file_path)
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


class PipelineJobManager:
    """流水线作业内存与状态管理器"""
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_job(self, job_type: str, params: Dict[str, Any]) -> str:
        job_id = f"job_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "type": job_type,
                "status": "running",
                "progress": 0,
                "step": "初始化",
                "message": "任务已创建，正在准备工作目录...",
                "logs": [],
                "created_at": time.time(),
                "completed_at": None,
                "error": None,
                "output_video": None,
                "params": params
            }
        return job_id

    def update_job(self, job_id: str, step: str, progress: int, message: str):
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job["step"] = step
                job["progress"] = progress
                job["message"] = message
                job["logs"].append({
                    "time": time.strftime("%H:%M:%S"),
                    "step": step,
                    "progress": progress,
                    "message": message
                })

    def complete_job(self, job_id: str, output_video: str):
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job["status"] = "completed"
                job["progress"] = 100
                job["step"] = "完成"
                job["message"] = "母片生产完毕，随时可预览下载"
                job["completed_at"] = time.time()
                job["output_video"] = output_video

    def fail_job(self, job_id: str, error: str):
        with self._lock:
            if job_id in self._jobs:
                job = self._jobs[job_id]
                job["status"] = "failed"
                job["step"] = "异常终止"
                job["error"] = error
                job["message"] = f"生产失败: {error}"
                job["completed_at"] = time.time()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._jobs.values())


PIPELINE_MANAGER = PipelineJobManager()


class StoryboardPipeline:
    """分镜故事板全自动端到端成片引擎"""

    def __init__(self, work_dir: Path | str, progress_callback: Optional[Callable[[str, int, str], None]] = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir = self.work_dir / "shots"
        self.audio_dir = self.work_dir / "audio"
        self.crops_dir = self.work_dir / "crops"
        for d in [self.shots_dir, self.audio_dir, self.crops_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback or (lambda step, pct, msg: None)

    def log(self, step: str, pct: int, msg: str):
        print(f"[{pct}%] [{step}] {msg}")
        self.progress_callback(step, pct, msg)

    def auto_crop_grid_images(
        self,
        grid_image_paths: List[Path | str],
        rows: int = 2,
        cols: int = 3,
        target_res: tuple = (1920, 1080),
        trim_edge_pct: float = 0.045
    ) -> List[Path]:
        self.log("切图解析", 10, f"开始自适应切分 {len(grid_image_paths)} 张分镜大图 (每张 {rows}x{cols} 宫格)...")
        cropped_paths = []
        shot_counter = 1

        for gpath in grid_image_paths:
            gpath = Path(gpath)
            if not gpath.exists():
                continue
            
            img = cv2.imdecode(np.fromfile(str(gpath), dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            h, w = img.shape[:2]
            
            # 如果原图高宽比本来就是 16:9 或接近单镜头，直接收纳
            aspect = w / h
            if 1.6 <= aspect <= 1.9 and (rows == 1 and cols == 1):
                resized = cv2.resize(img, target_res, interpolation=cv2.INTER_LANCZOS4)
                out_path = self.crops_dir / f"shot_{shot_counter:02d}.png"
                is_success, buf = cv2.imencode(".png", resized)
                if is_success:
                    with open(out_path, "wb") as f:
                        f.write(buf)
                    cropped_paths.append(out_path)
                    shot_counter += 1
                continue

            # 多宫格划分
            cell_w = w / cols
            cell_h = h / rows

            for r in range(rows):
                for c in range(cols):
                    x0 = int(c * cell_w)
                    x1 = int((c + 1) * cell_w)
                    y0 = int(r * cell_h)
                    y1 = int((r + 1) * cell_h)

                    pad_x = int((x1 - x0) * trim_edge_pct)
                    pad_y = int((y1 - y0) * trim_edge_pct)
                    
                    sub = img[y0 + pad_y: y1 - pad_y, x0 + pad_x: x1 - pad_x]
                    
                    sub_h, sub_w = sub.shape[:2]
                    target_ratio = target_res[0] / target_res[1]
                    current_ratio = sub_w / sub_h

                    if current_ratio > target_ratio:
                        desired_w = int(sub_h * target_ratio)
                        offset_x = (sub_w - desired_w) // 2
                        sub = sub[:, offset_x: offset_x + desired_w]
                    else:
                        desired_h = int(sub_w / target_ratio)
                        offset_y = (sub_h - desired_h) // 2
                        sub = sub[offset_y: offset_y + desired_h, :]

                    resized = cv2.resize(sub, target_res, interpolation=cv2.INTER_LANCZOS4)
                    out_path = self.crops_dir / f"shot_{shot_counter:02d}.png"
                    is_success, buf = cv2.imencode(".png", resized)
                    if is_success:
                        with open(out_path, "wb") as f:
                            f.write(buf)
                        cropped_paths.append(out_path)
                        shot_counter += 1

        self.log("切图解析", 25, f"成功切分生成 {len(cropped_paths)} 张标准高清分镜底图")
        return cropped_paths

    async def generate_narration_audio(
        self,
        script_sentences: List[str],
        voice: str = "zh-CN-YunxiNeural",
        rate: str = "+0%"
    ) -> tuple[Path, List[float]]:
        self.log("配音对齐", 35, f"开始生成 {len(script_sentences)} 句播音级旁白音频 (音色: {voice})...")
        sentence_durations = []
        sentence_files = []

        for idx, text in enumerate(script_sentences):
            clean_text = text.strip()
            if not clean_text:
                clean_text = "..."
            out_file = self.audio_dir / f"sentence_{idx:02d}.mp3"
            
            communicate = edge_tts.Communicate(clean_text, voice, rate=rate)
            await communicate.save(str(out_file))
            
            dur = get_media_duration(out_file)
            sentence_durations.append(dur)
            sentence_files.append(out_file)

        full_vo_file = self.audio_dir / "full_narration.mp3"
        concat_list_txt = self.audio_dir / "concat_audio.txt"
        with open(concat_list_txt, "w", encoding="utf-8") as f:
            for sf in sentence_files:
                f.write(f"file '{sf.resolve()}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_list_txt),
            "-c", "copy", str(full_vo_file)
        ], capture_output=True, check=True)

        total_audio_dur = get_media_duration(full_vo_file)
        self.log("配音对齐", 50, f"旁白合成完毕，总时长: {total_audio_dur:.2f} 秒")
        return full_vo_file, sentence_durations

    def compute_timeline(
        self,
        num_shots: int,
        target_duration: float = 45.0,
        fps: int = 25
    ) -> List[Dict[str, Any]]:
        total_frames = int(round(target_duration * fps))
        base_frames_per_shot = total_frames // num_shots
        remainder = total_frames % num_shots

        timeline = []
        cur_frame = 0
        cur_time = 0.0

        for i in range(num_shots):
            frames = base_frames_per_shot + (1 if i >= (num_shots - remainder) else 0)
            duration_sec = frames / float(fps)
            timeline.append({
                "shot_index": i,
                "start_frame": cur_frame,
                "num_frames": frames,
                "start_sec": cur_time,
                "duration_sec": duration_sec,
                "end_sec": cur_time + duration_sec
            })
            cur_frame += frames
            cur_time += duration_sec

        return timeline

    def render_ken_burns_clips(
        self,
        image_paths: List[Path],
        timeline: List[Dict[str, Any]],
        fps: int = 25
    ) -> List[Path]:
        self.log("运镜渲染", 60, f"正在并发渲染 {len(image_paths)} 个镜头微动效...")
        motion_presets = [
            {"type": "zoom_in", "s_start": 1.00, "s_end": 1.07},
            {"type": "pan_left", "scale": 1.05, "x_start": 0.54, "x_end": 0.46},
            {"type": "zoom_in", "s_start": 1.01, "s_end": 1.05},
            {"type": "pan_up", "scale": 1.05, "y_start": 0.54, "y_end": 0.46},
            {"type": "pan_right", "scale": 1.05, "x_start": 0.46, "x_end": 0.54},
            {"type": "zoom_out", "s_start": 1.06, "s_end": 1.00},
        ]

        rendered_clips = []
        for idx, img_path in enumerate(image_paths):
            tl = timeline[idx]
            dur_sec = tl["duration_sec"]
            out_clip = self.shots_dir / f"clip_{idx:02d}.mp4"
            
            preset = motion_presets[idx % len(motion_presets)]
            ptype = preset["type"]

            if ptype == "zoom_in":
                s0, s1 = preset["s_start"], preset["s_end"]
                vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)/2',fps={fps}"
            elif ptype == "zoom_out":
                s0, s1 = preset["s_start"], preset["s_end"]
                vf = f"scale='iw*({s0}-({s0}-{s1})*t/{dur_sec})':'ih*({s0}-({s0}-{s1})*t/{dur_sec})':eval=frame,crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)/2',fps={fps}"
            elif ptype == "pan_left":
                sc = preset["scale"]
                x0, x1 = preset["x_start"], preset["x_end"]
                vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)/2',fps={fps}"
            elif ptype == "pan_right":
                sc = preset["scale"]
                x0, x1 = preset["x_start"], preset["x_end"]
                vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-1080)/2',fps={fps}"
            elif ptype == "pan_up":
                sc = preset["scale"]
                y0, y1 = preset["y_start"], preset["y_end"]
                vf = f"scale=iw*{sc}:ih*{sc},crop=1920:1080:'(in_w-1920)/2':'(in_h-1080)*({y0}+({y1}-{y0})*t/{dur_sec})',fps={fps}"
            else:
                vf = f"scale=1920:1080,fps={fps}"

            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(img_path),
                "-t", f"{dur_sec:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                str(out_clip)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            rendered_clips.append(out_clip)

        self.log("运镜渲染", 75, f"运镜切片渲染完毕 (共 {len(rendered_clips)} 段)")
        return rendered_clips

    def build_ass_subtitles(
        self,
        sentences: List[str],
        timeline: List[Dict[str, Any]],
        output_ass: Path
    ):
        header = """[Script Info]
Title: Pipeline Auto Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,46,&H00FFFFFF,&H000000FF,&H000D0D0D,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,2,40,40,65,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        def fmt_ass(sec):
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            cs = int(round((sec - int(sec)) * 100))
            if cs >= 100:
                cs = 99
            return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

        events = []
        num_sentences = len(sentences)
        num_shots = len(timeline)
        shots_per_sentence = max(1, num_shots // num_sentences)

        for s_idx, text in enumerate(sentences):
            start_shot = s_idx * shots_per_sentence
            end_shot = min(num_shots - 1, (s_idx + 1) * shots_per_sentence - 1)
            if s_idx == num_sentences - 1:
                end_shot = num_shots - 1
            
            t_start = timeline[start_shot]["start_sec"]
            t_end = timeline[end_shot]["end_sec"] - 0.15
            clean_text = text.strip()
            events.append(f"Dialogue: 0,{fmt_ass(t_start)},{fmt_ass(t_end)},Default,,0,0,0,,{clean_text}")

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

    def assemble_final_master(
        self,
        clips: List[Path],
        narration_file: Path,
        bgm_file: Optional[Path],
        output_file: Path,
        ass_file: Optional[Path] = None,
        total_duration: float = 45.0
    ):
        self.log("母片压制", 85, "正在进行专业双轨避让混音与高清字幕压制...")
        concat_txt = self.work_dir / "concat_clips.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c.resolve()}'\n")

        ass_esc = str(ass_file.resolve()).replace("\\", "/").replace(":", "\\:") if ass_file else None
        fade_out_start = max(0.0, total_duration - 2.5)

        if bgm_file and Path(bgm_file).exists():
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-i", str(narration_file),
                "-i", str(bgm_file),
                "-filter_complex",
                (f"[0:v]ass='{ass_esc}'[v];" if ass_esc else "[0:v]copy[v];") +
                f"[1:a]volume=1.2[vo];"
                f"[2:a]volume=0.18,afade=t=out:st={fade_out_start:.2f}:d=2.5[bgm];"
                f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[v]", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-i", str(narration_file),
                "-filter_complex",
                f"[0:v]ass='{ass_esc}'[vout]" if ass_esc else "[0:v]copy[vout]",
                "-map", "[vout]", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]

        subprocess.run(cmd, capture_output=True, check=True)
        self.log("母片压制", 100, f"成片压制完成: {output_file.name}")


def start_storyboard_pipeline_async(
    grid_images: List[str | Path],
    script_sentences: List[str],
    bgm_path: Optional[str | Path],
    output_master_mp4: str | Path,
    work_dir: str | Path,
    total_duration: float = 45.0
) -> str:
    """启动后台异步流水线作业，返回 job_id"""
    job_id = PIPELINE_MANAGER.create_job("storyboard", {
        "num_images": len(grid_images),
        "num_sentences": len(script_sentences),
        "target_duration": total_duration,
        "output_path": str(output_master_mp4)
    })

    def _worker():
        try:
            def _cb(step, pct, msg):
                PIPELINE_MANAGER.update_job(job_id, step, pct, msg)

            pipeline = StoryboardPipeline(work_dir, progress_callback=_cb)
            
            # 1. 切图
            cropped = pipeline.auto_crop_grid_images(grid_images)
            if not cropped:
                raise RuntimeError("未检测到有效的分镜图片输入")

            # 2. TTS
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            vo_audio, _ = loop.run_until_complete(
                pipeline.generate_narration_audio(script_sentences)
            )
            loop.close()

            # 3. 时间轴
            timeline = pipeline.compute_timeline(len(cropped), target_duration=total_duration)

            # 4. 运镜
            clips = pipeline.render_ken_burns_clips(cropped, timeline)

            # 5. 字幕
            ass_path = pipeline.work_dir / "subtitles.ass"
            pipeline.build_ass_subtitles(script_sentences, timeline, ass_path)

            # 6. 母片
            out_p = Path(output_master_mp4)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            pipeline.assemble_final_master(clips, vo_audio, bgm_path, out_p, ass_path, total_duration)

            PIPELINE_MANAGER.complete_job(job_id, str(out_p))
        except Exception as e:
            import traceback
            err = f"{e}\n{traceback.format_exc()}"
            PIPELINE_MANAGER.fail_job(job_id, err)

    t = threading.Thread(target=_worker, daemon=True, name=f"Pipeline-{job_id}")
    t.start()
    return job_id


def run_storyboard_pipeline_sync(
    grid_images: List[str | Path],
    script_sentences: List[str],
    bgm_path: Optional[str | Path],
    output_master_mp4: str | Path,
    work_dir: str | Path,
    total_duration: float = 45.0,
    progress_cb: Optional[Callable[[str, int, str], None]] = None
) -> Path:
    pipeline = StoryboardPipeline(work_dir, progress_callback=progress_cb)
    cropped = pipeline.auto_crop_grid_images(grid_images)
    if not cropped:
        raise RuntimeError("未检测到有效的分镜图片输入")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    vo_audio, _ = loop.run_until_complete(
        pipeline.generate_narration_audio(script_sentences)
    )
    loop.close()

    timeline = pipeline.compute_timeline(len(cropped), target_duration=total_duration)
    clips = pipeline.render_ken_burns_clips(cropped, timeline)

    ass_path = pipeline.work_dir / "subtitles.ass"
    pipeline.build_ass_subtitles(script_sentences, timeline, ass_path)

    out_p = Path(output_master_mp4)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    pipeline.assemble_final_master(clips, vo_audio, bgm_path, out_p, ass_path, total_duration)
    return out_p
