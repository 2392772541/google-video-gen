# -*- coding: utf-8 -*-
"""
video_farm.timeline_spec - 工业级视频工程规范 (Timeline IR)
定义多分支正交解耦的视频生产数据协议，支持：
1. 分析策略解耦：AUTO(智能识别) / PASSTHROUGH(直通执行) / ASSIST(局部补全) / REPLAN(全案规划)
2. 权限锁保护(Locks)：锁定视觉、锁定文案、锁定秒数、锁定Prompt
3. 多轨道架构(Tracks)：Video Track, Voice Track, BGM Track, Subtitle Track
4. 镜头级独立生成器：Veo首尾帧 / Veo单图 / 静态高精微运镜 / 展台包装透视复合 / 外部素材切片
5. 时长驱动自由组合：旁白驱动 / 固定秒数 / 节拍卡点
"""
from __future__ import annotations
import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


class IntentLocks(BaseModel):
    """字段保护锁：规定AI可以动什么、绝对不能动什么"""
    visual: bool = False      # True = 严禁重绘或替换画面
    voice_text: bool = False  # True = 严禁改写或重拟旁白文案
    timing: bool = False      # True = 严禁调整镜头设定秒数
    prompt: bool = False      # True = 严禁AI修改Prompt


class IntentSpec(BaseModel):
    """用户意图与控制规范"""
    analysis_strategy: str = Field(
        default="AUTO",
        description="AUTO | PASSTHROUGH(直通不分析) | ASSIST(补全缺漏) | REPLAN(全案深度规划)"
    )
    confidence: float = 1.0   # 系统自动识别置信度 (0.0 ~ 1.0)
    user_instructions: Optional[str] = None
    locks: IntentLocks = Field(default_factory=IntentLocks)


class VisualConfig(BaseModel):
    """镜头级视觉生成器配置"""
    provider: str = Field(
        default="ken_burns",
        description="veo | ken_burns | product_composite | clip | static"
    )
    mode: str = Field(
        default="pan_zoom",
        description="interpolate(首尾帧) | start_frame(单图动态) | text_to_video(纯文生) | pan_zoom(微运镜) | stage_ncc(展台透视贴合) | cut(已有切片)"
    )
    start_image: Optional[str] = None
    end_image: Optional[str] = None
    product_image: Optional[str] = None
    scene_image: Optional[str] = None
    clip_path: Optional[str] = None
    prompt: Optional[str] = None
    motion_preset: Optional[str] = "slow_zoom_in"  # slow_zoom_in, slow_zoom_out, pan_left, pan_right, static


class ShotSpec(BaseModel):
    """单个镜头规范"""
    id: str
    duration: float = 2.5
    timing_policy: str = Field(
        default="voice_driven",
        description="voice_driven(人声撑开时长) | fixed(固定秒数) | bgm_beat(节拍卡点)"
    )
    visual: VisualConfig = Field(default_factory=VisualConfig)
    voice_text: Optional[str] = None
    subtitle_text: Optional[str] = None


class VoiceTrack(BaseModel):
    """人声旁白轨道（可为空、可自带音频、可TTS）"""
    enabled: bool = False
    source: str = Field(
        default="edge_tts",
        description="edge_tts | imported_audio | none"
    )
    voice_name: str = "zh-CN-YunxiNeural"
    rate: str = "+0%"
    volume: str = "+0%"
    imported_audio_path: Optional[str] = None


class BGMTrack(BaseModel):
    """背景音乐轨道（支持自动Ducking避让与末尾淡出）"""
    enabled: bool = False
    file_path: Optional[str] = None
    volume: float = 0.18
    ducking: bool = True               # 有人声时自动避让
    ducking_volume: float = 0.15       # 避让后音量
    normal_volume: float = 0.85        # 无人声/纯音乐模式全音量
    fade_out_seconds: float = 2.5


class SubtitleTrack(BaseModel):
    """字幕轨道（支持电影级ASS、居中大字或纯净关闭）"""
    enabled: bool = False
    format: str = "ass"                # ass | srt
    style_preset: str = "cinema_bottom" # cinema_bottom | modern_center | minimal


class TracksSpec(BaseModel):
    """多轨道组合架构"""
    video_track: List[ShotSpec] = Field(default_factory=list)
    voice_track: VoiceTrack = Field(default_factory=VoiceTrack)
    bgm_track: BGMTrack = Field(default_factory=BGMTrack)
    subtitle_track: SubtitleTrack = Field(default_factory=SubtitleTrack)


