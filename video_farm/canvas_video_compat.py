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

import json
import urllib.error
import urllib.request
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

from .models import Task
from . import db
from .video_contract import validate_video_request, VideoRequestError
from .image_modes import MAX_IMAGE_BYTES
from .local_security import media_type

router = APIRouter(tags=["Infinite Canvas Adapter"])

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "video_farm_data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
DB_PATH = DATA_DIR / "tasks.db"

CLI_PROXY_URL = "http://127.0.0.1:8317/v1"
CLI_PROXY_KEY = "sk-local-23fa8d80e597d0c0d90c2e75d1c1430787ed13afe1175d70"


def _is_upload_file(obj: Any) -> bool:
    return (
        obj is not None
        and hasattr(obj, "filename")
        and bool(getattr(obj, "filename", None))
        and hasattr(obj, "read")
    )


async def _save_upload_image(upload: UploadFile, directory: Path, stem: str) -> str:
    suffix = Path(upload.filename or "image.png").suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(422, f"参考图片格式不支持 ({suffix or '未知后缀'})，仅支持 JPG、PNG、WEBP 格式图片")
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
            raise HTTPException(400, "上传的参考图片内容为空 (0 字节)")
        with Image.open(str(dest)) as img:
            fmt = (img.format or "").upper()
            if fmt not in ("JPEG", "JPG", "PNG", "WEBP"):
                raise HTTPException(422, f"参考图片格式不支持 ({fmt})，仅支持 JPG、PNG、WEBP 格式")
            img.load()
            w, h = img.size
            if w < 32 or h < 32:
                raise HTTPException(422, f"参考图片分辨率过低 ({w}x{h})，宽高均需至少 32 像素")
            if w > 8192 or h > 8192:
                raise HTTPException(422, f"参考图片单边分辨率超过上限 ({w}x{h})，单边最大支持 8192 像素")
            if max(w, h) / max(1, min(w, h)) > 16.0:
                raise HTTPException(422, f"参考图片长宽比异常 ({w}:{h})，不支持极端狭长图片")
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
        },
        {
            "id": "gpt-image-1.5",
            "object": "model",
            "name": "GPT Image 1.5",
            "owned_by": "video-farm",
            "permission": []
        },
        {
            "id": "flow-image",
            "object": "model",
            "name": "Flow Local Image",
            "owned_by": "video-farm",
            "permission": []
        },
        {
            "id": "gpt-6-astra",
            "object": "model",
            "name": "GPT-6 Astra (分镜推演与提示词)",
            "owned_by": "video-farm",
            "permission": []
        },
        {
            "id": "gpt-5.6-sol",
            "object": "model",
            "name": "GPT-5.6 Sol (通用大模型)",
            "owned_by": "video-farm",
            "permission": []
        }
    ]
    return {"object": "list", "data": models}


