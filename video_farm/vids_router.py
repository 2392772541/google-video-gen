# -*- coding: utf-8 -*-
"""
Google Vids Workflow & Continuous Generation API Router
"""
from __future__ import annotations
import os
import re
import tempfile
from starlette.background import BackgroundTask
from .local_security import local_file, media_type
import uuid
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Body, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, Response
import io
import zipfile
import csv
from datetime import datetime
from pydantic import BaseModel

import urllib.parse
from .models import Task
from . import db
from . import vids_workflow

router = APIRouter(prefix="/api/vids", tags=["Google Vids"])

# -------------------------------------------------------------
# 智能语义化命名与剪辑资产交付系统
# -------------------------------------------------------------
def sanitize_filename_part(s: str, max_len: int = 24) -> str:
    """清理文件名片段，移除非法字符并适度截断"""
    if not s or not isinstance(s, str):
        return ""
    # 替换换行、制表符、连续空格为单个下划线
    s = re.sub(r'[\r\n\t\s]+', '_', s.strip())
    # 移除非法字符 \ / : * ? " < > | 以及标点符号
    s = re.sub(r'[\/:*?"<>|\\，。！？；：“”‘’（）()、·]+', '_', s)
    s = re.sub(r'_+', '_', s).strip('_')
    if len(s) > max_len:
        s = s[:max_len].rstrip('_')
    return s


def build_semantic_shot_filename(shot: Dict[str, Any], wf: Optional[Dict[str, Any]] = None, ext: str = "mp4") -> str:
    """
    生成高度语义化、剪辑友好的标准化文件名
    格式: [序数01]_[分镜名]_[SceneX]_[运镜模式]_[画质]_[台词或Prompt核心摘要].[ext]
    例如: 01_镜头01_Scene1_首尾帧过渡_1080p_偏碱的土壤里磷容易与钙结合.mp4
    """
    seq = shot.get("sequence") or 1
    scene = shot.get("scene_index") or seq
    raw_name = shot.get("name") or f"Shot{seq}"
    # 如果名字以 "镜头 01" 开头，清理格式
    name = sanitize_filename_part(raw_name, 16)
    
    mode = shot.get("mode") or "text2video"
    mode_map = {
        "first_last_frame": "首尾帧过渡",
        "image2video": "图生视频",
        "text2video": "文生视频",
        "extend": "尾帧延续"
    }
    mode_cn = mode_map.get(mode, "视频")
    res = (shot.get("resolution") or (wf.get("resolution") if wf else "1080p") or "1080p").strip()
    
    # 优先提取台词，若无台词则提取提示词前段
    summary_raw = (shot.get("narration") or "").strip()
    if not summary_raw:
        summary_raw = (shot.get("prompt") or "").strip()
    summary = sanitize_filename_part(summary_raw, 22)
    
    parts = [f"{seq:02d}", name, f"Scene{scene}", mode_cn, res]
    if summary:
        parts.append(summary)
    
    filename = "_".join(p for p in parts if p)
    clean_ext = ext.lstrip(".").lower()
    if not filename.lower().endswith(f".{clean_ext}"):
        filename += f".{clean_ext}"
    return filename



DATA_ROOT = Path(__file__).resolve().parent.parent / "video_farm_data"
UPLOADS_VIDS_DIR = DATA_ROOT / "uploads/vids"
UPLOADS_VIDS_DIR.mkdir(parents=True, exist_ok=True)


class CreateWorkflowRequest(BaseModel):
    title: str
    doc_url: str = ""
    style_prompt: str = ""
    aspect_ratio: str = "16:9"
    duration_per_shot: int = 10
    resolution: str = "1080p"
    model_name: str = "Omni"
    engine: str = "vids"
    shots: Optional[List[Dict[str, Any]]] = None


class UpdateWorkflowRequest(BaseModel):
    title: Optional[str] = None
    doc_url: Optional[str] = None
    style_prompt: Optional[str] = None
    aspect_ratio: Optional[str] = None
    duration_per_shot: Optional[int] = None
    resolution: Optional[str] = None
    model_name: Optional[str] = None
    engine: Optional[str] = None
    status: Optional[str] = None


class CreateShotRequest(BaseModel):
    name: str
    prompt: str
    narration: str = ""
    duration: int = 10
    sequence: Optional[int] = None
    scene_index: Optional[int] = None
    mode: str = "text2video"
    image_url: str = ""
    end_image_url: str = ""
    resolution: str = "1080p"
    model_name: str = "Omni"
    engine: Optional[str] = None


