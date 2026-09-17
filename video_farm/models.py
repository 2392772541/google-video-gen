from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class Profile:
    id: str
    name: str
    profile_path: str = ""
    account_label: str = ""
    status: str = "idle"  # idle, busy, cooldown, auth_expired, disabled, restricted
    watermark_mode: str = "unknown"  # clean, forced_visible, unknown
    last_heartbeat_at: Optional[str] = None
    last_success_at: Optional[str] = None
    last_failure_at: Optional[str] = None
    cooldown_until: Optional[str] = None
    enabled: bool = True
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

@dataclass
class Task:
    id: str
    prompt: str
    start_image_path: str = ""
    end_image_path: str = ""
    engine: str = "flow"  # "flow" (Google Flow 首尾帧/文生图) 或 "gemini" (Gemini 官方网页版)
    task_type: str = "video"  # "video" (视频生成) 或 "image" (图像生成)
    model: str = ""  # 视频模型: veo-lite, veo-fast, veo-quality, omni-flash 等; 图像模型: imagen4, nano-pro, nano2 等
    project_id: str = ""
    aspect_ratio: str = "9:16"
    duration_sec: int = 8
    status: str = "queued"  # queued, dispatching, running, verifying, completed, failed, retry_wait, cancelled
    assigned_profile_id: Optional[str] = None
    priority: int = 10
    retry_count: int = 0
    max_retries: int = 2
    require_clean_watermark: bool = False
    submit_time: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    start_time: Optional[str] = None
    finish_time: Optional[str] = None
    output_video_path: Optional[str] = None
    output_image_paths: Optional[str] = None  # JSON string of generated image paths, e.g. [".../img1.png"]
    first_frame_ncc: Optional[float] = None
    last_frame_ncc: Optional[float] = None
    last_vs_start_ncc: Optional[float] = None
    first_frame_matched: Optional[bool] = None
    last_frame_matched: Optional[bool] = None
    watermark_check: str = "unknown"  # clean, visible_veo, unknown
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    logs: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())