@router.post("/images/generations")
async def create_canvas_image_generation(request: Request):
    """
    无限画布文生图 OpenAI 兼容适配接口：
    将画布的 POST /images/generations 调度至 8317 或本地图像引擎，返回标准 { data: [{ b64_json: '...' }] } 结构。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "请求体必须为合法 JSON")

    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "生图提示词不能为空")

    target_model = "gpt-image-1.5"

    payload = {
        "model": target_model,
        "prompt": prompt,
        "n": int(body.get("n") or 1),
        "size": body.get("size") or "1024x1024",
        "quality": body.get("quality") or "standard",
        "response_format": "b64_json"
    }

    try:
        req = urllib.request.Request(
            f"{CLI_PROXY_URL}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLI_PROXY_KEY}"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            return JSONResponse(status_code=exc.code, content=err_json)
        except Exception:
            raise HTTPException(exc.code, f"生图代理返回异常: {err_body}") from exc
    except Exception as exc:
        raise HTTPException(502, f"连接生图引擎失败: {exc}") from exc


@router.post("/images/edits")
async def create_canvas_image_edit(request: Request):
    """
    无限画布参考图编辑 / 图生图 OpenAI 兼容适配接口：
    接收 multipart/form-data，抽取参考图与提示词，转发并生成新图像。
    """
    form = await request.form()
    prompt = str(form.get("prompt") or "").strip()
    if not prompt:
        prompt = "根据参考图片进行高质感创意重绘与渲染"

    target_model = "gpt-image-1.5"

    payload = {
        "model": target_model,
        "prompt": prompt,
        "n": 1,
        "size": str(form.get("size") or "1024x1024"),
        "quality": str(form.get("quality") or "standard"),
        "response_format": "b64_json"
    }

    try:
        req = urllib.request.Request(
            f"{CLI_PROXY_URL}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLI_PROXY_KEY}"
            }
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            err_json = json.loads(err_body)
            return JSONResponse(status_code=exc.code, content=err_json)
        except Exception:
            raise HTTPException(exc.code, f"图生图代理返回异常: {err_body}") from exc
    except Exception as exc:
        raise HTTPException(502, f"连接图生图引擎失败: {exc}") from exc


@router.post("/videos")
async def create_canvas_video_task(request: Request):
    """
    无限画布原生视频生成适配接口：接收标准 multipart/form-data 参数，
    全自动归一化画幅、时长、画质与参考帧，杜绝 422 验证报错，
    路由至 8088 底层 Google Flow 或 Google Vids 引擎并创建真实调度任务。
    """
    form = await request.form()
    raw_model = str(form.get("model") or "flow").split("::")[-1].strip().lower()
    clean_prompt = (str(form.get("prompt") or "")).strip() or "根据输入参考生成高质量连贯动态视频"
    mode = str(form.get("mode") or "").strip().lower()

    vquality_str = str(form.get("vquality") or form.get("resolution_name") or "720").strip().lower()
    is_1080p = "1080" in vquality_str

    # 1. 确定生成引擎
    if "vids" in raw_model:
        engine = "vids"
        internal_model = "Omni (1080p)" if is_1080p else "Omni"
    elif "gemini" in raw_model:
        engine = "gemini"
        internal_model = "gemini"
    else:
        engine = "flow"
        internal_model = "flow"

    # 2. 时长参数对齐与校验
    try:
        sec_int = int(str(form.get("seconds") or "6").strip())
    except (ValueError, TypeError):
        sec_int = 6

    if engine == "flow":
        # Flow 规范：4, 6, 8 秒使用 flow 内部模型；10秒必须对应 Omni 校验
        if sec_int not in (4, 6, 8, 10):
            if sec_int <= 4:
                sec_int = 4
            elif sec_int <= 6:
                sec_int = 6
            elif sec_int <= 8:
                sec_int = 8
            else:
                sec_int = 10
        if sec_int == 10:
            if "quality" in raw_model:
                sec_int = 8
                internal_model = "veo-quality"
            else:
                internal_model = "omni-flash"
        elif sec_int == 6:
            internal_model = "omni-flash"
        elif raw_model in ("veo-quality", "veo-fast", "veo-lite", "veo-lite-lp"):
            internal_model = raw_model
        else:
            internal_model = "omni-flash"
    elif engine == "vids":
        # Vids 允许 3 到 10
        sec_int = max(3, min(10, sec_int))

    # 3. 画面比例
    ratio = form.get("ratio")
    size = form.get("size")
    aspect_ratio = "9:16" if ("9:16" in str(ratio) or "720x1280" in str(size)) else "16:9"

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    directory = UPLOADS_DIR / task_id
    start_image_path = ""
    end_image_path = ""

    # 收集所有上传的文件，兼顾 first_frame, last_frame, images, image[], file 等
    collected_files: List[UploadFile] = []
    for field_name, value in form.multi_items():
        if _is_upload_file(value):
            collected_files.append(value)

    try:
        first_frame = form.get("first_frame")
        last_frame = form.get("last_frame")

        if mode == "frames":
            if last_frame and not first_frame and len(collected_files) <= 1:
                raise HTTPException(422, "首尾帧模式缺少起始帧；仅提供尾帧时无法生成，请补齐起始帧或切换为单图参考模式")

        if mode == "reference":
            if engine == "flow":
                if "quality" in raw_model and len(collected_files) > 0:
                    raise HTTPException(422, "Flow Veo Quality 模型不支持参考图 (Ingredients) 生成，请切换为 Veo Fast / Lite 或 Omni 模型，或改用首尾帧模式")
                if any(k in raw_model for k in ("omni-flash", "omni_flash", "omni")):
                    if len(collected_files) > 7:
                        raise HTTPException(422, f"Flow Omni 模型最多支持 7 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 7 张)")
                else:
                    if len(collected_files) > 3:
                        raise HTTPException(422, f"Flow {raw_model} 模型最多支持 3 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 3 张)")
            elif engine == "vids":
                if len(collected_files) > 2:
                    raise HTTPException(422, "Google Vids 当前仅支持首帧或首尾帧模式，不支持超过 2 张参考图")

            saved_refs = []
            for idx, f in enumerate(collected_files):
                saved_p = await _save_upload_image(f, directory, f"ref_{idx+1}")
                saved_refs.append(saved_p)
            start_image_path = ";".join(saved_refs)
            end_image_path = ""
        else:
            if _is_upload_file(first_frame):
                start_image_path = await _save_upload_image(first_frame, directory, "start")
            if _is_upload_file(last_frame):
                end_image_path = await _save_upload_image(last_frame, directory, "end")

            if not start_image_path and len(collected_files) > 0:
                start_image_path = await _save_upload_image(collected_files[0], directory, "start")
            if not end_image_path and len(collected_files) > 1 and engine in ("flow", "vids"):
                end_image_path = await _save_upload_image(collected_files[1], directory, "end")

            if end_image_path and not start_image_path:
                start_image_path = end_image_path
                end_image_path = ""

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
    return FileResponse(
        str(p),
        media_type="video/mp4",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Accept-Ranges": "bytes"
        }
    )
@router.post("/chat/completions")
async def create_canvas_chat_completion(request: Request):
    """
    无限画布文本推演 / 提示词生成 OpenAI 兼容适配接口：
    自动转发至本地 8317 模型网关，支持标准 JSON 与流式 SSE 返回。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "请求体必须为合法 JSON")

    model = (body.get("model") or "gpt-6-astra").split("::")[-1].strip()
    target_body = dict(body)
    target_body["model"] = model or "gpt-6-astra"
    is_stream = bool(body.get("stream", False))

    try:
        req = urllib.request.Request(
            f"{CLI_PROXY_URL}/chat/completions",
            data=json.dumps(target_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLI_PROXY_KEY}",
                "Accept": "text/event-stream" if is_stream else "application/json"
            }
        )
        if is_stream:
            resp = urllib.request.urlopen(req, timeout=60)
            def stream_generator():
                try:
                    while chunk := resp.read(1024):
                        yield chunk
                finally:
                    resp.close()
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            return JSONResponse(status_code=exc.code, content=json.loads(err_body))
        except Exception:
            raise HTTPException(exc.code, f"模型网关返回异常: {err_body}") from exc
    except Exception as exc:
        raise HTTPException(502, f"连接模型网关失败: {exc}") from exc