class UpdateShotRequest(BaseModel):
    name: Optional[str] = None
    prompt: Optional[str] = None
    narration: Optional[str] = None
    duration: Optional[int] = None
    sequence: Optional[int] = None
    scene_index: Optional[int] = None
    mode: Optional[str] = None
    image_url: Optional[str] = None
    end_image_url: Optional[str] = None
    resolution: Optional[str] = None
    model_name: Optional[str] = None
    engine: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    video_url: Optional[str] = None
    error_message: Optional[str] = None
    task_id: Optional[str] = None


class ParseScriptRequest(BaseModel):
    script: str
    default_duration: int = 10
    style_preset: str = ""


class ReorderShotsRequest(BaseModel):
    shot_ids: List[str]


@router.get("/overview")
def get_vids_overview():
    wfs = db.list_vids_workflows()
    total_shots = 0
    completed_shots = 0
    for wf in wfs:
        total_shots += wf.get("total_shots", 0)
        completed_shots += wf.get("completed_shots", 0)
    return {
        "status": "online",
        "workflows_count": len(wfs),
        "total_shots": total_shots,
        "completed_shots": completed_shots,
        "presets_count": len(vids_workflow.PRESETS),
        "supported_resolutions": ["1080p", "720p"],
        "supported_models": ["Omni", "Veo"],
        "supported_modes": ["text2video", "image2video", "first_last_frame", "extend"]
    }


@router.get("/presets")
def get_vids_presets():
    return {
        "presets": list(vids_workflow.PRESETS.values())
    }


@router.post("/parse_script")
def parse_script(req: ParseScriptRequest):
    shots = vids_workflow.parse_script_to_shots(
        raw_text=req.script,
        default_duration=req.default_duration,
        style_preset=req.style_preset
    )
    return {
        "shots": shots,
        "count": len(shots)
    }


@router.get("/sample_import_json")
def get_sample_import_json():
    """返回包含 1080p、Omni、首尾帧/图生视频的标准示范 JSON"""
    return vids_workflow.SAMPLE_BATCH_IMPORT_DATA


@router.post("/batch_import")
def batch_import_json(payload: Dict[str, Any] = Body(...)):
    """
    批量导入 JSON 分镜资产：
    支持各种格式：
    1. { "workflow_id": "...", "import_mode": "new"|"append"|"replace", "data": ... }
    2. 直接传入包含 title, resolution, shots 的 workflow 字典
    3. 直接传入 shots 列表 [ { ... }, { ... } ]
    4. 带有 Markdown 代码块包裹的 JSON 字符串
    """
    target_wf_id = payload.get("workflow_id")
    import_mode = payload.get("import_mode") or ("new" if not target_wf_id else "append")
    ui_engine = payload.get("engine")
    if ui_engine:
        ui_engine = str(ui_engine).strip().lower()
        if ui_engine not in ("vids", "flow", "gemini"):
            ui_engine = "vids"
    
    raw_data = payload.get("data") if "data" in payload else payload
    
    target_wf = None
    if target_wf_id and import_mode != "new":
        target_wf = db.get_vids_workflow(target_wf_id)
        if not target_wf:
            import_mode = "new"

    normalized = vids_workflow.normalize_imported_workflow_json(
        raw_data,
        default_workflow=target_wf,
        default_engine=ui_engine
    )

    chosen_engine = ui_engine or normalized.get("engine") or (target_wf.get("engine") if target_wf else None) or "vids"

    if import_mode == "new" or not target_wf:
        wf = db.create_vids_workflow(
            title=normalized.get("title") or "批量导入工作流",
            doc_url=normalized.get("doc_url") or "https://docs.google.com/videos/d/1EXFiC89I2CzVObDNGCXejn-FYySYoaKPjRIG8Fa6nS4/edit",
            style_prompt=normalized.get("style_prompt") or "",
            aspect_ratio=normalized.get("aspect_ratio") or "16:9",
            duration_per_shot=normalized.get("duration_per_shot") or 10,
            resolution=normalized.get("resolution") or "1080p",
            model_name=normalized.get("model_name") or "Omni",
            engine=chosen_engine
        )
        wf_id = wf["id"]
        start_seq = 1
    else:
        wf_id = target_wf["id"]
        updates = {}
        if chosen_engine:
            updates["engine"] = chosen_engine
        if normalized.get("style_prompt"):
            updates["style_prompt"] = normalized["style_prompt"]
        if normalized.get("resolution"):
            updates["resolution"] = normalized["resolution"]
        if normalized.get("model_name"):
            updates["model_name"] = normalized["model_name"]
        if normalized.get("aspect_ratio"):
            updates["aspect_ratio"] = normalized["aspect_ratio"]
        if updates:
            db.update_vids_workflow(wf_id, updates)

        if import_mode == "replace":
            old_shots = db.list_vids_shots(wf_id)
            for os_item in old_shots:
                db.delete_vids_shot(os_item["id"])
            start_seq = 1
        else:
            existing_shots = db.list_vids_shots(wf_id)
            start_seq = (existing_shots[-1]["sequence"] + 1) if existing_shots else 1

    created_shots = []
    default_res = normalized.get("resolution") or "1080p"
    default_model = normalized.get("model_name") or "Omni"

    for idx, shot in enumerate(normalized.get("shots", []), start=start_seq):
        shot_eng = shot.get("engine") or chosen_engine or "vids"
        s = db.create_vids_shot(
            workflow_id=wf_id,
            name=shot.get("name") or f"镜头 {idx}",
            prompt=shot.get("prompt", ""),
            narration=shot.get("narration", ""),
            duration=shot.get("duration", 10),
            sequence=idx,
            scene_index=idx,
            mode=shot.get("mode", "text2video"),
            image_url=shot.get("image_url", ""),
            end_image_url=shot.get("end_image_url", ""),
            resolution=shot.get("resolution") or default_res,
            model_name=shot.get("model_name") or default_model,
            engine=shot_eng
        )
        created_shots.append(s)

    full_wf = db.get_vids_workflow(wf_id)

    auto_start = payload.get("auto_start")
    if auto_start is None and isinstance(raw_data, dict):
        auto_start = raw_data.get("auto_start")
    if auto_start is None:
        auto_start = True

    task_ids = []
    if auto_start and created_shots:
        for s in created_shots:
            tid = _enqueue_shot_task(s, full_wf)
            task_ids.append(tid)
        db.update_vids_workflow(wf_id, {"status": "generating"})
        full_wf = db.get_vids_workflow(wf_id)

    return {
        "success": True,
        "workflow": full_wf,
        "imported_count": len(created_shots),
        "import_mode": import_mode,
        "auto_started": bool(task_ids),
        "task_ids": task_ids,
        "message": f"成功导入 {len(created_shots)} 个镜头" + (f"，已自动启动并排队下发 {len(task_ids)} 个生成任务！" if task_ids else "。")
    }


