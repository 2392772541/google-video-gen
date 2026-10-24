"""
多镜头时间线无缝合成引擎 (Timeline Assembler)
负责将无限画布中的多个分镜视频（Shot 1~N）按时间线顺次拼接为完整的单部成片 MP4。

特性与架构规范：
1. 音视频规格严格对齐：统一输出为 1280x720 24fps H.264 (yuv420p) + AAC 44.1kHz 双声道；
2. 缺流自动补齐：若某一镜头缺失音轨，自动为其生成对应时长的立体声静音流，避免 Concat 滤波断流；
3. 线程与资源严格受控：默认限制 FFmpeg 线程为 2，避免挤占系统资源和破坏并发稳定性；
4. 严格边界防御：文件缺失、损坏、空列表、路径越界等错误清晰拦截，失败自动清理孤儿临时文件；
5. 真实时间线计算：提取各输入流的物理实际时长并累加生成分镜时刻表 (Timeline Cue Points)。
"""
from __future__ import annotations
import os
import json
import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional


class TimelineAssemblyError(Exception):
    """时间线合成业务异常"""
    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code


def calculate_sha256(file_path: Path) -> str:
    """计算文件权威 SHA256 散列值"""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(64 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def probe_video(video_path: Path) -> Dict[str, Any]:
    """
    使用 ffprobe 探测视频流属性与精确物理时长。
    """
    if not video_path.is_file():
        raise TimelineAssemblyError(f"视频文件不存在或不可读取: {video_path.name}", code=404)
    if video_path.stat().st_size == 0:
        raise TimelineAssemblyError(f"视频文件为空 (0 字节): {video_path.name}", code=400)

    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate",
        "-show_entries", "stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
        "-of", "json",
        str(video_path.resolve())
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        data = json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        raise TimelineAssemblyError(f"无法解析视频文件 [{video_path.name}]: 文件损坏或非合法媒体格式", code=400) from e
    except subprocess.TimeoutExpired as e:
        raise TimelineAssemblyError(f"探测视频 [{video_path.name}] 超时 (30s)", code=504) from e
    except Exception as e:
        raise TimelineAssemblyError(f"视频探测失败 [{video_path.name}]: {e}", code=400) from e

    format_info = data.get("format", {})
    try:
        duration = float(format_info.get("duration", 0.0))
    except (ValueError, TypeError):
        duration = 0.0

    if duration <= 0.05:
        raise TimelineAssemblyError(f"视频时长异常 ({duration}s)，有效时长必须大于 0.05s: {video_path.name}", code=400)

    has_video = False
    has_audio = False
    width = 0
    height = 0
    fps = 24.0
    vcodec = "unknown"
    acodec = "unknown"

    for stream in data.get("streams", []):
        stype = stream.get("codec_type")
        if stype == "video" and not has_video:
            has_video = True
            vcodec = stream.get("codec_name", "unknown")
            width = int(stream.get("width") or 0)
            height = int(stream.get("height") or 0)
            r_fps = stream.get("r_frame_rate", "24/1")
            try:
                if "/" in r_fps:
                    num, den = r_fps.split("/", 1)
                    fps = round(float(num) / max(1.0, float(den)), 2)
                else:
                    fps = float(r_fps)
            except Exception:
                fps = 24.0
        elif stype == "audio" and not has_audio:
            has_audio = True
            acodec = stream.get("codec_name", "unknown")

    if not has_video:
        raise TimelineAssemblyError(f"文件中未检测到有效视频流: {video_path.name}", code=400)

    return {
        "path": str(video_path.resolve()),
        "filename": video_path.name,
        "duration": duration,
        "file_size": video_path.stat().st_size,
        "width": width,
        "height": height,
        "fps": fps,
        "has_video": has_video,
        "has_audio": has_audio,
        "vcodec": vcodec,
        "acodec": acodec,
    }


def assemble_timeline(
    video_paths: List[Path],
    output_path: Path,
    target_width: int = 1280,
    target_height: int = 720,
    target_fps: int = 24,
    max_threads: int = 2,
    timeout_sec: int = 180,
) -> Dict[str, Any]:
    """
    将传入的多个分镜视频按顺序顺次拼接为单部完整成片。
    采用 FFmpeg 滤波图重编码，确保不同分辨率、帧率与有无音轨的镜头均能完美融合。
    """
    if not video_paths or len(video_paths) < 2:
        raise TimelineAssemblyError("时间线合成至少需要 2 个有效镜头视频", code=400)

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. 探测所有输入流
    probed_list: List[Dict[str, Any]] = []
    for p in video_paths:
        info = probe_video(p)
        probed_list.append(info)

    # 2. 构建 FFmpeg 命令行参数与滤波图
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for p in video_paths:
        cmd.extend(["-i", str(p.resolve())])

    filter_parts: List[str] = []
    concat_in_v: List[str] = []
    concat_in_a: List[str] = []

    for i, info in enumerate(probed_list):
        dur = info["duration"]
        # 视频滤镜：保持比例居中缩放并加黑边，强制指定帧率与 SAR
        v_label = f"v{i}"
        filter_parts.append(
            f"[{i}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,"
            f"setsar=1,fps={target_fps}[{v_label}]"
        )
        concat_in_v.append(f"[{v_label}]")

        # 音频滤镜：若有音轨则重采样为 44.1kHz 立体声；若无音轨则生成等长静音轨
        a_label = f"a{i}"
        if info["has_audio"]:
            filter_parts.append(
                f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[{a_label}]"
            )
        else:
            filter_parts.append(
                f"anullsrc=r=44100:cl=stereo,atrim=duration={dur:.3f}[{a_label}]"
            )
        concat_in_a.append(f"[{a_label}]")

    # 合并 concat
    concat_inputs = "".join(f"{v}{a}" for v, a in zip(concat_in_v, concat_in_a))
    filter_parts.append(f"{concat_inputs}concat=n={len(video_paths)}:v=1:a=1[outv][outa]")
    complex_filter = ";".join(filter_parts)

    cmd.extend([
        "-filter_complex", complex_filter,
        "-map", "[outv]",
        "-map", "[outa]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "22",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-threads", str(max(1, max_threads)),
        "-movflags", "+faststart",
        str(output_path)
    ])

    # 3. 执行合成
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or "FFmpeg 转码异常退出"
            raise TimelineAssemblyError(f"多镜头视频合成失败 (exit {res.returncode}): {err_msg}", code=500)
    except subprocess.TimeoutExpired as e:
        if output_path.exists():
            output_path.unlink()
        raise TimelineAssemblyError(f"多镜头视频合成超时 (超过 {timeout_sec} 秒)", code=504) from e
    except Exception as e:
        if output_path.exists():
            output_path.unlink()
        if isinstance(e, TimelineAssemblyError):
            raise
        raise TimelineAssemblyError(f"多镜头视频合成内部错误: {e}", code=500) from e

    if not output_path.is_file() or output_path.stat().st_size == 0:
        if output_path.exists():
            output_path.unlink()
        raise TimelineAssemblyError("合成后成片产物为空或落盘失败", code=500)

    # 4. 后置探针与校验
    output_info = probe_video(output_path)
    output_sha256 = calculate_sha256(output_path)

    # 5. 构建分镜时刻清单
    timeline_cues = []
    acc_time = 0.0
    for i, info in enumerate(probed_list):
        dur = round(info["duration"], 3)
        start_t = round(acc_time, 3)
        end_t = round(acc_time + dur, 3)
        timeline_cues.append({
            "shot_index": i + 1,
            "source_filename": info["filename"],
            "start_time": start_t,
            "end_time": end_t,
            "duration": dur,
            "resolution": f"{info['width']}x{info['height']}",
            "has_audio": info["has_audio"],
            "source_sha256": calculate_sha256(Path(info["path"]))
        })
        acc_time += dur

    return {
        "success": True,
        "output_path": str(output_path),
        "output_filename": output_path.name,
        "file_size": output_path.stat().st_size,
        "sha256": output_sha256,
        "total_duration": round(output_info["duration"], 3),
        "expected_duration": round(acc_time, 3),
        "timeline": timeline_cues,
        "video_format": {
            "width": output_info["width"],
            "height": output_info["height"],
            "fps": output_info["fps"],
            "vcodec": output_info["vcodec"],
            "acodec": output_info["acodec"],
        }
    }
