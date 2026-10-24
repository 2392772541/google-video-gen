"""
Unified Model Capabilities Registry & Validation Layer.
Single source of truth loaded from MODEL_CAPABILITIES.json.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CAPABILITIES_PATH = BASE_DIR / "MODEL_CAPABILITIES.json"

_CACHED_DATA: Optional[Dict[str, Any]] = None


def get_capabilities_raw() -> Dict[str, Any]:
    global _CACHED_DATA
    if _CACHED_DATA is None:
        if not CAPABILITIES_PATH.is_file():
            raise FileNotFoundError(f"MODEL_CAPABILITIES.json not found at {CAPABILITIES_PATH}")
        with CAPABILITIES_PATH.open("r", encoding="utf-8") as f:
            _CACHED_DATA = json.load(f)
    return _CACHED_DATA


def reload_capabilities() -> Dict[str, Any]:
    global _CACHED_DATA
    _CACHED_DATA = None
    return get_capabilities_raw()


def get_channels() -> Dict[str, Any]:
    return get_capabilities_raw().get("channels", {})


def get_models() -> Dict[str, Any]:
    return get_capabilities_raw().get("models", {})


def get_model_spec(model_id: str) -> Optional[Dict[str, Any]]:
    models = get_models()
    clean_id = (model_id or "").strip().lower()
    # 剥离前缀，如 video-farm-8088::omni-flash -> omni-flash
    key = clean_id.split("::")[-1].strip()
    if key in models:
        return models[key]
    # 尝试模糊匹配映射
    if "quality" in key:
        return models.get("veo-quality")
    if "lite" in key:
        return models.get("veo-lite")
    if "fast" in key:
        return models.get("veo-fast")
    if "omni" in key or "flash" in key:
        return models.get("omni-flash")
    if "vids" in key:
        return models.get("vids")
    if "gemini" in key:
        return models.get("gemini")
    if "flow" in key:
        return models.get("flow") or models.get("omni-flash")
    return None


def get_canvas_models_payload() -> List[Dict[str, Any]]:
    """返回供无限画布模型选择器使用的分类分组模型列表"""
    models_dict = get_models()
    channels_dict = get_channels()
    output = []
    
    # 遍历各通道下的模型
    for ch_id, ch_info in channels_dict.items():
        ch_name = ch_info.get("display_name", ch_id)
        for m_id in ch_info.get("models", []):
            m_spec = models_dict.get(m_id)
            if not m_spec:
                continue
            output.append({
                "id": m_id,
                "object": "model",
                "name": m_spec.get("displayName", m_id),
                "channel_id": ch_id,
                "channel_name": ch_name,
                "provider": m_spec.get("provider", "unknown"),
                "badge": m_spec.get("badge", ""),
                "category": m_spec.get("category", "standard"),
                "capability": m_spec.get("capability", "video"),
                "duration_control_mode": m_spec.get("duration_control_mode", "upstream_default"),
                "supported_durations": m_spec.get("supportedDurations", []),
                "default_duration": m_spec.get("defaultDuration", 6),
                "max_references": m_spec.get("max_reference_images", 0),
                "supports_frames": m_spec.get("supportsFrames", False),
                "supports_ingredients": m_spec.get("supportsIngredients", False),
                "supported_resolutions": m_spec.get("supportedResolutions", ["720p"]),
                "supported_ratios": m_spec.get("supportedRatios", ["16:9", "9:16"]),
                "supported_output_counts": m_spec.get("supported_output_counts", [1]),
                "status": m_spec.get("validation_status", "verified"),
                "owned_by": "video-farm",
                "permission": []
            })
    return output
