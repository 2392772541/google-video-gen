# -*- coding: utf-8 -*-
"""
video_farm.timeline_spec - 工业级视频工程规范 (Timeline IR)
定义多分支正交解耦的视频生产数据协议，支持：
1. 分析策略解耦：AUTO(智能识别) / PASSTHROUGH(直通执行) / ASSIST(局部补全) / REPLAN(全案规划)
2. 权限锁保护(Locks)：锁定视觉、锁定文案、锁定秒数、锁定Prompt
3. 四维连续性锚点资产(Continuity Anchors / DNA Lock)：主体、场景、风格、状态
4. 五大镜头连接语义(Joint Connectors)：cut / continue / anchor / re_anchor / extend / auto
5. 多轨道架构(Tracks)：Video Track, Voice Track, BGM Track, Subtitle Track
6. 8宫格电影级运镜动力学矩阵：zoom_in, zoom_out, pan_left, pan_right, crane_up, tilt_down, orbit, static
7. 声明式 Job Spec 导入导出规范
"""
from __future__ import annotations
import os
import re
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


class ContinuityAnchors(BaseModel):
    """四维连续性锚点资产 (DNA Lock)
    解决长视频 (30s/50s/1分钟连续剧、产品大片) 跨镜头主体、场景、风格与动作状态的漂移问题。
    """
    subject_anchor: Optional[str] = Field(default=None, description="主体锚点: 人物脸部/产品包装图/Logo/核心物体")
    scene_anchor: Optional[str] = Field(default=None, description="场景锚点: 统一环境背景/光影色温/空间基准")
    style_anchor: Optional[str] = Field(
        default="商业影视大片质感, 8K超高清, 细腻材质光影, 景深通透",
        description="风格锚点: 视觉基调与画质标准"
    )
    state_anchor: Optional[str] = Field(
        default=None,
        description="状态锚点: 当前物体位置/朝向/持物手势基准，防止前后镜头道具错位跳变"
    )
    locked: bool = Field(default=True, description="是否全局锁定四维锚点资产")

    def build_continuity_prompt_prefix(self) -> str:
        """构建统一注入各分镜头的强一致性 Prompt 前缀"""
        parts = []
        if self.style_anchor:
            parts.append(f"风格要求: {self.style_anchor}")
        if self.subject_anchor:
            parts.append("保持主体身份轮廓与核心视觉特征严格一致，禁止变异")
        if self.scene_anchor:
            parts.append("保持环境空间布局与光照色温自然连续")
        if self.state_anchor:
            parts.append(f"状态基准: {self.state_anchor}")
        return " | ".join(parts)


