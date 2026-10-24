"""
Infinite Canvas Video Generation & Model Discovery Adapter.
Provides OpenAI-compatible endpoints for infinite-canvas:
- POST /videos
- GET  /videos/{task_id}
- GET  /videos/{task_id}/content
- GET  /models
"""
from __future__ import annotations
import asyncio
import os
import re
import threading
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
from pydantic import BaseModel
from .timeline_assembler import assemble_timeline, TimelineAssemblyError, calculate_sha256, ShotSpec
from .model_capabilities import get_canvas_models_payload, get_capabilities_raw, get_model_spec

router = APIRouter(tags=["Infinite Canvas Adapter"])

_ACTIVE_PROJECT_ASSEMBLIES: set[str] = set()
_ACTIVE_PROJECT_ASSEMBLIES_LOCK = threading.Lock()

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
    return {"object": "list", "data": get_canvas_models_payload()}


@router.get("/model-capabilities")
def get_model_capabilities_endpoint():
    """返回系统唯一的 MODEL_CAPABILITIES 权威注册数据"""
    return get_capabilities_raw()


def _forward_image_generation_request(payload: dict) -> dict:
    """向本地 CLIProxyAPI 发送生图请求，支持 120s 超时、3次退避重试与网络超时友好兜底。"""
    import time
    max_attempts = 3
    last_exc = None
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                f"{CLI_PROXY_URL}/images/generations",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {CLI_PROXY_KEY}"
                }
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="ignore")
            # 若上游出现 502/503/504 或特定 DNS 超时，且还有重试次数，则短暂回退重试
            if exc.code in (502, 503, 504) and attempt < max_attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                err_json = json.loads(err_body)
                msg = err_json.get("error", {}).get("message", "") if isinstance(err_json.get("error"), dict) else str(err_json)
                if any(k in msg.lower() for k in ("lookup chatgpt.com", "i/o timeout", "dial tcp", "timed out")):
                    friendly_msg = f"上游生图服务连接超时或网络解析波动 (chatgpt.com i/o timeout)，请确认本机 Clash 代理节点 (7897) 正常连接后点击重新生成。原错误: {msg}"
                    if isinstance(err_json.get("error"), dict):
                        err_json["error"]["message"] = friendly_msg
                    else:
                        err_json = {"error": {"message": friendly_msg}}
                return JSONResponse(status_code=exc.code, content=err_json)
            except Exception:
                raise HTTPException(exc.code, f"生图代理返回异常: {err_body}") from exc
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            err_str = str(last_exc)
            if any(k in err_str.lower() for k in ("lookup chatgpt.com", "i/o timeout", "timed out", "dial tcp")):
                return JSONResponse(
                    status_code=504,
                    content={"error": {"message": f"上游生图服务连接超时或网络波动 (chatgpt.com i/o timeout)，请检查本机 Clash 代理节点连通性后重试。详情: {err_str}"}}
                )
            raise HTTPException(502, f"连接生图引擎失败: {last_exc}") from exc


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

    raw_model = (body.get("model") or "").strip()
    target_model = raw_model if raw_model else "gpt-image-1.5"

    payload = {
        "model": target_model,
        "prompt": prompt,
        "n": int(body.get("n") or 1),
        "size": body.get("size") or "1024x1024",
        "quality": body.get("quality") or "standard",
        "response_format": "b64_json"
    }

    return _forward_image_generation_request(payload)


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

    raw_model = str(form.get("model") or "").strip()
    target_model = raw_model if raw_model else "gpt-image-1.5"

    payload = {
        "model": target_model,
        "prompt": prompt,
        "n": 1,
        "size": str(form.get("size") or "1024x1024"),
        "quality": str(form.get("quality") or "standard"),
        "response_format": "b64_json"
    }

    return _forward_image_generation_request(payload)


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
    raw_canvas_project = str(form.get("project_id") or form.get("projectId") or "").strip()
    assigned_profile_id = db.get_affinity_profile_id(raw_canvas_project, DB_PATH) if raw_canvas_project else None

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

    # 1.1 上游工程 ID 与画布 Session Affinity 解耦
    if engine == "flow":
        # 仅当传入的是合法的 Flow UUID 时直接透传，否则置空以便 worker 自动复用该 Profile 已绑定的 Flow 工程
        is_flow_uuid = bool(re.fullmatch(r"[0-9a-f-]{36}", raw_canvas_project.lower()))
        upstream_project_id = raw_canvas_project if is_flow_uuid else ""
    elif engine == "vids":
        # 仅当传入的是实际 docs.google.com/videos URL 时透传，否则置空让 Vids 导航至 /create
        upstream_project_id = raw_canvas_project if raw_canvas_project.startswith("https://docs.google.com/videos/") else ""
    else:
        upstream_project_id = ""

    # 2. 时长参数对齐与校验
    try:
        sec_int = int(str(form.get("seconds") or form.get("duration") or form.get("duration_sec") or "6").strip())
    except (ValueError, TypeError):
        sec_int = 6

    try:
        count_int = int(str(form.get("count") or form.get("n") or form.get("output_count") or "1").strip())
    except (ValueError, TypeError):
        count_int = 1
    if count_int not in (1, 2, 3, 4):
        raise HTTPException(422, f"生成条数仅支持 1~4 条，当前为 {count_int}")
    if engine != "flow" and count_int > 1:
        raise HTTPException(422, f"当前引擎 ({engine}) 仅支持单条生成 (count=1)，不支持批量多条生成")

    if engine == "flow":
        # 优先按用户明确选择的模型归一化
        if "quality" in raw_model:
            internal_model = "veo-quality"
        elif "fast" in raw_model:
            internal_model = "veo-fast"
        elif "lp" in raw_model:
            internal_model = "veo-lite-lp"
        elif "lite" in raw_model:
            internal_model = "veo-lite"
        elif raw_model in ("veo-quality", "veo-fast", "veo-lite", "veo-lite-lp"):
            internal_model = raw_model
        elif any(k in raw_model for k in ("omni-flash", "omni_flash", "omni")):
            internal_model = "omni-flash"
        else:
            internal_model = "flow"

        # 时长硬校验与拦截：严格防止静默替模 (BUG-08)
        is_veo_series = internal_model in ("veo-quality", "veo-fast", "veo-lite", "veo-lite-lp")
        if is_veo_series:
            if sec_int == 10:
                raise HTTPException(
                    422,
                    f"Google Flow 平台限制：Veo 系列模型 ({internal_model}) 仅支持 4s、6s、8s 时长；10s 为 Omni 模型独占。请调整时长为 4s/6s/8s，或切换模型为 Omni (omni-flash)。"
                )
            if sec_int not in (4, 6, 8):
                if sec_int <= 4:
                    sec_int = 4
                elif sec_int <= 6:
                    sec_int = 6
                else:
                    sec_int = 8
        else:
            if sec_int not in (4, 6, 8, 10):
                if sec_int <= 4:
                    sec_int = 4
                elif sec_int <= 6:
                    sec_int = 6
                elif sec_int <= 8:
                    sec_int = 8
                else:
                    sec_int = 10
            if sec_int == 10 and internal_model == "flow":
                internal_model = "omni-flash"
    elif engine == "vids":
        # Vids 允许 3 到 10
        sec_int = max(3, min(10, sec_int))

    # 2.1 延展 (Extend) 模式硬约束与校验：仅允许 Veo 3.1 Lite 8s
    if mode == "extend":
        if engine != "flow" or "quality" in raw_model or "fast" in raw_model:
            raise HTTPException(422, "视频延展 (Extend) 功能仅开放给 Google Flow 的 Veo 3.1 Lite (8s) 模型，当前所选模型不支持延展操作")
        sec_int = 8
        internal_model = "veo-lite"

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

        is_ref_mode = mode in ("reference", "ingredients", "ingredient") or (mode != "frames" and len(collected_files) > 0 and not (first_frame or last_frame))

        # 引擎级硬约束前置防护：Gemini 绝对不支持超过 1 张参考图片
        if engine == "gemini" and len(collected_files) > 1:
            raise HTTPException(422, f"Google Gemini 网页通道最多支持 1 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 1 张)")

        if mode == "frames":
            if engine == "vids":
                raise HTTPException(422, "Google Vids 暂不支持双关键帧首尾插值模式，请使用首帧单图或 1~3 张参考图模式，或切换为 Google Flow")
            if engine == "gemini":
                raise HTTPException(422, "Google Gemini 网页通道不支持尾帧绑定，请切换为 Google Flow 或移除尾帧")
            if last_frame and not first_frame and len(collected_files) <= 1:
                raise HTTPException(422, "首尾帧模式缺少起始帧；仅提供尾帧时无法生成，请补齐起始帧或切换为单图参考模式")

        if is_ref_mode:
            if engine == "flow":
                if "quality" in raw_model and len(collected_files) > 0:
                    raise HTTPException(422, "Flow Veo Quality 模型不支持参考图 (Ingredients) 生成，请切换为 Veo Fast / Lite 或 Omni 模型，或改用首尾帧模式")
                if any(k in raw_model for k in ("omni-flash", "omni_flash", "omni", "flow")):
                    if len(collected_files) > 3:
                        raise HTTPException(422, f"Flow Omni 模型当前已验证最多支持 3 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 3 张)")
                else:
                    if len(collected_files) > 3:
                        raise HTTPException(422, f"Flow {raw_model} 模型最多支持 3 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 3 张)")
            elif engine == "vids":
                if len(collected_files) > 3:
                    raise HTTPException(422, f"Google Vids 当前最多支持 3 张参考图，当前上传了 {len(collected_files)} 张，请减少参考图数量 (最大 3 张)")

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
            project_id=upstream_project_id,
            assigned_profile_id=assigned_profile_id,
            count=count_int,
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
            "model": internal_model,
            "raw_model": raw_model,
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
        urls = []
        if getattr(task, "output_video_paths", None):
            try:
                paths = json.loads(task.output_video_paths)
                for p in paths:
                    fn = Path(p).name
                    if fn:
                        urls.append(f"{base_url}/media/outputs/{fn}")
            except Exception:
                pass
        if not urls and video_url:
            urls = [video_url]

        return {
            "id": task.id,
            "object": "video",
            "status": "completed",
            "url": video_url,
            "video_url": video_url,
            "result_url": video_url,
            "urls": urls,
            "results": [{"url": u} for u in urls],
            "count": len(urls),
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


class TimelineAssemblyShot(BaseModel):
    shot_id: Optional[str] = None
    source_url: str
    order: Optional[int] = 0
    trim_start_s: Optional[float] = 0.0
    trim_end_s: Optional[float] = None


class TimelineAssemblyRequest(BaseModel):
    project_id: str
    shot_video_urls: Optional[List[str]] = None
    shots: Optional[List[TimelineAssemblyShot]] = None
    title: Optional[str] = "多镜头合成视频"
    output_filename: Optional[str] = None
    aspect_ratio: Optional[str] = "16:9"
    aspect_mode: Optional[str] = "fit"
    fps: Optional[int] = None


def resolve_media_url_to_path(url_or_path: str) -> Path:
    """安全将 URL 或文件名解析映射到本地物理视频文件"""
    s = str(url_or_path).strip()
    if not s:
        raise HTTPException(400, "分镜视频路径不能为空")
    p = Path(s)
    if p.is_file():
        return p.resolve()

    if "media/outputs/" in s:
        sub = s.split("media/outputs/")[-1].split("?")[0]
        cand = (OUTPUTS_DIR / sub).resolve()
        if cand.is_file():
            return cand
        cand_sub = (OUTPUTS_DIR / "tomato_story" / Path(sub).name).resolve()
        if cand_sub.is_file():
            return cand_sub
        cand_qa = (BASE_DIR / "QA_EVIDENCE" / "tomato_story" / Path(sub).name).resolve()
        if cand_qa.is_file():
            return cand_qa

    cand = (OUTPUTS_DIR / s).resolve()
    if cand.is_file():
        return cand
    cand_tomato = (OUTPUTS_DIR / "tomato_story" / Path(s).name).resolve()
    if cand_tomato.is_file():
        return cand_tomato
    cand_qa = (BASE_DIR / "QA_EVIDENCE" / "tomato_story" / Path(s).name).resolve()
    if cand_qa.is_file():
        return cand_qa

    raise HTTPException(400, f"分镜视频文件未找到或不可读取: {url_or_path}")


@router.post("/timeline-assembly")
@router.post("/api/canvas/timeline-assembly")
async def handle_timeline_assembly(req: TimelineAssemblyRequest):
    """
    多镜头时间线无缝成片合成接口：
    接收有序分镜视频 URL 列表，调用底层 FFmpeg 滤波图合成标准化 MP4。
    成片注册入库，返回精确时间线时刻清单、总时长及下载 URL。
    """
    with _ACTIVE_PROJECT_ASSEMBLIES_LOCK:
        if req.project_id in _ACTIVE_PROJECT_ASSEMBLIES:
            raise HTTPException(409, f"工程 [{req.project_id}] 已有时间线合成任务正在执行中，请勿重复提交")
        _ACTIVE_PROJECT_ASSEMBLIES.add(req.project_id)

    try:
        resolved_specs: List[ShotSpec] = []
        if req.shots and len(req.shots) >= 2:
            sorted_shots = sorted(req.shots, key=lambda s: s.order if s.order is not None else 0)
            for idx, shot in enumerate(sorted_shots):
                try:
                    rp = resolve_media_url_to_path(shot.source_url)
                    resolved_specs.append(ShotSpec(
                        path=rp,
                        trim_start_s=shot.trim_start_s or 0.0,
                        trim_end_s=shot.trim_end_s,
                        shot_id=shot.shot_id,
                        order=shot.order if shot.order is not None else idx
                    ))
                except HTTPException as e:
                    raise HTTPException(e.status_code, f"第 {idx + 1} 个分镜视频错误: {e.detail}") from e
        elif req.shot_video_urls and len(req.shot_video_urls) >= 2:
            for idx, u in enumerate(req.shot_video_urls):
                try:
                    rp = resolve_media_url_to_path(u)
                    resolved_specs.append(ShotSpec(path=rp, order=idx))
                except HTTPException as e:
                    raise HTTPException(e.status_code, f"第 {idx + 1} 个分镜视频错误: {e.detail}") from e
        else:
            raise HTTPException(400, "时间线合成至少需要 2 个有效镜头视频")

        out_stem = f"assembled_{uuid.uuid4().hex[:12]}"
        if req.output_filename:
            clean_name = re.sub(r"[^\w\-.]", "_", req.output_filename).strip("_")
            if clean_name.lower().endswith(".mp4"):
                clean_name = clean_name[:-4]
            if clean_name:
                out_stem = f"{out_stem}_{clean_name}"
        out_file = OUTPUTS_DIR / f"{out_stem}.mp4"

        is_vertical = str(req.aspect_ratio).strip() in ("9:16", "vertical")
        target_w = 1080 if is_vertical else 1280
        target_h = 1920 if is_vertical else 720
        target_fps = int(req.fps) if req.fps else (30 if is_vertical else 24)
        aspect_mode = "crop" if req.aspect_mode == "crop" else "fit"

        result = await asyncio.to_thread(
            assemble_timeline,
            resolved_specs,
            out_file,
            target_width=target_w,
            target_height=target_h,
            target_fps=target_fps,
            aspect_mode=aspect_mode,
            max_threads=2,
            timeout_sec=180
        )
    except TimelineAssemblyError as e:
        raise HTTPException(e.code, e.message) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"时间线合成异常: {e}") from e
    finally:
        with _ACTIVE_PROJECT_ASSEMBLIES_LOCK:
            _ACTIVE_PROJECT_ASSEMBLIES.discard(req.project_id)

    now_iso = datetime.now().astimezone().isoformat()
    task_id = f"t_{uuid.uuid4().hex[:12]}"
    prompt_text = f"【多镜头时间线成片】{req.title} ({len(resolved_specs)}分镜, {result['total_duration']}s)"

    new_task = Task(
        id=task_id,
        prompt=prompt_text,
        engine="timeline_assembly",
        task_type="video",
        status="completed",
        submit_time=now_iso,
        start_time=now_iso,
        finish_time=now_iso,
        output_video_path=str(out_file.resolve())
    )
    db.add_task(new_task, DB_PATH)

    return {
        "success": True,
        "task_id": task_id,
        "url": f"/media/outputs/{out_file.name}",
        "filename": out_file.name,
        "total_duration": result["total_duration"],
        "expected_duration": result["expected_duration"],
        "file_size": result["file_size"],
        "sha256": result["sha256"],
        "timeline": result["timeline"],
        "video_format": result["video_format"]
    }


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
