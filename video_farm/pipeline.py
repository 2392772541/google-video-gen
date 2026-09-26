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
    IntentDetector,
    ContinuityAnchors
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

def extract_tail_anchor_frame(
    video_path: Union[str, Path],
    out_img_path: Optional[Union[str, Path]] = None,
    offset_frames: int = 4
) -> Path:
    """
    智能提取视频尾部稳定帧（Tail Anchor Frame）作为下一个连续镜头的起始关键帧。
    自动避开末尾 0.1~0.3s 可能出现的编码黑场或停顿，优先保证主体构图完整稳定。
    """
    vpath = Path(video_path).resolve()
    if not vpath.exists():
        raise FileNotFoundError(f"视频文件不存在: {vpath}")

    if not out_img_path:
        out_img_path = vpath.parent / f"{vpath.stem}_tail_anchor.png"
    else:
        out_img_path = Path(out_img_path).resolve()

    out_img_path.parent.mkdir(parents=True, exist_ok=True)

    success = False
    try:
        cap = cv2.VideoCapture(str(vpath))
        if cap.isOpened():
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                # 倒数第 offset_frames 帧
                target_idx = max(0, total_frames - max(1, offset_frames) - 1)
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
                ret, frame = cap.read()
                if ret and frame is not None:
                    # 校验是否为纯黑帧
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    mean_val = float(cv2.mean(gray)[0])
                    if mean_val < 6.0 and target_idx > 10:
                        # 往前探寻有效彩色帧
                        for back_step in [8, 14, 20, 26]:
                            alt_idx = max(0, total_frames - back_step)
                            cap.set(cv2.CAP_PROP_POS_FRAMES, alt_idx)
                            r2, f2 = cap.read()
                            if r2 and f2 is not None and float(cv2.mean(cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY))[0]) >= 6.0:
                                frame = f2
                                break

                    is_ok, buf = cv2.imencode(".png", frame)
                    if is_ok:
                        with open(out_img_path, "wb") as out_f:
                            out_f.write(buf)
                        success = True
        cap.release()
    except Exception as e:
        success = False

    if not success or not out_img_path.exists():
        # ffmpeg 兜底抽取
        try:
            cmd = [
                "ffmpeg", "-y",
                "-sseof", "-0.25",
                "-i", str(vpath),
                "-update", "1",
                "-q:v", "2",
                str(out_img_path)
            ]
            subprocess.run(cmd, capture_output=True)
        except Exception:
            pass

    if not out_img_path.exists():
        # 终极保底：第 0 帧
        subprocess.run([
            "ffmpeg", "-y", "-i", str(vpath), "-vframes", "1", "-q:v", "2", str(out_img_path)
        ], capture_output=True, check=True)

    return out_img_path



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

            # 解析 8 宫格动力学运镜 (camera_motion) 与咬合模式
            user_motion = getattr(shot, "camera_motion", None) or getattr(shot.visual, "camera_motion", None) or getattr(shot.visual, "motion_preset", None)
            continuity_mode = getattr(shot, "continuity", None) or getattr(shot.visual, "continuity", "cut")

            if shot.visual.provider == "direct_cut" or user_motion == "static":
                vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}"
            else:
                if user_motion in ("zoom_in", "zoom_out", "pan_left", "pan_right", "crane_up", "tilt_down", "orbit"):
                    ptype = user_motion
                elif continuity_mode in ("last_frame", "continue"):
                    ptype = "zoom_in"
                else:
                    motion_presets = ["zoom_in", "pan_left", "crane_up", "pan_right", "zoom_out", "tilt_down", "orbit"]
                    ptype = motion_presets[preset_idx % len(motion_presets)]

                if ptype == "zoom_in":
                    s0, s1 = 1.00, 1.07
                    vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})/2',fps={fps}"
                elif ptype == "zoom_out":
                    s0, s1 = 1.07, 1.00
                    vf = f"scale='iw*({s0}-({s0}-{s1})*t/{dur_sec})':'ih*({s0}-({s0}-{s1})*t/{dur_sec})':eval=frame,crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})/2',fps={fps}"
                elif ptype == "pan_left":
                    sc = 1.08
                    x0, x1 = 0.55, 0.45
                    vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-{h})/2',fps={fps}"
                elif ptype == "pan_right":
                    sc = 1.08
                    x0, x1 = 0.45, 0.55
                    vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-{h})/2',fps={fps}"
                elif ptype == "crane_up":
                    sc = 1.08
                    y0, y1 = 0.55, 0.45
                    vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})*({y0}+({y1}-{y0})*t/{dur_sec})',fps={fps}"
                elif ptype == "tilt_down":
                    sc = 1.08
                    y0, y1 = 0.45, 0.55
                    vf = f"scale=iw*{sc}:ih*{sc},crop={w}:{h}:'(in_w-{w})/2':'(in_h-{h})*({y0}+({y1}-{y0})*t/{dur_sec})',fps={fps}"
                elif ptype == "orbit":
                    s0, s1 = 1.01, 1.06
                    x0, x1 = 0.47, 0.53
                    vf = f"scale='iw*({s0}+({s1}-{s0})*t/{dur_sec})':'ih*({s0}+({s1}-{s0})*t/{dur_sec})':eval=frame,crop={w}:{h}:'(in_w-{w})*({x0}+({x1}-{x0})*t/{dur_sec})':'(in_h-{h})/2',fps={fps}"
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

        # 4. 渲染各镜头画面切片 (支持连续性衔接 & 关键帧锚定)
        clips = []
        for idx, shot in enumerate(spec.tracks.video_track):
            pct = 40 + int(35 * (idx + 1) / len(spec.tracks.video_track))
            continuity_mode = getattr(shot, "continuity", None) or getattr(shot.visual, "continuity", "cut")

            # 连续性衔接处理：支持 continue (尾帧接力)、re_anchor (防漂移重锚)、anchor (首尾插值)
            if idx > 0 and continuity_mode in ("last_frame", "continue") and len(clips) > 0:
                prev_clip = clips[idx - 1]
                if prev_clip and Path(prev_clip).exists():
                    tail_frame_path = self.cache_dir / f"tail_anchor_{spec.tracks.video_track[idx-1].id}.png"
                    try:
                        extract_tail_anchor_frame(prev_clip, tail_frame_path, offset_frames=4)
                        shot.visual.start_image = str(tail_frame_path)
                        shot.in_frame = str(tail_frame_path)
                        self.log("连续性衔接", pct, f"镜头 [{shot.id}] 启用尾帧接力：继承上一镜 [{spec.tracks.video_track[idx-1].id}] 尾部稳定帧作为首帧")
                    except Exception as e:
                        self.log("连续性警告", pct, f"提取上一镜尾帧异常: {e}，回退使用预设底图")
            elif continuity_mode == "re_anchor":
                # 防漂移重锚：重置为全局主体锚点，截断形态畸变累计
                if spec.continuity_anchors and spec.continuity_anchors.subject_anchor and Path(spec.continuity_anchors.subject_anchor).exists():
                    shot.visual.start_image = str(spec.continuity_anchors.subject_anchor)
                    shot.in_frame = str(spec.continuity_anchors.subject_anchor)
                    self.log("防漂移重锚", pct, f"镜头 [{shot.id}] 触发防漂移重锚：重置入点为全局主体锚点 [{Path(spec.continuity_anchors.subject_anchor).name}]")
            elif continuity_mode == "anchor":
                self.log("关键帧锚定", pct, f"镜头 [{shot.id}] 启用首尾双锚点插值约束：[首: {Path(shot.visual.start_image).name if shot.visual.start_image else '无'} -> 尾: {Path(shot.visual.end_image).name if shot.visual.end_image else '无'}]")

            self.log("视觉切片", pct, f"渲染镜头 [{shot.id}] ({shot.duration:.2f}s, {shot.visual.provider}, 模式: {continuity_mode})...")
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

    def prepare_adaptive_images(
        self,
        image_paths: List[Path | str],
        force_crop_grid: bool = False,
        target_res: tuple = (1920, 1080)
    ) -> List[Path]:
        valid_paths = [Path(p) for p in image_paths if Path(p).exists()]
        if not valid_paths:
            return []
        if force_crop_grid:
            return self.auto_crop_grid_images(valid_paths, rows=2, cols=3, target_res=target_res)
        return valid_paths

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


