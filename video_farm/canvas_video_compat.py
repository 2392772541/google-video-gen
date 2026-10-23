"""
Infinite Canvas Video Generation & Model Discovery Adapter.
Provides OpenAI-compatible endpoints for infinite-canvas:
- POST /videos
- GET  /videos/{task_id}
- GET  /videos/{task_id}/content
- GET  /models
"""
from __future__ import annotations
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

from .models import Task
from . import db
from .video_contract import validate_video_request, VideoRequestError
from .image_modes import MAX_IMAGE_BYTES
from .local_security import media_type

router = APIRouter(tags=["Infinite Canvas Video Adapter"])

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "video_farm_data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
DB_PATH = DATA_DIR / "tasks.db"


async def _save_upload_image(upload: UploadFile, directory: Path, stem: str) -> str:
    suffix = Path(upload.filename or "image.png").suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        suffix = ".png"
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"{stem}{suffix}"
    size = 0
    try:
        with dest.open("wb") as f:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise HTTPException(413, "参考图片体积超过限制 (最大 32MB)")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "上传的参考图片内容为空")
        # Verify image loadable
        with Image.open(str(dest)) as img:
            img.load()
        return str(dest.resolve())
    except (HTTPException, VideoRequestError):
        if dest.exists():
            dest.unlink()
        raise
    except Exception as exc:
        if dest.exists():
            dest.unlink()
        raise HTTPException(422, f"参考图片解码失败: {exc}") from exc
    finally:
        await upload.close()


@router.get("/models")
def list_canvas_models():
    """返回供无限画布模型选择器使用的本地可用模型列表"""
    models = [
        {
            "id": "flow",
            "object": "model",
            "name": "Google Flow (Veo)",
            "owned_by": "video-farm",
            "permission": []
        },
        {
            "id": "vids",
            "object": "model",
            "name": "Google Vids",
            "owned_by": "video-farm",
            "permission": []
        },
        {
            "id": "gemini",
            "object": "model",
            "name": "Gemini Video",
            "owned_by": "video-farm",
            "permission": []
        }
    ]
    return {"object": "list", "data": models}


