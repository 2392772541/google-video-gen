# -*- coding: utf-8 -*-
"""
video_farm.pipeline - 全要素通用视频生产管线引擎 (AI Video Factory Engine)
支持多分支、多轨道、解耦式生产：
1. 意图自适应：支持无需分析直通执行 (PASSTHROUGH) 与全案规划 (REPLAN)
2. 音频解耦：无配音高保真音乐片 vs 播音级TTS配音对齐片
3. 视觉多模态：静态微运镜(Ken Burns)、Veo首尾帧片段、外部切片、产品展台复合
4. 轨道化时间线驱动：按 TimelineSpec 协议调度，无硬编码
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
from typing import List, Dict, Any, Optional, Callable, Union

import cv2
import numpy as np
from PIL import Image

try:
    import edge_tts
except ImportError:
    edge_tts = None

from .timeline_spec import (
    TimelineSpec,
    IntentSpec,
    ShotSpec,
    VisualConfig,
    TracksSpec,
    VoiceTrack,
    BGMTrack,
    SubtitleTrack,
    IntentDetector
)


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


class TimelineEngine:
    """通用时间线执行引擎：全要素支持任意分支组合"""

    def __init__(self, work_dir: Path | str, progress_callback: Optional[Callable[[str, int, str], None]] = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.shots_dir = self.work_dir / "shots"
        self.audio_dir = self.work_dir / "audio"
        self.cache_dir = self.work_dir / "cache"
        for d in [self.shots_dir, self.audio_dir, self.cache_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback or (lambda step, pct, msg: None)

    def log(self, step: str, pct: int, msg: str):
        print(f"[{pct}%] [{step}] {msg}")
        self.progress_callback(step, pct, msg)

    async def process_voice_track(self, spec: TimelineSpec) -> Dict[str, float]:
        """处理配音轨道，返回各镜头实际音频时长字典 {shot_id: duration_sec}"""
        vt = spec.tracks.voice_track
        shot_durations = {}
        if not vt.enabled:
            self.log("音频分支", 20, "检测到配音轨道未启用：采用无配音模式，跳过语音合成。")
            return shot_durations

        self.log("音频分支", 25, f"正在生成各镜头配音 (音色: {vt.voice_name}, 语速: {vt.rate})...")
        for idx, shot in enumerate(spec.tracks.video_track):
            text = (shot.voice_text or "").strip()
            if not text:
                continue

            audio_file = self.audio_dir / f"voice_{shot.id}.mp3"
            if edge_tts is not None:
                communicate = edge_tts.Communicate(text, vt.voice_name, rate=vt.rate)
                await communicate.save(str(audio_file))
                dur = get_media_duration(audio_file)
                shot_durations[shot.id] = dur
            else:
                self.log("音频警告", 25, "未安装 edge_tts，跳过生成")

        return shot_durations

    def render_visual_clip(
        self,
        shot: ShotSpec,
        target_res: tuple[int, int],
        fps: int = 30,
        preset_idx: int = 0
    ) -> Path:
        """根据镜头配置渲染单镜头视频切片"""
        out_clip = self.shots_dir / f"clip_{shot.id}.mp4"
        dur_sec = shot.duration
        w, h = target_res

        # 分支 1：外部已有视频片段或 Veo 预渲染视频
        if shot.visual.provider in ("clip", "veo") and shot.visual.clip_path:
            cpath = Path(shot.visual.clip_path)
            if cpath.exists():
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(cpath),
                    "-t", f"{dur_sec:.3f}",
                    "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", "-preset", "ultrafast",
                    str(out_clip)
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                return out_clip

        # 分支 2：静态高精微运镜 (Ken Burns)
        img_path = shot.visual.start_image or shot.visual.scene_image
        if img_path and Path(img_path).exists():
            # 预处理：自适应保持比例铺满目标画布 (Cover 缩放)，避免因原始尺寸小于目标导致 crop 崩溃
            prep_img = self.cache_dir / f"prep_{shot.id}.png"
            src_im = cv2.imdecode(np.fromfile(str(img_path), dtype=np.uint8), cv2.IMREAD_COLOR)
            if src_im is not None:
                sh, sw = src_im.shape[:2]
                scale_factor = max(w / sw, h / sh) * 1.12
                nw, nh = int(sw * scale_factor), int(sh * scale_factor)
                resized = cv2.resize(src_im, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
                # 居中裁切成稍大的工作底图 (w*1.1, h*1.1) 供给运镜
                bw, bh = int(w * 1.1), int(h * 1.1)
                ox = max(0, (nw - bw) // 2)
                oy = max(0, (nh - bh) // 2)
                base_crop = resized[oy:oy+bh, ox:ox+bw]
                is_ok, buf = cv2.imencode(".png", base_crop)
                if is_ok:
                    with open(prep_img, "wb") as f:
                        f.write(buf)
                    target_input = prep_img
                else:
                    target_input = Path(img_path)
            else:
                target_input = Path(img_path)

            motion_presets = [
                {"type": "zoom_in", "s_start": 1.00, "s_end": 1.06},
                {"type": "pan_left", "scale": 1.05, "x_start": 0.54, "x_end": 0.46},
                {"type": "zoom_in", "s_start": 1.01, "s_end": 1.05},
                {"type": "pan_right", "scale": 1.05, "x_start": 0.46, "x_end": 0.54},
                {"type": "zoom_out", "s_start": 1.06, "s_end": 1.00},
            ]
            preset = motion_presets[preset_idx % len(motion_presets)]
            ptype = preset["type"]

            if ptype == "zoom_in":
                s0, s1 = preset["s_start"], preset["s_end"]
                vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})/2',fps={fps}"
            elif ptype == "zoom_out":
                s0, s1 = preset["s_start"], preset["s_end"]
                vf = f"scale='iw*({s0}-({s0}-{s1})*t/{dur_sec})':'ih*({s0}-({s0}-{s1})*t/{dur_sec})':eval=frame,crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})/2',fps={fps}"
            elif ptype == "pan_left":
                sc = preset["scale"]
                x0, x1 = preset["x_start"], preset["x_end"]
                vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-{h})/2',fps={fps}"
            elif ptype == "pan_right":
                sc = preset["scale"]
                x0, x1 = preset["x_start"], preset["x_end"]
                vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-{h})/2',fps={fps}"
            else:
                vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}"

            cmd = [
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(target_input),
                "-t", f"{dur_sec:.3f}",
                "-vf", vf,
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
                str(out_clip)
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            return out_clip

        # 兜底：纯黑占位
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:d={dur_sec:.3f}:r={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            str(out_clip)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return out_clip

    def build_ass_subtitles(self, spec: TimelineSpec, timeline: List[Dict[str, Any]], output_ass: Path):
        """生成 ASS 电影字幕文件"""
        w, h = spec.resolution
        font_size = int(h * 0.046)
        margin_v = int(h * 0.065)

        header = f"""[Script Info]