@router.post("/responses")
async def create_canvas_response_stream(request: Request):
    """
    无限画布 Agent 交互 / 提示词流式响应适配接口：
    转发至 8317 /v1/responses，支持流式 SSE 连续推演与打字机效果。
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "请求体必须为合法 JSON")

    model = (body.get("model") or "gpt-6-astra").split("::")[-1].strip()
    target_body = dict(body)
    target_body["model"] = model or "gpt-6-astra"
    is_stream = bool(body.get("stream", True))

    try:
        req = urllib.request.Request(
            f"{CLI_PROXY_URL}/responses",
            data=json.dumps(target_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {CLI_PROXY_KEY}",
                "Accept": "text/event-stream" if is_stream else "application/json"
            }
        )
        if is_stream:
            resp = urllib.request.urlopen(req, timeout=60)
            def stream_generator():
                try:
                    while chunk := resp.read(1024):
                        yield chunk
                finally:
                    resp.close()
            return StreamingResponse(stream_generator(), media_type="text/event-stream")
        else:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        try:
            return JSONResponse(status_code=exc.code, content=json.loads(err_body))
        except Exception:
            raise HTTPException(exc.code, f"模型网关返回异常: {err_body}") from exc
    except Exception as exc:
        raise HTTPException(502, f"连接模型网关失败: {exc}") from exc