def start_smart_pipeline_async(
    image_paths: List[str | Path],
    script_sentences: Optional[List[str]] = None,
    mode: str = "custom",
    aspect_ratio: str = "16:9",
    duration_mode: str = "auto",
    total_duration: float = 30.0,
    voice_mode: str = "auto",
    voice_name: str = "zh-CN-YunxiNeural",
    bgm_path: Optional[str | Path] = None,
    subtitle_mode: str = "auto",
    engine_choice: str = "local",
    grid_crop: Optional[bool] = None,
    output_master_mp4: Optional[str | Path] = None,
    work_dir: Optional[str | Path] = None,
    user_shots_override: Optional[List[Dict[str, Any]]] = None,
    continuity_anchors: Optional[Dict[str, Any]] = None
) -> str:
    """全模态自适应流水线启动器：彻底打破死板限制"""
    work_dir = Path(work_dir or (Path("video_farm_data") / f"pipe_{int(time.time())}_{uuid.uuid4().hex[:4]}"))
    work_dir.mkdir(parents=True, exist_ok=True)
    res_map = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    target_res = res_map.get(aspect_ratio, (1920, 1080))
    sb = StoryboardPipeline(work_dir)
    force_crop = grid_crop if grid_crop is not None else (mode == "storyboard_motion")
    provider = "direct_cut" if engine_choice == "direct_cut" else ("veo" if engine_choice == "flow_veo" else "ken_burns")
    processed_imgs = sb.prepare_adaptive_images(image_paths, force_crop_grid=force_crop, target_res=target_res)
    if not processed_imgs and not user_shots_override:
        raise ValueError("没有可用的图片或镜头素材")
    scripts = script_sentences or []
    shots: List[ShotSpec] = []
    if user_shots_override and len(user_shots_override) > 0:
        for idx, us in enumerate(user_shots_override):
            img_p = us.get("image_path") or us.get("in_frame")
            if not img_p or not Path(img_p).exists():
                img_p = str(processed_imgs[idx % len(processed_imgs)]) if processed_imgs else ""
            end_img_p = us.get("end_image") or us.get("end_image_path") or us.get("out_frame")
            txt = us.get("voice_text", "").strip()
            dur = float(us.get("duration", 2.5))
            motion = us.get("camera_motion") or us.get("motion", "zoom_in")
            continuity = us.get("continuity", "cut")
            shots.append(ShotSpec(
                id=f"shot_{idx+1:02d}",
                duration=dur,
                timing_policy="voice_driven" if (voice_mode != "none" and duration_mode == "auto") else "fixed",
                visual=VisualConfig(
                    provider=provider,
                    start_image=str(img_p) if img_p else None,
                    end_image=str(end_img_p) if (end_img_p and Path(end_img_p).exists()) else None,
                    camera_motion=motion,
                    motion_preset=motion,
                    continuity=continuity
                ),
                continuity=continuity,
                camera_motion=motion,
                in_frame=str(img_p) if img_p else None,
                out_frame=str(end_img_p) if (end_img_p and Path(end_img_p).exists()) else None,
                drift_warning=us.get("drift_warning"),
                locked=bool(us.get("locked", False)),
                voice_text=txt,
                subtitle_text=txt
            ))
    else:
        # 自适应多镜头与连续模式分配 (支持 30s/60s 连续短片与一镜到底)
        if mode == "one_shot_chain":
            num_shots = max(len(processed_imgs), 4)
            base_dur = total_duration / num_shots if total_duration > 0 else 7.5
            for idx in range(num_shots):
                cp = processed_imgs[idx % len(processed_imgs)] if processed_imgs else ""
                txt = scripts[idx] if idx < len(scripts) else ""
                continuity = "cut" if idx == 0 else "last_frame"
                shots.append(ShotSpec(
                    id=f"shot_{idx+1:02d}",
                    duration=base_dur,
                    timing_policy="voice_driven" if (voice_mode != "none" and duration_mode == "auto") else "fixed",
                    visual=VisualConfig(provider=provider, start_image=str(cp), motion_preset="slow_zoom_in", continuity=continuity),
                    continuity=continuity,
                    voice_text=txt,
                    subtitle_text=txt
                ))
        elif mode in ("long_series_30s", "long_series_60s"):
            target_total = 60.0 if mode == "long_series_60s" else 30.0
            num_shots = max(len(processed_imgs), 8 if mode == "long_series_60s" else 4)
            base_dur = (total_duration if total_duration > 0 else target_total) / num_shots
            motions = ["slow_zoom_in", "pan_left", "slow_zoom_out", "pan_right", "slow_zoom_in"]
            for idx in range(num_shots):
                cp = processed_imgs[idx % len(processed_imgs)] if processed_imgs else ""
                txt = scripts[idx] if idx < len(scripts) else ""
                motion = motions[idx % len(motions)]
                # 连续短剧策略：第1、3镜头切景(cut)，第2、4镜头动作接力(last_frame)，动静结合电影感强
                continuity = "last_frame" if (idx % 2 == 1) else "cut"
                shots.append(ShotSpec(
                    id=f"shot_{idx+1:02d}",
                    duration=base_dur,
                    timing_policy="voice_driven" if (voice_mode != "none" and duration_mode == "auto") else "fixed",
                    visual=VisualConfig(provider=provider, start_image=str(cp), motion_preset=motion, continuity=continuity),
                    continuity=continuity,
                    voice_text=txt,
                    subtitle_text=txt
                ))
        else:
            num_shots = len(processed_imgs)
            if duration_mode == "fixed" and total_duration > 0:
                base_dur = max(2.0, total_duration / max(1, num_shots))
            else:
                base_dur = 2.8
            motions = ["slow_zoom_in", "pan_left", "slow_zoom_out", "pan_right", "slow_zoom_in"]
            for idx, cp in enumerate(processed_imgs):
                txt = scripts[idx] if idx < len(scripts) else ""
                motion = motions[idx % len(motions)]
                shots.append(ShotSpec(
                    id=f"shot_{idx+1:02d}",
                    duration=base_dur,
                    timing_policy="voice_driven" if (voice_mode != "none" and duration_mode == "auto") else "fixed",
                    visual=VisualConfig(provider=provider, start_image=str(cp), motion_preset=motion, continuity="cut"),
                    continuity="cut",
                    voice_text=txt,
                    subtitle_text=txt
                ))
    has_voice = (voice_mode != "none") and any(bool(s.voice_text) for s in shots)
    has_sub = (subtitle_mode != "none") and any(bool(s.subtitle_text) for s in shots)
    final_bgm_path = None
    if bgm_path and Path(bgm_path).exists():
        final_bgm_path = str(bgm_path)
    ca_obj = None
    if continuity_anchors:
        ca_obj = ContinuityAnchors(
            subject_anchor=continuity_anchors.get("subject_anchor"),
            scene_anchor=continuity_anchors.get("scene_anchor"),
            style_anchor=continuity_anchors.get("style_anchor", "商业影视大片质感, 8K超高清, 细腻材质光影, 景深通透"),
            state_anchor=continuity_anchors.get("state_anchor"),
            locked=bool(continuity_anchors.get("locked", True))
        )

    spec = TimelineSpec(
        project_id=f"smart_{int(time.time())}",
        project_name="Smart Video Pipeline",
        aspect_ratio=aspect_ratio,
        resolution=list(target_res),
        fps=30,
        continuity_anchors=ca_obj,
        tracks=TracksSpec(
            video_track=shots,
            voice_track=VoiceTrack(enabled=has_voice, voice_name=voice_name, source="edge_tts"),
            bgm_track=BGMTrack(enabled=bool(final_bgm_path), file_path=final_bgm_path, volume=0.18, ducking=has_voice),
            subtitle_track=SubtitleTrack(enabled=has_sub, format="ass", style_preset="cinema_bottom")
        ),
        output_master_path=str(output_master_mp4 or (work_dir / "smart_master_1080p.mp4"))
    )
    return start_timeline_pipeline_async(spec, work_dir)


def start_animatic_pipeline_async(
    image_paths: List[str | Path],
    script_sentences: Optional[List[str]] = None,
    aspect_ratio: str = "16:9",
    total_duration: float = 20.0,
    voice_mode: str = "auto",
    voice_name: str = "zh-CN-YunxiNeural",
    bgm_path: Optional[str | Path] = None,
    user_shots_override: Optional[List[Dict[str, Any]]] = None,
    continuity_anchors: Optional[Dict[str, Any]] = None
) -> str:
    """极速动态分镜预演 (Animatic Preview):
    采用高精微运镜 + 真实TTS与BGM在数秒内合成出全片节奏预演视频，
    方便创作者在实际消耗 Veo 算力前验证运镜、对齐音频并检查节奏。
    """
    return start_smart_pipeline_async(
        image_paths=image_paths,
        script_sentences=script_sentences,
        mode="animatic_fast",
        aspect_ratio=aspect_ratio,
        duration_mode="fixed",
        total_duration=total_duration,
        voice_mode=voice_mode,
        voice_name=voice_name,
        bgm_path=bgm_path,
        subtitle_mode="auto",
        engine_choice="local",
        user_shots_override=user_shots_override,
        continuity_anchors=continuity_anchors
    )