Title: Timeline Engine Master Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei, {font_size}, &H00FFFFFF, &H000000FF, &H00000000, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 3, 2, 2, 30, 30, {margin_v}, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        def fmt_ass(sec: float) -> str:
            m = int(sec // 60)
            s = int(sec % 60)
            cs = int(round((sec - int(sec)) * 100))
            if cs >= 100:
                s += 1
                cs = 0
            h_ = int(m // 60)
            m = int(m % 60)
            return f"{h_}:{m:02d}:{s:02d}.{cs:02d}"

        events = []
        for tl in timeline:
            text = tl.get("text", "").strip()
            if not text:
                continue
            t0 = fmt_ass(tl["start_sec"])
            t1 = fmt_ass(tl["end_sec"])
            events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{text}")

        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

    def execute(self, spec: TimelineSpec) -> Path:
        """按照 TimelineSpec 全量执行视频生产"""
        t0 = time.time()
        self.log("意图研判", 5, f"项目: {spec.project_name} | 分析策略: {spec.intent.analysis_strategy}")

        # 1. 视听参数自适应准备
        target_res = tuple(spec.resolution)
        fps = spec.fps

        # 2. 配音轨道处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        shot_voice_durs = loop.run_until_complete(self.process_voice_track(spec))
        loop.close()

        # 3. 动态时间轴计算 (支持 voice_driven 与 fixed 混合)
        timeline = []
        cur_sec = 0.0
        for idx, shot in enumerate(spec.tracks.video_track):
            # 如果是人声驱动且生成了有效语音，且未锁定时间
            if shot.timing_policy == "voice_driven" and shot.id in shot_voice_durs and not spec.intent.locks.timing:
                actual_dur = max(shot_voice_durs[shot.id] + 0.4, shot.duration)
                shot.duration = actual_dur
            
            dur = shot.duration
            timeline.append({
                "shot_id": shot.id,
                "start_sec": cur_sec,
                "duration_sec": dur,
                "end_sec": cur_sec + dur,
                "text": shot.subtitle_text or shot.voice_text or ""
            })
            cur_sec += dur

        total_duration = cur_sec
        self.log("时间轴计算", 35, f"完成多轨道时间轴排期：总镜头数 {len(spec.tracks.video_track)}，总时长 {total_duration:.2f} 秒")

        # 4. 渲染各镜头画面切片
        clips = []
        for idx, shot in enumerate(spec.tracks.video_track):
            pct = 40 + int(35 * (idx + 1) / len(spec.tracks.video_track))
            self.log("视觉切片", pct, f"渲染镜头 [{shot.id}] ({shot.duration:.2f}s, {shot.visual.provider})...")
            clip_path = self.render_visual_clip(shot, target_res, fps=fps, preset_idx=idx)
            clips.append(clip_path)

        # 5. 音频装配
        full_vo_file = None
        if spec.tracks.voice_track.enabled:
            vo_files = []
            for shot in spec.tracks.video_track:
                vf = self.audio_dir / f"voice_{shot.id}.mp3"
                if vf.exists():
                    vo_files.append(vf)
            
            if vo_files:
                full_vo_file = self.audio_dir / "master_voice.mp3"
                concat_list_txt = self.audio_dir / "concat_voice.txt"
                with open(concat_list_txt, "w", encoding="utf-8") as f:
                    for vf in vo_files:
                        f.write(f"file '{vf.resolve()}'\n")
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_txt),
                    "-c", "copy", str(full_vo_file)
                ], capture_output=True, check=True)

        # 6. 字幕装配
        ass_path = None
        if spec.tracks.subtitle_track.enabled:
            ass_path = self.work_dir / "subtitles.ass"
            self.build_ass_subtitles(spec, timeline, ass_path)

        # 7. 母片总成合成 (Master Assembly)
        self.log("母片压制", 85, "开始专业母片压制...")
        concat_txt = self.work_dir / "concat_clips.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c.resolve()}'\n")

        ass_esc = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:") if ass_path else None
        bgm_p = spec.tracks.bgm_track.file_path if spec.tracks.bgm_track.enabled else None
        has_bgm = bgm_p and Path(bgm_p).exists()
        fade_out_start = max(0.0, total_duration - spec.tracks.bgm_track.fade_out_seconds)

        output_file = Path(spec.output_master_path or (self.work_dir / "final_master.mp4"))
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 场景 A：有配音 + 有背景音乐（双轨 Ducking 避让混音）
        if full_vo_file and has_bgm:
            duck_vol = spec.tracks.bgm_track.ducking_volume
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-i", str(full_vo_file),
                "-i", str(bgm_p),
                "-filter_complex",
                (f"[0:v]ass='{ass_esc}'[v];" if ass_esc else "[0:v]copy[v];") +
                f"[1:a]volume=1.2[vo];"
                f"[2:a]volume={duck_vol},afade=t=out:st={fade_out_start:.2f}:d={spec.tracks.bgm_track.fade_out_seconds}[bgm];"
                f"[vo][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "[v]", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]
        # 场景 B：无配音 + 仅背景音乐（纯音乐片，BGM 高保真全音量）
        elif (not full_vo_file) and has_bgm:
            norm_vol = spec.tracks.bgm_track.normal_volume
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-i", str(bgm_p),
                "-filter_complex",
                (f"[0:v]ass='{ass_esc}'[v];" if ass_esc else "[0:v]copy[v];") +
                f"[1:a]volume={norm_vol},afade=t=out:st={fade_out_start:.2f}:d={spec.tracks.bgm_track.fade_out_seconds}[aout]",
                "-map", "[v]", "-map", "[aout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]
        # 场景 C：有配音 + 无背景音乐
        elif full_vo_file and (not has_bgm):
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-i", str(full_vo_file),
                "-filter_complex",
                f"[0:v]ass='{ass_esc}'[vout]" if ass_esc else "[0:v]copy[vout]",
                "-map", "[vout]", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]
        # 场景 D：纯净无声音视频
        else:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_txt),
                "-filter_complex",
                f"[0:v]ass='{ass_esc}'[vout]" if ass_esc else "[0:v]copy[vout]",
                "-map", "[vout]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "9000k", "-preset", "fast",
                "-an",
                "-t", f"{total_duration:.3f}",
                str(output_file)
            ]

        subprocess.run(cmd, capture_output=True, check=True)
        elapsed = time.time() - t0
        self.log("母片完成", 100, f"成片就绪: {output_file.name} (耗时 {elapsed:.1f} 秒)")
        return output_file