@router.get("/workflows/{workflow_id}/export_json")
def export_workflow_json(workflow_id: str):
    """导出工作流为完整、可重用的规范 JSON"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    clean_shots = []
    for s in wf.get("shots", []):
        clean_shots.append({
            "name": s.get("name"),
            "sequence": s.get("sequence"),
            "scene_index": s.get("scene_index"),
            "mode": s.get("mode", "text2video"),
            "prompt": s.get("prompt", ""),
            "narration": s.get("narration", ""),
            "image_url": s.get("image_url", ""),
            "end_image_url": s.get("end_image_url", ""),
            "resolution": s.get("resolution", wf.get("resolution", "1080p")),
            "model_name": s.get("model_name", wf.get("model_name", "Omni")),
            "duration": s.get("duration", 10)
        })

    export_data = {
        "title": wf.get("title"),
        "doc_url": wf.get("doc_url", ""),
        "style_prompt": wf.get("style_prompt", ""),
        "aspect_ratio": wf.get("aspect_ratio", "16:9"),
        "resolution": wf.get("resolution", "1080p"),
        "model_name": wf.get("model_name", "Omni"),
        "duration_per_shot": wf.get("duration_per_shot", 10),
        "shots": clean_shots
    }
    return export_data


@router.post("/upload_asset")
async def upload_asset(file: UploadFile = File(...)):
    """上传本地首帧图、尾帧图或参考图"""
    orig_name = file.filename or "image.png"
    ext = Path(orig_name).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        raise HTTPException(400, "仅支持 PNG/JPEG/WebP/GIF 图片")
    file_id = f"vids_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = UPLOADS_VIDS_DIR / file_id
    size = 0
    try:
        with open(dest_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 32 * 1024 * 1024:
                    raise HTTPException(413, "图片不能超过 32 MiB")
                f.write(chunk)
        from PIL import Image
        with Image.open(dest_path) as img:
            img.verify()
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException): raise
        raise HTTPException(400, "上传文件不是有效图片")
    finally:
        await file.close()
    
    return {
        "success": True,
        "filename": file_id,
        "url": f"/api/vids/assets/{file_id}",
        "absolute_path": str(dest_path.resolve())
    }


@router.get("/assets/{filename}")
def get_vids_asset(filename: str):
    """获取上传的资产图片"""
    safe_name = Path(filename).name
    p = (UPLOADS_VIDS_DIR / safe_name).resolve()
    if not p.is_file() or UPLOADS_VIDS_DIR.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail="资产未找到")
    return FileResponse(str(p), media_type=media_type(p))


@router.get("/workflows")
def list_workflows():
    wfs = db.list_vids_workflows()
    return {"workflows": wfs}


@router.post("/workflows")
def create_workflow(req: CreateWorkflowRequest):
    wf_engine = getattr(req, "engine", "vids") or "vids"
    wf = db.create_vids_workflow(
        title=req.title,
        doc_url=req.doc_url,
        style_prompt=req.style_prompt,
        aspect_ratio=req.aspect_ratio,
        duration_per_shot=req.duration_per_shot,
        resolution=req.resolution,
        model_name=req.model_name,
        engine=wf_engine
    )
    if req.shots:
        for idx, shot in enumerate(req.shots, start=1):
            db.create_vids_shot(
                workflow_id=wf["id"],
                name=shot.get("name") or f"Shot {idx}",
                prompt=shot.get("prompt", ""),
                narration=shot.get("narration", ""),
                duration=shot.get("duration", req.duration_per_shot),
                sequence=shot.get("sequence", idx),
                scene_index=shot.get("scene_index", idx),
                mode=shot.get("mode", "text2video"),
                image_url=shot.get("image_url", shot.get("start_image_path", "")),
                end_image_url=shot.get("end_image_url", shot.get("end_image_path", "")),
                resolution=shot.get("resolution", req.resolution),
                model_name=shot.get("model_name", req.model_name),
                engine=shot.get("engine") or wf_engine
            )
    return db.get_vids_workflow(wf["id"])


@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return wf


@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, req: UpdateWorkflowRequest):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        db.update_vids_workflow(workflow_id, updates)
    return db.get_vids_workflow(workflow_id)


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    db.delete_vids_workflow(workflow_id)
    return {"success": True, "deleted_id": workflow_id}


@router.post("/workflows/{workflow_id}/shots")
def add_shot(workflow_id: str, req: CreateShotRequest):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    shots = db.list_vids_shots(workflow_id)
    next_seq = (shots[-1]["sequence"] + 1) if shots else 1
    seq = req.sequence or next_seq
    scene_idx = req.scene_index or seq
    shot = db.create_vids_shot(
        workflow_id=workflow_id,
        name=req.name,
        prompt=req.prompt,
        narration=req.narration,
        duration=req.duration,
        sequence=seq,
        scene_index=scene_idx,
        mode=req.mode,
        image_url=req.image_url,
        end_image_url=req.end_image_url,
        resolution=req.resolution,
        model_name=req.model_name
    )
    return shot


@router.put("/shots/{shot_id}")
def update_shot(shot_id: str, req: UpdateShotRequest):
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        db.update_vids_shot(shot_id, updates)
    return db.get_vids_shot(shot_id)


@router.delete("/shots/{shot_id}")
def delete_shot(shot_id: str):
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    db.delete_vids_shot(shot_id)
    return {"success": True, "deleted_shot_id": shot_id}


@router.post("/workflows/{workflow_id}/reorder")
def reorder_shots(workflow_id: str, req: ReorderShotsRequest):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    for idx, sid in enumerate(req.shot_ids, start=1):
        db.update_vids_shot(sid, {"sequence": idx, "scene_index": idx})
    return db.get_vids_workflow(workflow_id)


@router.get("/workflows/{workflow_id}/next_pending")
def get_next_pending_shot(workflow_id: str):
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    shots = wf.get("shots", [])
    for shot in shots:
        if shot.get("status") in ("pending", "failed"):
            return {"has_pending": True, "shot": shot, "workflow": wf}
    return {"has_pending": False, "shot": None, "workflow": wf}


@router.post("/shots/{shot_id}/progress")
def update_shot_progress(shot_id: str, payload: Dict[str, Any] = Body(...)):
    progress = payload.get("progress", 0)
    status = payload.get("status", "running")
    error_message = payload.get("error_message")
    updates = {"progress": progress, "status": status}
    if error_message is not None:
        updates["error_message"] = error_message
    db.update_vids_shot(shot_id, updates)
    return {"success": True}


@router.post("/shots/{shot_id}/complete")
def complete_shot(shot_id: str, payload: Dict[str, Any] = Body(...)):
    video_url = payload.get("video_url", "")
    db.update_vids_shot(shot_id, {
        "status": "completed",
        "progress": 100,
        "video_url": video_url,
        "error_message": ""
    })
    return {"success": True}


@router.post("/shots/{shot_id}/fail")
def fail_shot(shot_id: str, payload: Dict[str, Any] = Body(...)):
    error_msg = payload.get("error_message", "生成失败")
    db.update_vids_shot(shot_id, {
        "status": "failed",
        "error_message": error_msg
    })
    return {"success": True}


def _resolve_local_image_path(p_str: str) -> str:
    """标准化解析本地首尾帧图片绝对路径"""
    if not p_str or not isinstance(p_str, str):
        return ""
    p_str = p_str.strip().strip('"\'')
    if not p_str:
        return ""
    if p_str.startswith("file:///"):
        p_str = p_str[8:]
    elif p_str.startswith("file://"):
        p_str = p_str[7:]

    unquoted = urllib.parse.unquote(p_str).strip().strip('"\'')
    if unquoted.startswith("file:///"):
        unquoted = unquoted[8:]
    elif unquoted.startswith("file://"):
        unquoted = unquoted[7:]

    for candidate in [p_str, unquoted]:
        if "/media/file" in candidate and "path=" in candidate:
            parsed = urllib.parse.urlparse(candidate)
            qs = urllib.parse.parse_qs(parsed.query)
            if "path" in qs and qs["path"]:
                candidate = qs["path"][0].strip().strip('"\'')
                candidate = urllib.parse.unquote(candidate).strip().strip('"\'')
        if "/api/vids/assets/" in candidate:
            fname = candidate.split("/api/vids/assets/")[-1].split("?")[0]
            local_p = (UPLOADS_VIDS_DIR / fname).resolve()
            if local_p.exists():
                return str(local_p)
        p = Path(candidate)
        if p.exists() and p.is_file():
            return str(p.resolve())
    return unquoted or p_str


def _enqueue_shot_task(shot: Dict[str, Any], wf: Dict[str, Any]) -> str:
    """将分镜转换为底层的真实 Task 并写入 tasks 数据库进入队列调度"""
    raw_start = shot.get("image_url") or ""
    raw_end = shot.get("end_image_url") or ""
    start_path = _resolve_local_image_path(raw_start)
    end_path = _resolve_local_image_path(raw_end)
    
    mode = shot.get("mode") or "text2video"
    is_first_last = (mode == "first_last_frame") or (bool(start_path) and bool(end_path))
    
    shot_model = (shot.get("model_name") or wf.get("model_name") or "Omni").strip()
    shot_res = (shot.get("resolution") or wf.get("resolution") or "1080p").strip()
    
    engine = (shot.get("engine") or wf.get("engine") or "vids").strip().lower()
    if engine not in ("vids", "flow", "gemini"):
        engine = "vids"

    if engine == "vids":
        # Google Vids 原生模型与画质规格: Omni 多模态引擎，支持 1080p (超清) 与 720p (标清)
        final_model = f"Omni ({shot_res})" if shot_res in ("1080p", "720p") else "Omni (1080p)"
    elif engine == "flow":
        final_model = shot_model if shot_model and shot_model != "Omni" else "veo-lite"
    else:
        final_model = shot_model or "gemini-video"

    duration_sec = shot.get("duration") or wf.get("duration") or 10

    aspect_ratio = wf.get("aspect_ratio") or "16:9"
    if aspect_ratio not in ("16:9", "9:16"):
        aspect_ratio = "9:16" if ("9:16" in aspect_ratio or "竖" in aspect_ratio) else "16:9"

    task_id = f"task_{uuid.uuid4().hex[:10]}"
    
    task = Task(
        id=task_id,
        prompt=shot.get("prompt", "").strip(),
        start_image_path=start_path if (is_first_last or mode in ("image2video", "extend") or start_path) else "",
        end_image_path=end_path if is_first_last else "",
        engine=engine,
        task_type="video",
        model=final_model,
        project_id=wf.get("doc_url", ""),
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
        status="queued",
        priority=10,
        require_clean_watermark=False,
        assigned_profile_id=None  # 由账号池空闲可用账号动态调度抢占
    )
    
    db.add_task(task)
    engine_name_cn = "Google Vids 原生工作流" if engine == "vids" else ("Google Flow 首尾帧模式" if engine == "flow" else "Gemini")
    db.log_task_event(
        task_id,
        "TASK_CREATED_VIDS",
        f"分镜任务下发 [{engine_name_cn}]: [{shot.get('name')}] (所属工程: {wf.get('title')}), 模型: {final_model}, 画质: {shot_res}, 时长: {duration_sec}s"
    )
    
    old_task_id = shot.get("task_id")
    if old_task_id:
        try:
            old_task = db.get_task(old_task_id)
            if old_task and old_task.status in ("queued", "running", "retry_wait"):
                db.update_task_status(old_task_id, status="cancelled", error_message="用户重新下发分镜生成，取消旧排队任务")
        except Exception:
            pass

    db.update_vids_shot(shot["id"], {
        "task_id": task_id,
        "status": "running",
        "progress": 5,
        "video_url": "",
        "local_video_path": "",
        "error_message": ""
    })
    
    return task_id


@router.post("/shots/{shot_id}/generate")
def generate_single_shot(shot_id: str):
    """单个镜头立即提交生成调度任务"""
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    wf = db.get_vids_workflow(shot["workflow_id"])
    if not wf:
        raise HTTPException(status_code=404, detail="所属工作流不存在")
    
    task_id = _enqueue_shot_task(shot, wf)
    updated_shot = db.get_vids_shot(shot_id)
    return {
        "success": True,
        "task_id": task_id,
        "shot": updated_shot,
        "message": f"分镜 [{shot.get('name')}] 已加入真实调度队列 (Task ID: {task_id})"
    }


@router.post("/workflows/{workflow_id}/generate_all")
def generate_all_shots(workflow_id: str):
    """整个工作流连续批量排队生成"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    shots = wf.get("shots", [])
    target_shots = [s for s in shots if s.get("status") in ("pending", "failed")]
    if not target_shots:
        target_shots = [s for s in shots if s.get("status") != "completed"]
    if not target_shots:
        raise HTTPException(status_code=400, detail="没有待生成的镜头。如需全量重新生成，请先点击【重置全部状态】。")
        
    task_ids = []
    for s in target_shots:
        tid = _enqueue_shot_task(s, wf)
        task_ids.append(tid)
        
    db.update_vids_workflow(workflow_id, {"status": "generating"})
    updated_wf = db.get_vids_workflow(workflow_id)
    return {
        "success": True,
        "queued_count": len(task_ids),
        "task_ids": task_ids,
        "workflow": updated_wf,
        "message": f"成功将 {len(task_ids)} 个镜头加入生成队列，调度器将按序连续执行"
    }