class TimelineSpec(BaseModel):
    """工业级全要素时间线规范 (Timeline IR)"""
    project_id: str
    project_name: str = "Untitled Project"
    aspect_ratio: str = "16:9"         # 16:9 | 9:16 | 1:1
    resolution: List[int] = [1920, 1080]
    fps: int = 30
    intent: IntentSpec = Field(default_factory=IntentSpec)
    tracks: TracksSpec = Field(default_factory=TracksSpec)
    output_master_path: Optional[str] = None

    def total_estimated_duration(self) -> float:
        return sum(s.duration for s in self.tracks.video_track)


class IntentDetector:
    """智能素材意图识别器：自动判断是否需要分析，识别输入类型"""

    @staticmethod
    def inspect_input(
        input_dir_or_files: Union[str, Path, List[Union[str, Path]]],
        user_explicit_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据输入目录或文件集合，输出自动研判报告与推荐 IntentSpec
        """
        report = {
            "has_existing_spec": False,
            "has_paired_frames": False,
            "has_grid_storyboard": False,
            "has_raw_products": False,
            "has_voice_script": False,
            "has_bgm": False,
            "recommended_strategy": "AUTO",
            "confidence": 0.9,
            "details": []
        }

        # 归一化路径
        path_list: List[Path] = []
        if isinstance(input_dir_or_files, (str, Path)):
            p = Path(input_dir_or_files)
            if p.is_dir():
                path_list = list(p.glob("*"))
            elif p.exists():
                path_list = [p]
        else:
            path_list = [Path(f) for f in input_dir_or_files if Path(f).exists()]

        file_names = [f.name.lower() for f in path_list]

        # 1. 检查是否存在已有 spec 文件
        for f in path_list:
            if f.name.lower() in ("timeline_spec.json", "timeline.json", "job_spec.json"):
                report["has_existing_spec"] = True
                report["recommended_strategy"] = "PASSTHROUGH"
                report["confidence"] = 1.0
                report["details"].append(f"发现现成时间轴规范: {f.name}，无需二次分析，直通执行。")
                return report

        # 2. 检查是否有首尾帧对 (01_start, 01_end)
        starts = [f for f in file_names if "start" in f]
        ends = [f for f in file_names if "end" in f]
        if len(starts) > 0 and len(starts) == len(ends):
            report["has_paired_frames"] = True
            report["recommended_strategy"] = "PASSTHROUGH"
            report["confidence"] = 0.95
            report["details"].append(f"识别到标准首尾帧对 ({len(starts)} 组)，直接构建精准插值流水线。")

        # 3. 检查是否有网格图 (如 6宫格、storyboard)
        for f in file_names:
            if "storyboard" in f or "grid" in f or "6ba" in f or "分镜" in f:
                report["has_grid_storyboard"] = True
                report["details"].append(f"检测到分镜板图集: {f}")

        # 4. 检查是否有产品包装图
        for f in file_names:
            if "产品" in f or "包装" in f or "效果图" in f or "bottle" in f or "box" in f:
                report["has_raw_products"] = True
                report["details"].append(f"检测到产品原图: {f}")

        # 5. 检查音频与文案
        for f in file_names:
            if f.endswith((".txt", ".md", ".json")) and ("script" in f or "文案" in f or "台词" in f or "voice" in f):
                report["has_voice_script"] = True
            if f.endswith((".mp3", ".wav", ".aac", ".m4a")) and ("bgm" in f or "music" in f or "音乐" in f):
                report["has_bgm"] = True

        # 决策归纳
        if report["has_paired_frames"]:
            report["recommended_strategy"] = "PASSTHROUGH"
        elif report["has_raw_products"] and not report["has_paired_frames"] and not report["has_voice_script"]:
            report["recommended_strategy"] = "REPLAN"
            report["confidence"] = 0.85
            report["details"].append("仅包含产品原图，需系统执行卖点分析、场景大片设计与分镜规划。")
        elif report["has_grid_storyboard"]:
            report["recommended_strategy"] = "ASSIST"
            report["confidence"] = 0.9
            report["details"].append("包含分镜板，仅需网格裁切与参数自适应装配。")
        else:
            report["recommended_strategy"] = "AUTO"

        return report