# ---------------- 异步启动器与向后兼容适配器 ----------------

def start_timeline_pipeline_async(
    spec: TimelineSpec,
    work_dir: str | Path
) -> str:
    """以 TimelineSpec 启动后台通用流水线作业，返回 job_id"""
    job_id = PIPELINE_MANAGER.create_job("timeline", {
        "project_name": spec.project_name,
        "num_shots": len(spec.tracks.video_track),
        "has_voice": spec.tracks.voice_track.enabled,
        "has_bgm": spec.tracks.bgm_track.enabled,
        "has_subtitles": spec.tracks.subtitle_track.enabled,
        "output_path": str(spec.output_master_path or "")
    })

    def _worker():
        try:
            def _cb(step, pct, msg):
                PIPELINE_MANAGER.update_job(job_id, step, pct, msg)

            engine = TimelineEngine(work_dir, progress_callback=_cb)
            out_file = engine.execute(spec)
            PIPELINE_MANAGER.complete_job(job_id, str(out_file))
        except Exception as e:
            import traceback
            err = f"{e}\n{traceback.format_exc()}"
            PIPELINE_MANAGER.fail_job(job_id, err)

    t = threading.Thread(target=_worker, daemon=True, name=f"TimelineEngine-{job_id}")
    t.start()
    return job_id