@router.post("/workflows/{workflow_id}/reset_status")
def reset_workflow_shots_status(workflow_id: str):
    """重置工作流全部镜头状态为待生成"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    shots = db.list_vids_shots(workflow_id)
    for s in shots:
        old_tid = s.get("task_id")
        if old_tid:
            try:
                old_task = db.get_task(old_tid)
                if old_task and old_task.status in ("queued", "running", "retry_wait"):
                    db.update_task_status(old_tid, status="cancelled", error_message="用户已重置工作流分镜状态")
            except Exception:
                pass
        # 保留已有成片记录，防止用户点击重置后历史成片丢失
        existing_video_url = s.get("video_url") or ""
        existing_local_path = s.get("local_video_path") or ""
        db.update_vids_shot(s["id"], {
            "status": "pending",
            "progress": 0,
            "error_message": "",
            "video_url": existing_video_url,
            "local_video_path": existing_local_path,
            "task_id": ""
        })
        
    db.update_vids_workflow(workflow_id, {"status": "draft"})
    updated_wf = db.get_vids_workflow(workflow_id)
    return {
        "success": True,
        "workflow": updated_wf,
        "message": "所有镜头已重置为待生成状态"
    }


@router.get("/shots/{shot_id}/semantic_name")
def get_shot_semantic_name(shot_id: str):
    """获取分镜的标准语义化文件名及剪辑定位信息"""
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    wf = db.get_vids_workflow(shot["workflow_id"]) if shot.get("workflow_id") else None
    filename = build_semantic_shot_filename(shot, wf)
    return {
        "shot_id": shot_id,
        "semantic_filename": filename,
        "narration": shot.get("narration", ""),
        "scene_index": shot.get("scene_index", 1),
        "sequence": shot.get("sequence", 1),
        "duration": shot.get("duration", 8),
        "mode": shot.get("mode", "text2video"),
        "resolution": shot.get("resolution", "1080p")
    }


@router.get("/shots/{shot_id}/download")
def download_shot_video(shot_id: str):
    """单镜头规范命名直接下载接口"""
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    wf = db.get_vids_workflow(shot["workflow_id"]) if shot.get("workflow_id") else None
    
    video_path = None
    local_p = shot.get("local_video_path")
    if local_p and Path(local_p).exists() and Path(local_p).is_file():
        video_path = Path(local_p)
    else:
        v_url = shot.get("video_url") or ""
        if "/media/outputs/" in v_url:
            fname = v_url.split("/media/outputs/")[-1].split("?")[0]
            cand = DATA_ROOT / "outputs" / Path(fname).name
            if cand.exists() and cand.is_file():
                video_path = cand
        elif v_url.startswith("/") or ":" in v_url:
            cand = Path(v_url.replace("/media/file?path=", ""))
            if cand.exists() and cand.is_file():
                video_path = cand
    
    if not video_path or not video_path.exists():
        raise HTTPException(status_code=404, detail="成片视频文件尚未生成或不存在")
        
    video_path = local_file(str(video_path))
    filename = build_semantic_shot_filename(shot, wf, ext=video_path.suffix or ".mp4")
    quoted_filename = urllib.parse.quote(filename)
    
    headers = {
        'Content-Disposition': f'attachment; filename="{quoted_filename}"; filename*=UTF-8\'\'{quoted_filename}',
        "X-Semantic-Filename": quoted_filename,
        "Access-Control-Expose-Headers": "Content-Disposition, X-Semantic-Filename"
    }
    return FileResponse(
        path=str(video_path),
        filename=filename,
        media_type="video/mp4",
        headers=headers
    )


@router.get("/workflows/{workflow_id}/package_zip")
def package_workflow_zip(workflow_id: str):
    """一键打包当前工程全部分镜成片（规范语义命名）并附带剪辑分镜与台词对齐清单"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    
    shots = wf.get("shots") or []
    completed_shots = []
    for s in shots:
        local_p = s.get("local_video_path")
        v_path = None
        if local_p and Path(local_p).exists() and Path(local_p).is_file():
            v_path = local_file(local_p)
        elif s.get("video_url"):
            v_url = s.get("video_url")
            if "/media/outputs/" in v_url:
                fname = v_url.split("/media/outputs/")[-1].split("?")[0]
                cand = DATA_ROOT / "outputs" / Path(fname).name
                if cand.exists() and cand.is_file():
                    v_path = cand
        if v_path and v_path.exists():
            completed_shots.append((s, v_path))
            
    if not completed_shots:
        raise HTTPException(status_code=400, detail="当前工程暂无可打包的已完成视频成片")
        
    export_dir = DATA_ROOT / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="vids_package_", suffix=".zip", dir=export_dir)
    os.close(fd)
    zip_path = Path(temp_name)
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
            manifest_lines = [
                "==================================================",
                "  Google Vids 连续生成工程剪辑素材与台词对齐表",
                "==================================================",
                f"工程名称: {wf.get('title', '')}",
                f"画质规格: {wf.get('resolution', '1080p')} · {wf.get('aspect_ratio', '16:9')}",
                f"默认模型: {wf.get('model_name', 'Omni')} / Google Veo",
                f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"包含镜头: 共 {len(completed_shots)} / {len(shots)} 段成片",
                "--------------------------------------------------\n",
                "【剪辑软件导入使用指南】",
                "1. 所有视频文件已按 [01, 02...] 时间线顺序规范命名，可直接批量拖入剪映 / PR / Final Cut / Google Vids 轨道。",
                "2. 下方清单清晰标注了每个视频对应的「场景Scene」、「旁白台词」、「提示词核心」与建议时长。",
                "3. 剪映用户建议：将所有视频拖入视频轨，将下方台词复制到剪映「文本朗读」或直接作为字幕轨道对齐。\n",
                "--------------------------------------------------\n"
            ]
            
            csv_rows = [
                ["序号", "分镜ID", "分镜名称", "场景号", "规范文件名", "时长(秒)", "运镜模式", "画质", "旁白台词", "画面提示词"]
            ]
            
            for shot, v_path in completed_shots:
                fn = build_semantic_shot_filename(shot, wf, ext=v_path.suffix or ".mp4")
                zf.write(str(v_path), arcname=f"videos/{fn}")

                seq = shot.get("sequence", 1)
                scene = shot.get("scene_index", seq)
                name = shot.get("name", f"镜头 {seq}")
                dur = shot.get("duration", 8)
                mode = shot.get("mode", "text2video")
                narr = shot.get("narration", "")
                prompt = shot.get("prompt", "")

                manifest_lines.append(f"【镜头 {seq:02d}】{name}")
                manifest_lines.append(f"  - 对应场景: Scene {scene}")
                manifest_lines.append(f"  - 素材文件: videos/{fn}")
                manifest_lines.append(f"  - 视频时长: {dur} 秒 | 运镜模式: {mode}")
                manifest_lines.append(f"  - 旁白台词: {narr if narr else '(无台词)'}")
                manifest_lines.append(f"  - 视觉提示: {prompt}\n")

                csv_rows.append([
                    str(seq), str(shot.get("id", "")), name, str(scene), fn, str(dur), mode, str(shot.get("resolution", "1080p")), narr, prompt
                ])

            txt_content = "\n".join(manifest_lines)
            zf.writestr("00_剪辑分镜与台词对齐表.txt", txt_content.encode("utf-8-sig"))
            
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            # Spreadsheet text must not execute formula prefixes when opened in Excel.
            csv_writer.writerows([["'"+v if isinstance(v,str) and v.lstrip().startswith(("=","+","-","@")) else v for v in row] for row in csv_rows])
            zf.writestr("00_剪辑分镜与台词对齐表.csv", csv_buffer.getvalue().encode("utf-8-sig"))
            
            clean_wf_backup = {k: v for k, v in wf.items() if k != "shots"}
            clean_wf_backup["shots"] = [
                {k: v for k, v in s.items()} for s in shots
            ]
            zf.writestr("project_workflow.json", json.dumps(clean_wf_backup, ensure_ascii=False, indent=2).encode("utf-8"))

    except Exception:
        zip_path.unlink(missing_ok=True)
        raise
    safe_wf_title = sanitize_filename_part(wf.get("title") or "Vids_Project", 20)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"{safe_wf_title}_剪辑素材包_{date_str}.zip"
    quoted_zip_name = urllib.parse.quote(zip_name)
    
    headers = {
        'Content-Disposition': f'attachment; filename="{quoted_zip_name}"; filename*=UTF-8\'\'{quoted_zip_name}',
        "Access-Control-Expose-Headers": "Content-Disposition"
    }
    return FileResponse(str(zip_path), media_type="application/zip", headers=headers,
                        background=BackgroundTask(zip_path.unlink, missing_ok=True))