@router.post("/videos")
async def create_canvas_video_task(
    model: str = Form(...),
    prompt: str = Form(""),
    mode: Optional[str] = Form(None),
    seconds: Optional[str] = Form("6"),
    size: Optional[str] = Form("1280x720"),
    ratio: Optional[str] = Form("16:9"),
    first_frame: Optional[UploadFile] = File(None),
    last_frame: Optional[UploadFile] = File(None),
    images: Optional[List[UploadFile]] = File(None),
    generate_audio: Optional[str] = Form("true"),
    watermark: Optional[str] = Form("false")
):
    """
    无限画布原生视频生成适配接口：接收标准 multipart/form-data 参数，
    路由至 8088 底层 Google Flow 或 Google Vids 引擎并创建真实调度任务。
    """
    raw_model = (model or "").split("::")[-1].strip().lower()
    clean_prompt = (prompt or "无限画布生成视频").strip()
    if not clean_prompt:
        raise HTTPException(400, "提示词不能为空")

    # 1. 确定生成引擎
    if "vids" in raw_model:
        engine = "vids"
        internal_model = "Omni"
    elif "gemini" in raw_model:
        engine = "gemini"
        internal_model = "gemini"
    else:
        engine = "flow"
        internal_model = "flow"

    # 2. 时长参数对齐与校验
    try:
        sec_int = int(str(seconds).strip())
    except (ValueError, TypeError):
        sec_int = 6

    if engine == "flow":
        # Flow 允许 4, 6, 8, 10
        if sec_int not in (4, 6, 8, 10):
            if sec_int <= 4:
                sec_int = 4
            elif sec_int <= 6:
                sec_int = 6
            elif sec_int <= 8:
                sec_int = 8
            else:
                sec_int = 10
    elif engine == "vids":
        # Vids 允许 3 到 10
        sec_int = max(3, min(10, sec_int))

    # 3. 画面比例
    aspect_ratio = "9:16" if ("9:16" in str(ratio) or "720x1280" in str(size)) else "16:9"

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    directory = UPLOADS_DIR / task_id
    start_image_path = ""
    end_image_path = ""

    try:
        # 处理首帧
        if first_frame and first_frame.filename:
            start_image_path = await _save_upload_image(first_frame, directory, "start")
        elif images and len(images) > 0 and images[0].filename:
            start_image_path = await _save_upload_image(images[0], directory, "start")

        # 处理尾帧
        if last_frame and last_frame.filename:
            end_image_path = await _save_upload_image(last_frame, directory, "end")
        elif images and len(images) > 1 and images[1].filename and (mode == "frames" or engine in ("flow", "vids")):
            end_image_path = await _save_upload_image(images[1], directory, "end")

        task = Task(
            id=task_id,
            prompt=clean_prompt,
            start_image_path=start_image_path,
            end_image_path=end_image_path,
            aspect_ratio=aspect_ratio,
            duration_sec=sec_int,
            status="queued",
            engine=engine,
            task_type="video",
            model=internal_model,
            priority=10,
            submit_time=datetime.now().astimezone().isoformat()
        )

        validate_video_request(task)
        db.add_task(task, DB_PATH)
        db.log_task_event(
            task_id,
            "TASK_CREATED_CANVAS",
            f"无限画布视频节点调用生成: 引擎={engine}, 模型={raw_model}, 时长={sec_int}s, 画幅={aspect_ratio}",
            db_path=DB_PATH
        )
        return {
            "id": task_id,
            "object": "video",
            "model": raw_model,
            "status": "queued",
            "created_at": int(time.time())
        }
    except (VideoRequestError, ValueError) as exc:
        if directory.exists():
            for f in directory.iterdir():
                if f.is_file():
                    f.unlink()
            directory.rmdir()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        if directory.exists():
            for f in directory.iterdir():
                if f.is_file():
                    f.unlink()
            directory.rmdir()
        raise


@router.get("/videos/{task_id}")
def get_canvas_video_task_status(task_id: str, request: Request):
    """供无限画布轮询视频任务进度与成片地址"""
    task = db.get_task(task_id, DB_PATH)
    if not task:
        raise HTTPException(404, f"任务 [{task_id}] 未找到")

    base_url = str(request.base_url).rstrip("/")
    if task.status == "completed":
        fname = Path(task.output_video_path).name if task.output_video_path else ""
        video_url = f"{base_url}/media/outputs/{fname}" if fname else ""
        return {
            "id": task.id,
            "object": "video",
            "status": "completed",
            "url": video_url,
            "video_url": video_url,
            "result_url": video_url,
            "progress": 100,
            "created_at": task.submit_time,
            "completed_at": task.finish_time
        }
    elif task.status in ("failed", "cancelled"):
        return {
            "id": task.id,
            "object": "video",
            "status": "failed",
            "error": {
                "message": task.error_message or "视频生成失败或已被取消"
            }
        }
    else:
        # 队列中、调度中、运行中或质检中
        prog_map = {"queued": 10, "dispatching": 25, "running": 50, "verifying": 90, "retry_wait": 15}
        progress = prog_map.get(task.status, 30)
        return {
            "id": task.id,
            "object": "video",
            "status": "pending",
            "progress": progress
        }


@router.get("/videos/{task_id}/content")
def get_canvas_video_content(task_id: str):
    """供无限画布直接拉取成片 MP4 二进制流"""
    task = db.get_task(task_id, DB_PATH)
    if not task:
        raise HTTPException(404, f"任务 [{task_id}] 未找到")
    if not task.output_video_path or not Path(task.output_video_path).is_file():
        raise HTTPException(404, "成片文件尚未生成或不可读取")
    p = Path(task.output_video_path).resolve()
    return FileResponse(str(p), media_type="video/mp4")