# 向后兼容旧的 StoryboardPipeline 接口
class StoryboardPipeline:
    def __init__(self, work_dir: Path | str, progress_callback: Optional[Callable[[str, int, str], None]] = None):
        self.engine = TimelineEngine(work_dir, progress_callback)
        self.work_dir = self.engine.work_dir
        self.crops_dir = self.engine.work_dir / "crops"
        self.crops_dir.mkdir(parents=True, exist_ok=True)
        self.log = self.engine.log

    def auto_crop_grid_images(
        self,
        grid_image_paths: List[Path | str],
        rows: int = 2,
        cols: int = 3,
        target_res: tuple = (1920, 1080),
        trim_edge_pct: float = 0.045
    ) -> List[Path]:
        self.log("切图解析", 10, f"开始切分 {len(grid_image_paths)} 张分镜大图...")
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
                    resized = cv2.resize(sub, target_res, interpolation=cv2.INTER_LANCZOS4)
                    out_path = self.crops_dir / f"shot_{shot_counter:02d}.png"
                    is_success, buf = cv2.imencode(".png", resized)
                    if is_success:
                        with open(out_path, "wb") as f:
                            f.write(buf)
                        cropped_paths.append(out_path)
                        shot_counter += 1
        self.log("切图解析", 25, f"成功切分生成 {len(cropped_paths)} 张底图")
        return cropped_paths


def start_storyboard_pipeline_async(
    grid_images: List[str | Path],
    script_sentences: List[str],
    bgm_path: Optional[str | Path],
    output_master_mp4: str | Path,
    work_dir: str | Path,
    total_duration: float = 45.0
) -> str:
    """向后兼容的旧入口，内部自动封装为 TimelineSpec 提交"""
    sb = StoryboardPipeline(work_dir)
    cropped = sb.auto_crop_grid_images(grid_images)

    shots = []
    base_dur = total_duration / max(1, len(cropped))
    for idx, cp in enumerate(cropped):
        txt = script_sentences[idx] if idx < len(script_sentences) else ""
        shots.append(ShotSpec(
            id=f"shot_{idx+1:02d}",
            duration=base_dur,
            timing_policy="voice_driven" if len(script_sentences) > 0 else "fixed",
            visual=VisualConfig(provider="ken_burns", start_image=str(cp)),
            voice_text=txt,
            subtitle_text=txt
        ))

    spec = TimelineSpec(
        project_id=f"proj_{int(time.time())}",
        project_name="Storyboard Pipeline",
        aspect_ratio="16:9",
        resolution=[1920, 1080],
        tracks=TracksSpec(
            video_track=shots,
            voice_track=VoiceTrack(enabled=bool(script_sentences)),
            bgm_track=BGMTrack(enabled=bool(bgm_path), file_path=str(bgm_path) if bgm_path else None),
            subtitle_track=SubtitleTrack(enabled=bool(script_sentences))
        ),
        output_master_path=str(output_master_mp4)
    )

    return start_timeline_pipeline_async(spec, work_dir)