@router.put("/workflows/{workflow_id}/rename")
def rename_workflow(workflow_id: str, payload: Dict[str, Any] = Body(...)):
    """重命名工作流工程标题"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    new_title = (payload.get("title") or "").strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="工程标题不能为空")
    db.update_vids_workflow(workflow_id, {"title": new_title})
    return {
        "success": True,
        "workflow_id": workflow_id,
        "title": new_title,
        "message": f"工程已重命名为: {new_title}"
    }


@router.post("/workflows/clean_empty")
def clean_empty_workflows():
    """一键清理所有0镜头的无用空工程与测试废稿，释放工程列表空间"""
    wfs = db.list_vids_workflows()
    deleted = []
    for wf in wfs:
        if wf.get("total_shots", 0) == 0:
            db.delete_vids_workflow(wf["id"])
            deleted.append({"id": wf["id"], "title": wf.get("title", "")})
    return {
        "success": True,
        "deleted_count": len(deleted),
        "deleted_workflows": deleted,
        "message": f"已清理 {len(deleted)} 个无分镜的空工程/废弃测试工程"
    }


@router.get("/workflows_stats")
def get_workflows_stats():
    """获取所有工程的生命周期统计数据"""
    wfs = db.list_vids_workflows()
    empty_count = sum(1 for w in wfs if w.get("total_shots", 0) == 0)
    total_shots = sum(w.get("total_shots", 0) for w in wfs)
    total_completed = sum(w.get("completed_shots", 0) for w in wfs)
    return {
        "total_workflows": len(wfs),
        "empty_workflows_count": empty_count,
        "total_shots": total_shots,
        "total_completed_shots": total_completed,
        "workflows": wfs
    }


@router.post("/workflows/{workflow_id}/stop_all")
def stop_workflow_generation(workflow_id: str):
    """强行中止当前工作流中所有正在运行或排队的分镜任务"""
    wf = db.get_vids_workflow(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="工作流不存在")
    shots = db.list_vids_shots(workflow_id)
    stopped = 0
    from . import web
    for s in shots:
        tid = s.get("task_id")
        if tid:
            try:
                if web.mgr and web.mgr.scheduler:
                    web.mgr.scheduler.cancel_task(tid)
                db.transition_task(tid, "stop", web.DB_PATH)
                stopped += 1
            except Exception:
                pass
        if s.get("status") in ("running", "queued"):
            db.update_vids_shot(s["id"], {"status": "pending", "progress": 0, "error_message": "用户手动停止生成"})
    db.update_vids_workflow(workflow_id, {"status": "draft"})
    return {"success": True, "stopped_count": stopped, "message": f"已成功停止 {stopped} 个镜头的生成任务并释放资源"}


@router.post("/shots/{shot_id}/cancel")
def cancel_shot_generation(shot_id: str):
    """强行中止单个分镜的生成任务"""
    shot = db.get_vids_shot(shot_id)
    if not shot:
        raise HTTPException(status_code=404, detail="分镜不存在")
    tid = shot.get("task_id")
    from . import web
    if tid:
        try:
            if web.mgr and web.mgr.scheduler:
                web.mgr.scheduler.cancel_task(tid)
            db.transition_task(tid, "stop", web.DB_PATH)
        except Exception:
            pass
    db.update_vids_shot(shot_id, {"status": "pending", "progress": 0, "error_message": "用户手动停止生成"})
    return {"success": True, "message": f"分镜 [{shot.get('name')}] 生成任务已成功停止并释放资源"}