class VisualConfig(BaseModel):
    """镜头级视觉生成器配置"""
    provider: str = Field(
        default="ken_burns",
        description="veo | ken_burns | product_composite | clip | static | direct_cut"
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
    camera_motion: Optional[str] = "zoom_in"  # 8 宫格动力学运镜: zoom_in, zoom_out, pan_left, pan_right, crane_up, tilt_down, orbit, static
    camera_intent: Optional[str] = "highlight" # highlight(突出主体), reveal(展示全貌), explore(环视漫游), sculpt(立体雕塑), focus(凝视特写)
    motion_preset: Optional[str] = "slow_zoom_in"
    continuity: Optional[str] = "cut"  # cut | continue (或 last_frame) | anchor | re_anchor | extend | auto


class ShotSpec(BaseModel):
    """单个镜头规范"""
    id: str
    duration: float = 2.5
    timing_policy: str = Field(
        default="voice_driven",
        description="voice_driven(人声撑开时长) | fixed(固定秒数) | bgm_beat(节拍卡点)"
    )
    visual: VisualConfig = Field(default_factory=VisualConfig)
    continuity: str = Field(
        default="cut",
        description="cut(独立机位切镜) | continue(尾帧接力) | last_frame(兼容尾帧接力) | anchor(首尾关键帧插值) | re_anchor(防漂移重锚) | extend(模型续写) | auto(自动推导)"
    )
    camera_motion: Optional[str] = "zoom_in"  # 8 宫格运镜快捷字段
    in_frame: Optional[str] = None           # 入点参考图路径 (首帧)
    out_frame: Optional[str] = None          # 出点参考图路径 (尾帧)
    drift_warning: Optional[str] = None      # 漂移风险警告信息 (当连续接力>=2次时自动提示)
    locked: bool = False                     # 镜头锁定 (重新全案生成时跳过本镜)
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
    project_id: str = ""
    project_name: str = "Untitled Project"
    aspect_ratio: str = "16:9"         # 16:9 | 9:16 | 1:1
    resolution: List[int] = [1920, 1080]
    fps: int = 30
    intent: IntentSpec = Field(default_factory=IntentSpec)
    continuity_anchors: ContinuityAnchors = Field(default_factory=ContinuityAnchors)
    tracks: TracksSpec = Field(default_factory=TracksSpec)
    output_master_path: Optional[str] = None

    def total_estimated_duration(self) -> float:
        return sum(s.duration for s in self.tracks.video_track)

    def export_job_spec(self) -> Dict[str, Any]:
        """导出声明式 Video Job Spec (方便一键复制分享或第三方调用)"""
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_job_spec(cls, data: Dict[str, Any]) -> TimelineSpec:
        """从声明式 Video Job Spec 反序列化还原，全面兼容简版与标准版"""
        d = dict(data)
        if not d.get("project_id"):
            d["project_id"] = f"proj_{int(time.time())}"
        tracks = d.get("tracks")
        if isinstance(tracks, dict):
            v_list = tracks.pop("video", None) or tracks.get("video_track", [])
            clean_shots = []
            for idx, item in enumerate(v_list):
                if isinstance(item, dict):
                    it = dict(item)
                    if "id" not in it:
                        it["id"] = it.get("shot_id") or f"shot_{idx+1:02d}"
                    if isinstance(it.get("continuity"), dict):
                        it["continuity"] = it["continuity"].get("mode") or it["continuity"].get("type") or "cut"
                    if "visual" not in it:
                        it["visual"] = {
                            "source_type": "image" if it.get("image_path") else "generate",
                            "start_image": it.get("image_path") or it.get("in_frame"),
                            "end_image": it.get("end_image") or it.get("out_frame"),
                            "prompt": it.get("prompt") or it.get("voice_text") or "",
                            "camera_motion": it.get("camera_motion") or it.get("motion") or "zoom_in",
                            "continuity": it.get("continuity") or "cut"
                        }
                    elif isinstance(it["visual"], dict):
                        vis = dict(it["visual"])
                        if isinstance(vis.get("continuity"), dict):
                            vis["continuity"] = vis["continuity"].get("mode") or vis["continuity"].get("type") or "cut"
                        it["visual"] = vis
                    clean_shots.append(it)
                else:
                    clean_shots.append(item)
            tracks["video_track"] = clean_shots
        return cls(**d)


class IntentDetector:
    """智能素材意图识别器：自动判断是否需要分析，识别输入类型，生成交互式推荐方案"""

    @staticmethod
    def inspect_input(
        input_dir_or_files: Union[str, Path, List[Union[str, Path]]],
        user_explicit_instruction: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        根据输入目录或文件集合，输出自动研判报告与推荐 IntentSpec 与分镜预案 (Shots Plan)
        """
        report = {
            "valid": True,
            "source_dir": "",
            "has_existing_spec": False,
            "has_paired_frames": False,
            "has_grid_storyboard": False,
            "has_raw_products": False,
            "has_video_clips": False,
            "has_voice_script": False,
            "has_bgm": False,
            "recommended_strategy": "AUTO",
            "recommended_mode": "ai_commercial", # ai_commercial | storyboard_motion | media_montage
            "mode_title": "AI商业大片重塑模式",
            "confidence": 0.9,
            "summary_text": "",
            "details": [],
            "images": [],
            "videos": [],
            "audios": [],
            "scripts": [],
            "script_lines": [],
            "continuity_anchors": {
                "subject_anchor": None,
                "scene_anchor": None,
                "style_anchor": "商业影视大片质感, 8K超高清, 细腻材质光影, 景深通透",
                "state_anchor": None,
                "locked": True
            },
            "suggested_shots": []
        }

        path_list: List[Path] = []
        if isinstance(input_dir_or_files, (str, Path)):
            p = Path(input_dir_or_files)
            if p.is_dir():
                report["source_dir"] = str(p.resolve())
                for root, dirs, files in os.walk(str(p)):
                    r_lower = root.lower()
                    if any(x in r_lower for x in ["output", "temp", "pipeline_temp", "cache", ".git", ".idea"]):
                        continue
                    for f in files:
                        path_list.append(Path(root) / f)
            elif p.exists():
                report["source_dir"] = str(p.parent.resolve())
                path_list = [p]
        else:
            for item in input_dir_or_files:
                ip = Path(item)
                if ip.exists():
                    if ip.is_dir():
                        for root, _, files in os.walk(str(ip)):
                            r_lower = root.lower()
                            if any(x in r_lower for x in ["output", "temp", "pipeline_temp", "cache"]):
                                continue
                            for f in files:
                                path_list.append(Path(root) / f)
                    else:
                        path_list.append(ip)

        if not path_list:
            report["valid"] = False
            report["summary_text"] = "未在指定路径中找到任何有效素材文件，请检查路径是否正确。"
            return report

        img_exts = { ".png", ".jpg", ".jpeg", ".webp", ".bmp" }
        video_exts = { ".mp4", ".mov", ".mkv", ".avi", ".webm" }
        audio_exts = { ".mp3", ".wav", ".aac", ".m4a", ".flac" }
        txt_exts = { ".txt", ".md", ".json" }

        for f in path_list:
            ext = f.suffix.lower()
            name_lower = f.name.lower()
            if ext in img_exts:
                report["images"].append({
                    "name": f.name,
                    "path": str(f.resolve()),
                    "stem": f.stem
                })
            elif ext in video_exts:
                report["videos"].append({
                    "name": f.name,
                    "path": str(f.resolve())
                })
            elif ext in audio_exts:
                report["audios"].append({
                    "name": f.name,
                    "path": str(f.resolve())
                })
                if any(k in name_lower for k in ["bgm", "music", "配乐", "背景音乐", "纪录片配乐", "完整版"]):
                    report["has_bgm"] = True
            elif ext in txt_exts:
                report["scripts"].append({
                    "name": f.name,
                    "path": str(f.resolve())
                })
                if not report["script_lines"]:
                    try:
                        content = f.read_text(encoding="utf-8").strip()
                        if content:
                            lines = [re.sub(r"^[0-9]+[、.·s]*", "", l.strip()) for l in content.splitlines() if l.strip()]
                            lines = [l for l in lines if not l.startswith("#") and len(l) > 1]
                            if lines:
                                report["script_lines"] = lines
                                report["has_voice_script"] = True
                    except Exception:
                        pass

        # 1. 检查是否存在已有 spec 文件
        for f in path_list:
            if f.name.lower() in ("timeline_spec.json", "timeline.json", "job_spec.json"):
                report["has_existing_spec"] = True
                report["recommended_strategy"] = "PASSTHROUGH"
                report["recommended_mode"] = "media_montage"
                report["mode_title"] = "直通时间线装配模式"
                report["confidence"] = 1.0
                report["summary_text"] = f"发现现成工程规范文件 ({f.name})，系统可直接直通装配交付，无需重复分析。"
                report["details"].append("规范驱动生产：完全遵循已有 TimelineSpec 轨道与镜头设定。")
                return report

        # 2. 检查是否有首尾帧对 (01_start, 01_end)
        starts = [img for img in report["images"] if "start" in img["name"].lower()]
        ends = [img for img in report["images"] if "end" in img["name"].lower()]
        if len(starts) > 0 and len(starts) == len(ends):
            report["has_paired_frames"] = True
            report["recommended_strategy"] = "PASSTHROUGH"
            report["recommended_mode"] = "ai_commercial"
            report["mode_title"] = "首尾帧精准约束生成模式"
            report["confidence"] = 0.95
            report["summary_text"] = f"检测到 {len(starts)} 组标准配对的首尾帧图片，最适合采用 Google Flow / Veo 首尾帧插值生成。"
            report["details"].append(f"成对首尾帧：{len(starts)} 对已就绪，确保运动起点与收束终点绝对受控。")
            if starts:
                report["continuity_anchors"]["subject_anchor"] = starts[0]["path"]
                report["continuity_anchors"]["style_anchor"] = "首尾关键帧电影级插值渲染"

        # 3. 检查是否有网格图 (如 6宫格、storyboard)
        for img in report["images"]:
            nl = img["name"].lower()
            if any(k in nl for k in ["storyboard", "grid", "6ba", "分镜", "宫格"]):
                report["has_grid_storyboard"] = True
                report["details"].append(f"检测到分镜板图集素材: {img['name']}")

        # 4. 检查是否有产品包装图
        for img in report["images"]:
            nl = img["name"].lower()
            if any(k in nl for k in ["产品", "包装", "效果图", "原粉", "液剂", "粉剂", "bottle", "box", "product", "纳铠甲", "捷邦", "氨基寡糖", "超免蛋白", "调理剂", "促保利素", "优根优苗"]):
                report["has_raw_products"] = True
                report["details"].append(f"检测到产品核心实景包装图: {img['name']}")
                if not report["continuity_anchors"]["subject_anchor"]:
                    report["continuity_anchors"]["subject_anchor"] = img["path"]
                    report["continuity_anchors"]["scene_anchor"] = "科技感商业摄影展台与微观场景"
                    report["continuity_anchors"]["state_anchor"] = "产品居中平稳陈列，微距慢动作流光掠过"

        if report["videos"]:
            report["has_video_clips"] = True
            report["details"].append(f"检测到现成视频切片: {len(report['videos'])} 个")

        # 综合决策推荐模式
        if report["has_paired_frames"]:
            report["recommended_mode"] = "ai_commercial"
            report["mode_title"] = "AI商业大片模式 (Veo首尾帧驱动)"
            report["recommended_strategy"] = "PASSTHROUGH"
            report["summary_text"] = f"识别到 {len(starts)} 组已成对的首尾帧素材，推荐直接由 Veo 多账号调度生成高清视频并混音成片。"
        elif report["has_raw_products"] and not report["has_grid_storyboard"]:
            report["recommended_mode"] = "ai_commercial"
            report["mode_title"] = "AI商业大片模式 (场景扩展+大片质感)"
            report["recommended_strategy"] = "REPLAN"
            report["summary_text"] = f"检测到 {len(report['images'])} 款产品包装实景图，建议采用【AI商业大片模式】制作场景底图与大片运镜，生成16:9高清宣传片。"
            report["details"].append("拒绝简单绿地贴图：建议结合生图大片底图生成 + 原生包装保护 + 运动光影。")
        elif report["has_grid_storyboard"]:
            report["recommended_mode"] = "storyboard_motion"
            report["mode_title"] = "科学分镜动效模式 (宫格切图+毫秒运镜)"
            report["recommended_strategy"] = "ASSIST"
            report["summary_text"] = f"检测到分镜板宫格大图与文案，建议采用【科学分镜动效模式】执行智能网格切图、TTS配音与Ken Burns电影级运镜。"
            report["details"].append("智能识别网格排布，对齐播音级语音和电影级双语字幕。")
        elif report["has_video_clips"]:
            report["recommended_mode"] = "media_montage"
            report["mode_title"] = "多片段自由混剪模式 (重组缝合)"
            report["recommended_strategy"] = "AUTO"
            report["summary_text"] = f"检测到多段现成媒体文件 ({len(report['videos'])} 视频, {len(report['images'])} 图片)，推荐进行自由重排、BGM避让配乐与字幕混剪。"
        else:
            report["recommended_mode"] = "ai_commercial"
            report["mode_title"] = "AI多模态自适应模式"
            report["summary_text"] = f"检测到 {len(report['images'])} 个图像素材，支持自由设定时长、配音音色与BGM生成成片。"

        # 默认回填主体锚点
        if not report["continuity_anchors"]["subject_anchor"] and report["images"]:
            report["continuity_anchors"]["subject_anchor"] = report["images"][0]["path"]
            report["continuity_anchors"]["scene_anchor"] = "统一影视环境布局与专业照明"

        # 生成分镜头预案 (Shots Plan) - 升级版连续性与 8 宫格运镜
        shots = []
        imgs = report["images"]
        script_lines = report["script_lines"]
        num_shots = len(imgs) if imgs else 6
        if num_shots > 18:
            num_shots = 18

        # 8 宫格动力学运镜循环列表
        camera_motions = ["zoom_in", "pan_left", "crane_up", "tilt_down", "pan_right", "orbit", "zoom_out", "static"]
        consecutive_continues = 0

        for i in range(num_shots):
            shot_id = f"shot_{i+1:02d}"
            img_info = imgs[i % len(imgs)] if imgs else None
            txt = script_lines[i] if i < len(script_lines) else (img_info["stem"] if img_info else f"镜头 {i+1} 核心视觉呈现")
            motion = camera_motions[i % len(camera_motions)]

            if i == 0:
                continuity = "cut"
                consecutive_continues = 0
                drift_warn = None
            elif report["has_paired_frames"]:
                continuity = "anchor"
                consecutive_continues = 0
                drift_warn = None
            else:
                if consecutive_continues >= 2:
                    continuity = "re_anchor"
                    consecutive_continues = 0
                    drift_warn = "⚠️ 已连续接力 2 次，建议在此重新锚定主体 DNA，防止形态与光影漂移"
                else:
                    continuity = "continue"
                    consecutive_continues += 1
                    drift_warn = None

            shots.append({
                "id": shot_id,
                "name": f"镜头 #{i+1}",
                "image_name": img_info["name"] if img_info else "未指定图片",
                "image_path": img_info["path"] if img_info else "",
                "in_frame": img_info["path"] if img_info else "",
                "out_frame": "",
                "duration": 2.5,
                "voice_text": txt,
                "motion": motion,
                "camera_motion": motion,
                "continuity": continuity,
                "drift_warning": drift_warn,
                "locked": False,
                "provider": "ken_burns" if report["recommended_mode"] == "storyboard_motion" else "veo"
            })

        report["suggested_shots"] = shots
        return report
