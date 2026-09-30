# -*- coding: utf-8 -*-
"""
Google Vids Workflow & Continuous Generation API Router
"""
from __future__ import annotations
import os
import uuid
import json
from typing import Optional, List, Dict, Any
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Body, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

import urllib.parse
from .models import Task
from . import db
from . import vids_workflow

router = APIRouter(prefix="/api/vids", tags=["Google Vids"])

UPLOADS_VIDS_DIR = Path("video_farm_data/uploads/vids")
UPLOADS_VIDS_DIR.mkdir(parents=True, exist_ok=True)


class CreateWorkflowRequest(BaseModel):
    title: str
    doc_url: str = ""
    style_prompt: str = ""
    aspect_ratio: str = "16:9"
    duration_per_shot: int = 10
    resolution: str = "1080p"
    model_name: str = "Omni"
    shots: Optional[List[Dict[str, Any]]] = None


class UpdateWorkflowRequest(BaseModel):
    title: Optional[str] = None
    doc_url: Optional[str] = None
    style_prompt: Optional[str] = None
    aspect_ratio: Optional[str] = None
    duration_per_shot: Optional[int] = None
    resolution: Optional[str] = None
    model_name: Optional[str] = None
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
    
    raw_data = payload.get("data") if "data" in payload else payload
    
    target_wf = None
    if target_wf_id and import_mode != "new":
        target_wf = db.get_vids_workflow(target_wf_id)
        if not target_wf:
            import_mode = "new"

    normalized = vids_workflow.normalize_imported_workflow_json(raw_data, default_workflow=target_wf)

    if import_mode == "new" or not target_wf:
        wf = db.create_vids_workflow(
            title=normalized.get("title") or "批量导入工作流",
            doc_url=normalized.get("doc_url") or "https://docs.google.com/videos/d/1EXFiC89I2CzVObDNGCXejn-FYySYoaKPjRIG8Fa6nS4/edit",
            style_prompt=normalized.get("style_prompt") or "",
            aspect_ratio=normalized.get("aspect_ratio") or "16:9",
            duration_per_shot=normalized.get("duration_per_shot") or 10,
            resolution=normalized.get("resolution") or "1080p",
            model_name=normalized.get("model_name") or "Omni"
        )
        wf_id = wf["id"]
        start_seq = 1
    else:
        wf_id = target_wf["id"]
        updates = {}
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
            model_name=shot.get("model_name") or default_model
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
        ext = ".png"
    file_id = f"vids_{uuid.uuid4().hex[:12]}{ext}"
    dest_path = UPLOADS_VIDS_DIR / file_id
    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)
    
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
    if not p.exists() or UPLOADS_VIDS_DIR.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail="资产未找到")
    media_type = "image/png" if p.suffix.lower() in (".png",) else "image/jpeg"
    if p.suffix.lower() == ".webp":
        media_type = "image/webp"
    return FileResponse(str(p), media_type=media_type)


@router.get("/workflows")
def list_workflows():
    wfs = db.list_vids_workflows()
    return {"workflows": wfs}


@router.post("/workflows")
def create_workflow(req: CreateWorkflowRequest):
    wf = db.create_vids_workflow(
        title=req.title,
        doc_url=req.doc_url,
        style_prompt=req.style_prompt,
        aspect_ratio=req.aspect_ratio,
        duration_per_shot=req.duration_per_shot,
        resolution=req.resolution,
        model_name=req.model_name
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
                model_name=shot.get("model_name", req.model_name)
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
    
    # 核心映射逻辑：
    # 1. 首尾帧插值：底层 flow 官方约束只支持 veo-quality (1080p) 与 veo-lite (720p)，标准时长为 8s
    if is_first_last:
        if shot_res == "720p":
            final_model = "veo-lite"
            duration_sec = 8
        else:
            final_model = "veo-quality"
            duration_sec = 8
    else:
        # 单图/图生视频或文生视频
        if shot_model.lower() in ("omni", "omni-flash"):
            final_model = "omni-flash"
            duration_sec = shot.get("duration") or 5
        elif shot_res == "1080p" or shot_model.lower() in ("veo", "veo-quality"):
            final_model = "veo-quality"
            duration_sec = 8
        elif shot_model.lower() in ("veo-lite", "veolite"):
            final_model = "veo-lite"
            duration_sec = 8
        else:
            final_model = "veo-lite"
            duration_sec = 8

    aspect_ratio = wf.get("aspect_ratio") or "16:9"
    if aspect_ratio not in ("16:9", "9:16"):
        aspect_ratio = "9:16" if ("9:16" in aspect_ratio or "竖" in aspect_ratio) else "16:9"

    task_id = f"task_{uuid.uuid4().hex[:10]}"
    
    task = Task(
        id=task_id,
        prompt=shot.get("prompt", "").strip(),
        start_image_path=start_path if (is_first_last or mode in ("image2video", "extend") or start_path) else "",
        end_image_path=end_path if is_first_last else "",
        engine="flow",
        task_type="video",
        model=final_model,
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
        status="queued",
        priority=10,
        require_clean_watermark=False,
        assigned_profile_id=None  # 由账号池空闲可用账号动态调度抢占
    )
    
    db.add_task(task)
    db.log_task_event(
        task_id,
        "TASK_CREATED_VIDS",
        f"Google Vids 任务下发: [{shot.get('name')}] (所属工程: {wf.get('title')}), 模型: {final_model}, 画质: {shot_res}, 时长: {duration_sec}s"
    )
    
    db.update_vids_shot(shot["id"], {
        "task_id": task_id,
        "status": "running",
        "progress": 5,
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
        db.update_vids_shot(s["id"], {
            "status": "pending",
            "progress": 0,
            "error_message": "",
            "video_url": "",
            "task_id": ""
        })
        
    db.update_vids_workflow(workflow_id, {"status": "draft"})
    updated_wf = db.get_vids_workflow(workflow_id)
    return {
        "success": True,
        "workflow": updated_wf,
        "message": "所有镜头已重置为待生成状态"
    }
