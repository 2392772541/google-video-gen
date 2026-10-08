from __future__ import annotations
from .onboard import auto_onboard_profile
import os
import re
import sys
import time
import json
import uuid
import shutil
import threading
import subprocess
import psutil
import urllib.parse
import zipfile
import tempfile
from starlette.background import BackgroundTask
from pathlib import Path
from contextlib import nullcontext
from typing import Optional, List, Dict, Any

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response as FastAPIResponse
from .local_security import LocalBrowserBoundary, local_file, media_type
from pydantic import BaseModel

from . import db
from .models import Task, Profile
from .video_contract import validate_video_request, VideoRequestError
from .image_modes import image_options, validate_image_settings, validate_image_file, MAX_IMAGE_BYTES
from .flow_errors import (
    FLOW_RESPONSE_UNREADABLE,
    FLOW_RESPONSE_UNREADABLE_MESSAGE,
    is_flow_response_unreadable,
)
from .gemini_worker import GeminiWebWorker
from .scheduler import VideoScheduler

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = BASE_DIR / "video_farm_data"
OUTPUTS_DIR = DATA_DIR / "outputs"
QA_DIR = DATA_DIR / "qa"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "tasks.db"
GFLOW_DIR = BASE_DIR / "gflow-cli"

for d in [DATA_DIR, OUTPUTS_DIR, QA_DIR, UPLOADS_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def profile_directory(profile: Profile | str) -> Path:
    if isinstance(profile, str):
        profile = db.get_profile_by_name(profile, DB_PATH) or Profile(id="", name=profile)
    if profile.profile_path:
        return Path(profile.profile_path).resolve()
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return (Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile.name}").resolve()


def _chrome_uses_directory(cmdline, directory: Path) -> bool:
    # Match the complete flag value, not a profile-name substring.
    for i, arg in enumerate(cmdline or []):
        value = None
        if arg.startswith("--user-data-dir="):
            value = arg.split("=", 1)[1].strip('"')
        elif arg == "--user-data-dir" and i + 1 < len(cmdline):
            value = cmdline[i + 1].strip('"')
        if value and os.path.normcase(str(Path(value).resolve())) == os.path.normcase(str(directory)):
            return True
    return False


def close_chrome_for_profile(profile: Profile | str) -> int:
    directory = profile_directory(profile)
    closed_count = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if (proc.info.get('name') or '').lower() == 'chrome.exe' and _chrome_uses_directory(proc.info.get('cmdline'), directory):
                proc.kill()
                closed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    # Chrome owns its singleton locks; never remove them while another owner may exist.
    return closed_count


def check_chrome_running_for_profile(profile: Profile | str) -> bool:
    directory = profile_directory(profile)
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if (proc.info.get('name') or '').lower() == 'chrome.exe' and _chrome_uses_directory(proc.info.get('cmdline'), directory):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False


_PROFILE_ACTIONS: Dict[str, Dict[str, Any]] = {}


def _reserve_profile_action(profile_id: str, kind: str):
    # A short reservation shares the dispatch guard, never the slow browser work.
    with _scheduler_guard():
        profile = db.get_profile_by_id(profile_id, DB_PATH) or db.get_profile_by_name(profile_id, DB_PATH)
        if not profile:
            raise HTTPException(404, "Profile未找到")
        require_profile_released(profile)
        token = uuid.uuid4().hex
        _PROFILE_ACTIONS[profile.id] = {
            "token": token, "kind": kind, "status": profile.status,
            "cooldown_until": profile.cooldown_until,
        }
        try:
            db.update_profile_status(profile.id, status="busy", db_path=DB_PATH)
        except Exception:
            del _PROFILE_ACTIONS[profile.id]
            raise
        return profile, token


def _release_profile_action(profile_id: str, token: str, auth_valid=None):
    with _scheduler_guard():
        entry = _PROFILE_ACTIONS.get(profile_id)
        if not entry or entry["token"] != token:
            return
        current = db.get_profile_by_id(profile_id, DB_PATH)
        if current and current.status == "busy":
            status = entry["status"]
            if auth_valid is True and status == "auth_expired":
                status = "idle"
            db.update_profile_status(profile_id, status=status,
                                     cooldown_until=entry["cooldown_until"], db_path=DB_PATH)
        del _PROFILE_ACTIONS[profile_id]


def watch_chrome_login_exit(profile_id: str, profile: Profile, db_path: Path, token: str):
    def _worker():
        # Chrome startup is asynchronous. Do not release before it has appeared.
        deadline = time.monotonic() + 15
        seen = False
        while time.monotonic() < deadline:
            if check_chrome_running_for_profile(profile):
                seen = True
                break
            time.sleep(0.5)
        while seen and check_chrome_running_for_profile(profile):
            time.sleep(3)
        # Window closure is not proof of login/consent and cannot reset a new owner.
        _release_profile_action(profile_id, token)
    threading.Thread(target=_worker, daemon=True, name=f"LoginWatcher-{profile.name}").start()

# Scheduler background controller
class SchedulerManager:
    def __init__(self):
        self.scheduler: Optional[VideoScheduler] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.poll_interval = 2.5

    def initialize(self):
        db.init_db(DB_PATH)
        self.scheduler = VideoScheduler(
            db_path=DB_PATH,
            gflow_dir=GFLOW_DIR,
            output_dir=OUTPUTS_DIR,
            qa_dir=QA_DIR,
            max_workers=1,
            worker_timeout_sec=360
        )
        self.scheduler.recover_orphans()
        self.scheduler.running = True  # Default running
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="WebSchedulerLoop")
        self.thread.start()
        print("[SchedulerManager] 后台任务调度器已初始化并启动运行")

    def _run_loop(self):
        while not self.stop_event.is_set():
            try:
                if self.scheduler and self.scheduler.running:
                    self.scheduler.dispatch_cycle()
            except Exception as e:
                print(f"[SchedulerManager] dispatch_cycle 异常: {e}")
            self.stop_event.wait(self.poll_interval)

    def is_running(self) -> bool:
        return bool(self.scheduler and self.scheduler.running)

    def set_running(self, state: bool):
        if self.scheduler:
            self.scheduler.running = state
            print(f"[SchedulerManager] 调度器运行状态切换为: {'RUNNING' if state else 'PAUSED'}")

    def shutdown(self):
        self.stop_event.set()
        if self.scheduler:
            self.scheduler.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        print("[SchedulerManager] 后台调度器已平稳停止")

mgr = SchedulerManager()

app = FastAPI(title="Video Farm Control Studio", version="1.0.0")

app.add_middleware(LocalBrowserBoundary)

from .pipeline import PipelineCapacityError, PipelineInputError, validate_pipeline_spec

@app.exception_handler(PipelineInputError)
async def pipeline_input_error(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})

@app.exception_handler(PipelineCapacityError)
async def pipeline_capacity_error(request, exc):
    return JSONResponse(status_code=429, content={"detail":str(exc)})

@app.on_event("startup")
def on_startup():
    mgr.initialize()

@app.on_event("shutdown")
def on_shutdown():
    mgr.shutdown()

# ==================== API Endpoints ====================

@app.get("/api/overview")
def get_overview():
    profiles = db.list_profiles(DB_PATH)
    task_stats = db.task_statistics(DB_PATH)

    prof_stats = {
        "total": len(profiles),
        "idle": sum(1 for p in profiles if p.status == "idle" and p.enabled),
        "busy": sum(1 for p in profiles if p.status == "busy" and p.enabled),
        "cooldown": sum(1 for p in profiles if p.status == "cooldown" and p.enabled),
        "disabled": sum(1 for p in profiles if not p.enabled or p.status == "disabled"),
        "restricted": sum(1 for p in profiles if p.status == "restricted"),
        "forced_visible_count": sum(1 for p in profiles if p.watermark_mode == "forced_visible"),
        "clean_count": sum(1 for p in profiles if p.watermark_mode == "clean")
    }

    fleet_cooldown_sec = 0
    if mgr.scheduler and mgr.scheduler.fleet_cooldown_until:
        from datetime import datetime
        now_dt = datetime.now().astimezone()
        if mgr.scheduler.fleet_cooldown_until > now_dt:
            fleet_cooldown_sec = max(0, int((mgr.scheduler.fleet_cooldown_until - now_dt).total_seconds()))

    return {
        "scheduler_running": mgr.is_running(),
        "fleet_cooldown_sec": fleet_cooldown_sec,
        "profiles": prof_stats,
        "tasks": task_stats
    }

class ToggleSchedulerReq(BaseModel):
    running: bool

@app.post("/api/scheduler/toggle")
def toggle_scheduler(req: ToggleSchedulerReq):
    mgr.set_running(req.running)
    return {"scheduler_running": mgr.is_running()}

@app.post("/api/fleet/resume")
def api_fleet_resume():
    recovered = 0
    if mgr.scheduler:
        recovered = mgr.scheduler.clear_fleet_cooldown()
    return {"status": "ok", "recovered_tasks": recovered, "fleet_cooldown_sec": 0}

@app.get("/api/profiles")
def get_profiles():
    mgr.scheduler.recover_cooldowns() if mgr.scheduler else None
    profiles = db.list_profiles(DB_PATH)
    res = []
    from .onboard import get_profile_flow_project_id
    for p in profiles:
        human_status = "空闲"
        if not p.enabled:
            human_status = "已停用"
        elif p.status == "busy":
            human_status = "正在生成"
        elif p.status == "cooldown":
            human_status = "冷却中"
        elif p.status == "restricted":
            human_status = "受限 (仅草稿)"
        elif p.watermark_mode == "forced_visible":
            human_status = "可用 (有水印)"
        elif p.watermark_mode == "clean":
            human_status = "可用 (无水印)"

        flow_proj_id = get_profile_flow_project_id(p.name)

        res.append({
            "id": p.id,
            "name": p.name,
            "account_label": p.account_label,
            "status": p.status,
            "human_status": human_status,
            "watermark_mode": p.watermark_mode,
            "flow_project_id": flow_proj_id,
            "is_onboarded": bool(flow_proj_id),
            "enabled": p.enabled,
            "cooldown_until": p.cooldown_until,
            "last_success_at": p.last_success_at,
            "notes": p.notes,
            "created_at": p.created_at
        })
    return res

class AddProfileReq(BaseModel):
    name: str
    account_label: Optional[str] = ""
    notes: Optional[str] = ""

@app.post("/api/profiles/add")
def add_profile_endpoint(req: AddProfileReq):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Profile名称不能为空")

    existing = db.get_profile_by_name(name, DB_PATH)
    if existing:
        raise HTTPException(status_code=400, detail=f"Profile '{name}' 已存在")

    p_id = f"prof_{uuid.uuid4().hex[:8]}"
    profile = Profile(
        id=p_id,
        name=name,
        account_label=req.account_label or "",
        notes=req.notes or "",
        status="idle",
        enabled=True
    )
    db.add_profile(profile, DB_PATH)
    return {"id": p_id, "name": name, "status": "idle"}

class ToggleProfileReq(BaseModel):
    enabled: bool

@app.post("/api/profiles/{profile_id}/toggle")
def toggle_profile(profile_id: str, req: ToggleProfileReq):
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")

    conn = db.get_db_connection(DB_PATH)
    try:
        with conn:
            conn.execute("UPDATE profiles SET enabled = ?, updated_at = ? WHERE id = ?",
                         (1 if req.enabled else 0, time.strftime("%Y-%m-%dT%H:%M:%S%z"), profile_id))
    finally:
        conn.close()
    return {"id": profile_id, "enabled": req.enabled}

@app.post("/api/profiles/{profile_id}/reset-status")
def reset_profile_status(profile_id: str):
    with _scheduler_guard():
        p = db.get_profile_by_id(profile_id, DB_PATH)
        if not p:
            raise HTTPException(status_code=404, detail="Profile未找到")
        require_profile_released(p)
        db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=DB_PATH)
        conn = db.get_db_connection(DB_PATH)
        try:
            with conn:
                conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
        finally:
            conn.close()
        return {"id": profile_id, "status": "idle", "message": f"账号 [{p.name}] 状态已重置为空闲就绪"}


@app.post("/api/profiles/{profile_id}/close-chrome")
def api_close_chrome(profile_id: str):
    with _scheduler_guard():
        p = db.get_profile_by_id(profile_id, DB_PATH)
        if not p:
            raise HTTPException(status_code=404, detail="Profile未找到")
        require_profile_released(p)
        count = close_chrome_for_profile(p)
        db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=DB_PATH)
        conn = db.get_db_connection(DB_PATH)
        try:
            with conn:
                conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
        finally:
            conn.close()
        return {
            "success": True,
            "closed_count": count,
            "message": f"已关闭 {count} 个 Chrome 进程，账号 [{p.name}] 已重置为空闲就绪！"
        }


@app.post("/api/profiles/{profile_id}/verify-auth")
def api_verify_auth(profile_id: str):
    profile, token = _reserve_profile_action(profile_id, "verify")
    result = None
    try:
        result = auto_onboard_profile(profile.name, create_default_project=False)
        return {**result, "valid": bool(result.get("success"))}
    finally:
        _release_profile_action(profile.id, token, auth_valid=bool(result and result.get("success")))


@app.post("/api/profiles/{profile_id}/auto-onboard")
def api_auto_onboard(profile_id: str):
    profile, token = _reserve_profile_action(profile_id, "initialize")
    result = None
    try:
        result = auto_onboard_profile(profile.name, create_default_project=True)
        return result
    finally:
        _release_profile_action(profile.id, token, auth_valid=bool(result and result.get("success")))


@app.post("/api/profiles/auto-onboard-all")
def api_auto_onboard_all():
    results = []
    for profile in db.list_profiles(DB_PATH):
        if not profile.enabled:
            continue
        try:
            # Sequential and explicitly requested; reservations protect every item.
            result = api_auto_onboard(profile.id)
        except HTTPException as exc:
            result = {"success": False, "error_code": "PROFILE_BUSY" if exc.status_code == 409 else "INITIALIZE_ERROR",
                      "message": str(exc.detail)}
        results.append({"profile_id": profile.id, "name": profile.name, "result": result})
    return {"results": results}


def _launch_profile_login(profile_id: str, url: str):
    profile, token = _reserve_profile_action(profile_id, "login")
    try:
        if check_chrome_running_for_profile(profile):
            raise HTTPException(409, "该账号浏览器已打开，请先关闭已有窗口再登录")
        directory = profile_directory(profile)
        directory.mkdir(parents=True, exist_ok=True)
        candidates = [Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                      Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
                      Path(os.environ.get("LOCALAPPDATA", ""))/"Google/Chrome/Application/chrome.exe"]
        chrome = next((p for p in candidates if p.is_file()), None)
        if not chrome:
            raise HTTPException(500, "系统未找到 Google Chrome 可执行文件")
        # User requested an interactive login window; keep its owner until exit.
        subprocess.Popen([str(chrome), f"--user-data-dir={directory}", "--no-first-run",
                          "--no-default-browser-check", url])
        watch_chrome_login_exit(profile.id, profile, DB_PATH, token)
        return {"success": True, "message": f"已打开账号 [{profile.name}] 登录窗口；请亲自登录并处理协议，关闭后重新验证。"}
    except Exception:
        _release_profile_action(profile.id, token)
        raise


@app.post("/api/profiles/{profile_id}/launch-gemini-login")
def launch_gemini_login(profile_id: str):
    return _launch_profile_login(profile_id, "https://gemini.google.com/app")


@app.post("/api/profiles/{profile_id}/launch-login")
def launch_login(profile_id: str):
    return _launch_profile_login(profile_id, "https://flow.google.com/")


def _resolve_output_images(task: Task) -> tuple[List[str], List[str]]:
    paths: List[str] = []
    urls: List[str] = []
    raw_json = getattr(task, "output_image_paths", None)
    if raw_json:
        try:
            raw = json.loads(raw_json)
            if isinstance(raw, list):
                paths = [str(Path(p).resolve()) for p in raw]
            elif isinstance(raw, str) and raw:
                paths = [str(Path(raw).resolve())]
        except Exception:
            pass
    for p_str in paths:
        p = Path(p_str)
        if p.is_relative_to(OUTPUTS_DIR.resolve()):
            relative = p.relative_to(OUTPUTS_DIR.resolve()).as_posix()
            urls.append(f"/media/outputs/{urllib.parse.quote(relative)}")
        else:
            urls.append(f"/media/file?path={urllib.parse.quote(p.as_posix(), safe='')}")
    return paths, urls

def _resolve_image_url(path_str: str, task_id: str, kind: str) -> Optional[str]:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.exists():
        # Maybe inside uploads?
        up_path = UPLOADS_DIR / task_id / f"{kind}.png"
        if up_path.exists():
            return f"/media/uploads/{task_id}/{kind}.png"
        return None
    try:
        # Check if inside uploads
        if UPLOADS_DIR in p.resolve().parents:
            rel = p.resolve().relative_to(UPLOADS_DIR)
            return f"/media/uploads/{rel.as_posix()}"
        # If relative to BASE_DIR or workspace
        return f"/media/file?path={p.resolve().as_posix()}"
    except Exception:
        return f"/media/file?path={p.resolve().as_posix()}"


@app.get("/api/tasks")
def get_tasks(response: FastAPIResponse, status: Optional[str] = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    tasks = db.list_tasks(status=status, limit=limit, db_path=DB_PATH, offset=offset)
    response.headers["X-Total-Count"] = str(db.task_statistics(DB_PATH, status)["total"])
    res = []
    for t in tasks:
        # Human status mapping
        h_status = "排队中"
        if t.status == "dispatching":
            h_status = "分配中"
        elif t.status == "running":
            h_status = "生成中"
        elif t.status == "verifying":
            h_status = "质检中"
        elif t.status == "completed":
            h_status = "已完成"
        elif t.status == "failed":
            h_status = "失败"
        elif t.status == "retry_wait":
            h_status = "等待重试"
        elif t.status == "cancelled":
            h_status = "已取消"

        has_video = bool(t.output_video_path and Path(t.output_video_path).exists())
        video_filename = Path(t.output_video_path).name if has_video else None
        has_audio = bool(getattr(t, "output_audio_path", None) and Path(t.output_audio_path).exists())
        audio_filename = Path(t.output_audio_path).name if has_audio else None
        img_paths, img_urls = _resolve_output_images(t)

        qa_task_dir = QA_DIR / t.id
        first_frame_url = f"/media/qa/{t.id}/first_frame.png" if (qa_task_dir / "first_frame.png").exists() else None
        last_frame_url = f"/media/qa/{t.id}/last_frame.png" if (qa_task_dir / "last_frame.png").exists() else None
        start_img_url = _resolve_image_url(t.start_image_path, t.id, "start")
        end_img_url = _resolve_image_url(t.end_image_path, t.id, "end")
        input_vid_url = _resolve_image_url(getattr(t, "input_video_path", None), t.id, "input_video")

        # Correct old misleading wire classifications for display only; preserve
        # the original incident log and DB history for result recovery.
        response_unreadable = is_flow_response_unreadable(t.error_code, t.error_message, t.logs)
        res.append({
            "id": t.id,
            "prompt": t.prompt,
            "status": t.status,
            "human_status": h_status,
            "engine": getattr(t, "engine", "flow"),
            "task_type": getattr(t, "task_type", "video") or "video",
            "model": getattr(t, "model", "") or "",
            "image_paths": img_paths,
            "image_urls": img_urls,
            "input_video_path": getattr(t, "input_video_path", "") or "",
            "input_video_url": input_vid_url,
            "output_audio_path": getattr(t, "output_audio_path", None),
            "has_audio": has_audio,
            "audio_url": f"/media/outputs/{audio_filename}" if audio_filename else None,
            "aspect_ratio": t.aspect_ratio,
            "duration_sec": t.duration_sec,
            "assigned_profile_id": t.assigned_profile_id,
            "priority": t.priority,
            "retry_count": t.retry_count,
            "max_retries": t.max_retries,
            "submit_time": t.submit_time,
            "start_time": t.start_time,
            "finish_time": t.finish_time,
            "has_video": has_video,
            "output_video_path": t.output_video_path,
            "video_url": f"/media/outputs/{video_filename}" if video_filename else None,
            "first_frame_url": first_frame_url,
            "last_frame_url": last_frame_url,
            "start_image_url": start_img_url,
            "end_image_url": end_img_url,
            "first_frame_ncc": t.first_frame_ncc,
            "last_frame_ncc": t.last_frame_ncc,
            "last_vs_start_ncc": t.last_vs_start_ncc,
            "first_frame_matched": t.first_frame_matched,
            "last_frame_matched": t.last_frame_matched,
            "watermark_check": t.watermark_check,
            "error_code": FLOW_RESPONSE_UNREADABLE if response_unreadable else t.error_code,
            "error_message": FLOW_RESPONSE_UNREADABLE_MESSAGE if response_unreadable else t.error_message
        })
    return res

class BatchTasksReq(BaseModel):
    task_ids: List[str]


@app.delete("/api/tasks/{task_id}")
def delete_single_task(task_id: str):
    try:
        with _scheduler_guard():
            require_task_released(task_id)
            res = db.delete_task(task_id, delete_files=True, db_path=DB_PATH)
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))
    except OSError as e:
        raise HTTPException(409, "产物隔离失败，任务保留: " + str(e))
    if not res.get("deleted"):
        raise HTTPException(status_code=404, detail="Task未找到或已删除")
    return res


@app.post("/api/tasks/batch-delete")
def batch_delete_tasks_endpoint(req: BatchTasksReq):
    if not req.task_ids:
        raise HTTPException(status_code=400, detail="task_ids 列表不能为空")
    with _scheduler_guard():
        for task_id in req.task_ids:
            require_task_released(task_id)
        return db.batch_delete_tasks(req.task_ids, delete_files=True, db_path=DB_PATH)


CN_NUM = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

def parse_shot_info(prompt: Optional[str]):
    if not prompt:
        return None, ''
    p = prompt.strip()
    m = re.search(r'(?:镜头|shot|scene|第)\s*([0-9一二两三四五六七八九十]+)\s*([a-zA-Z]?)(?:镜)?', p, re.I)
    if m:
        num_str = m.group(1)
        sub = m.group(2).upper()
        if num_str.isdigit():
            n = int(num_str)
        else:
            n = 0
            if num_str == '十':
                n = 10
            elif num_str.startswith('十'):
                n = 10 + CN_NUM.get(num_str[1], 0)
            elif num_str.endswith('十'):
                n = CN_NUM.get(num_str[0], 1) * 10
            else:
                n = CN_NUM.get(num_str, 0)
        return n, sub

    m2 = re.match(r'^([0-9]{1,3})[_\-\.、\s]+(?![0-9]|秒|s|min|分|p|k|:)', p, re.I)
    if m2:
        return int(m2.group(1)), ''
    return None, ''

def clean_title_desc(prompt: Optional[str]) -> str:
    if not prompt:
        return '生成视频'
    p = prompt.strip()
    # 循环清洗剥离前缀（镜头编号、数字序号、时长规格、宽高比）
    for _ in range(5):
        old_p = p
        # 1. 镜头前缀 如 镜头01、第2镜、shot 3A、01_
        p = re.sub(r'^(?:镜头|shot|scene|第)\s*[0-9一二两三四五六七八九十]+[a-zA-Z]?(?:镜)?(?:[\s\|：:_\-\.、]+)?', '', p, flags=re.I).strip()
        p = re.sub(r'^[0-9]{1,3}[_\-\.、\s]+(?![0-9]|秒|s|min|分|p|k|:)', '', p, flags=re.I).strip()
        # 2. 规格说明 如 8秒、8s、16:9、9:16、横屏、竖屏、4k
        p = re.sub(r'^[0-9]{1,3}\s*(?:秒|s|min|分)\s*(?:[，,、\s\|：:]+)?', '', p, flags=re.I).strip()
        p = re.sub(r'^[0-9]{1,2}\s*[:：]\s*[0-9]{1,2}\s*(?:横屏|竖屏)?(?:[，,、\s\|：:]+)?', '', p, flags=re.I).strip()
        p = re.sub(r'^(?:横屏|竖屏|4k|1080p)\s*(?:[，,、\s\|：:]+)?', '', p, flags=re.I).strip()
        p = re.sub(r'^[：:\|，,、\s_\-]+', '', p).strip()
        if p == old_p:
            break

    # 3. 按主标点切取第一个核心表达句
    parts = re.split(r'(?<!\d)[:：](?!\d)|[\|，,。；;\r\n]', p)
    first_part = ''
    for part in parts:
        clean_part = part.strip()
        if len(clean_part) >= 2:
            if clean_part in ('特写镜头', '全景镜头', '中景镜头', '近景镜头', '远景镜头', '空镜头', '镜头'):
                continue
            first_part = clean_part
            break
    desc = first_part if first_part else (parts[0].strip() if parts else p)
    cleaned = re.sub(r'[^\w\-一-龥]', '_', desc)
    cleaned = re.sub(r'_+', '_', cleaned).strip('_')
    return cleaned[:25] or '视频'


def format_ordered_filename(task, index: Optional[int] = None, ext: Optional[str] = None, sub_index: Optional[int] = None) -> str:
    raw_prompt = getattr(task, 'prompt', None) or (task.get('prompt') if isinstance(task, dict) else '') or ''
    shot_num, sub = parse_shot_info(raw_prompt)
    desc = clean_title_desc(raw_prompt)
    eng = getattr(task, 'engine', None) or (task.get('engine') if isinstance(task, dict) else None) or 'flow'
    ratio = getattr(task, 'aspect_ratio', None) or (task.get('aspect_ratio') if isinstance(task, dict) else None) or '16-9'
    ratio = str(ratio).replace(':', '-')
    if not ext:
        task_type = getattr(task, 'task_type', None) or (task.get('task_type') if isinstance(task, dict) else 'video')
        if task_type == 'audio':
            ext = '.mp3'
        elif task_type == 'image':
            ext = '.png'
        else:
            ext = '.mp4'

    if shot_num is not None:
        shot_label = f"镜头{shot_num:02d}{sub}"
    else:
        shot_label = "分镜"

    # 关键：当处于批量打包模式（传入全局自然序号 index）时，强制以绝对序号两位数开头，如 01_镜头01_两份原料...
    # 彻底保证在 Windows 资源管理器或其他播放器中按默认名称排序时的先后顺序100%严格正确递增
    if index is not None:
        prefix = f"{index:02d}_{shot_label}"
    else:
        prefix = shot_label

    sub_suffix = f"_img{sub_index:02d}" if sub_index is not None else ""
    return f"{prefix}_{desc}_{eng}_{ratio}{sub_suffix}{ext}"

def get_task_sort_key(task_tuple):
    t = task_tuple[0] if isinstance(task_tuple, (tuple, list)) else task_tuple
    raw_prompt = getattr(t, 'prompt', None) or (t.get('prompt') if isinstance(t, dict) else '') or ''
    created_at = getattr(t, 'created_at', None) or (t.get('created_at') if isinstance(t, dict) else '') or ''
    shot_num, sub = parse_shot_info(raw_prompt)
    sub_idx = task_tuple[2] if isinstance(task_tuple, (tuple, list)) and len(task_tuple) > 2 and task_tuple[2] is not None else 0
    if shot_num is not None:
        return (0, shot_num, sub, str(created_at), sub_idx)
    else:
        return (1, 999999, '', str(created_at), sub_idx)


@app.get("/api/tasks/{task_id}/download")
def download_single_task(task_id: str):
    t = db.get_task(task_id, DB_PATH)
    if not t:
        raise HTTPException(status_code=404, detail="Task未找到")

    file_path = None
    media_type = "application/octet-stream"
    ext = ".mp4"
    if t.output_video_path and Path(t.output_video_path).is_file():
        file_path = Path(t.output_video_path)
        media_type = "video/mp4"
        ext = file_path.suffix or ".mp4"
    elif getattr(t, "output_audio_path", None) and Path(t.output_audio_path).is_file():
        file_path = Path(t.output_audio_path)
        media_type = "audio/mpeg"
        ext = file_path.suffix or ".mp3"
    elif getattr(t, "output_image_paths", None):
        try:
            imgs = json.loads(t.output_image_paths) if isinstance(t.output_image_paths, str) else t.output_image_paths
            valid_imgs = [Path(p) for p in (imgs or []) if p and Path(p).is_file()]
            if len(valid_imgs) == 1:
                file_path = valid_imgs[0]
                media_type = "image/png"
                ext = file_path.suffix or ".png"
            elif len(valid_imgs) > 1:
                temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="video_farm_images_")
                temp_zip_path = Path(temp_zip.name)
                temp_zip.close()
                try:
                    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
                        for s_idx, img_p in enumerate(valid_imgs, 1):
                            arc_name = format_ordered_filename(t, ext=img_p.suffix, sub_index=s_idx)
                            zf.write(local_file(str(img_p)), arcname=arc_name)
                except Exception as e:
                    if temp_zip_path.exists():
                        temp_zip_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=500, detail=f"打包多图失败: {e}")

                zip_name = format_ordered_filename(t, ext=".zip")
                encoded_zip_name = urllib.parse.quote(zip_name)

                def cleanup_temp_zip():
                    try:
                        if temp_zip_path.exists():
                            temp_zip_path.unlink()
                    except Exception:
                        pass

                return FileResponse(
                    str(temp_zip_path),
                    media_type="application/zip",
                    filename=zip_name,
                    headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_zip_name}"},
                    background=BackgroundTask(cleanup_temp_zip)
                )
        except HTTPException:
            raise
        except Exception:
            pass

    if not file_path or not file_path.is_file():
        raise HTTPException(status_code=404, detail="该任务尚未生成完成或产物文件不存在")

    file_path = local_file(str(file_path))
    media_type = __import__("mimetypes").guess_type(str(file_path))[0] or "application/octet-stream"
    filename = format_ordered_filename(t, ext=ext)
    encoded_filename = urllib.parse.quote(filename)

    return FileResponse(
        str(file_path),
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )


@app.post("/api/tasks/batch-download-zip")
@app.get("/api/tasks/batch-download-zip")
def batch_download_tasks_zip(req: Optional[BatchTasksReq] = None, task_ids: Optional[str] = Query(None)):
    ids = []
    if req and req.task_ids:
        ids.extend(req.task_ids)
    if task_ids:
        ids.extend([x.strip() for x in task_ids.split(",") if x.strip()])

    seen = set()
    unique_ids = []
    for x in ids:
        if x not in seen:
            seen.add(x)
            unique_ids.append(x)

    if not unique_ids:
        raise HTTPException(status_code=400, detail="未提供有效的 task_ids")

    tasks_to_pack = []
    for tid in unique_ids:
        t = db.get_task(tid, DB_PATH)
        if not t:
            continue
        if t.output_video_path and Path(t.output_video_path).is_file():
            tasks_to_pack.append((t, local_file(str(Path(t.output_video_path))), None))
        elif getattr(t, "output_audio_path", None) and Path(t.output_audio_path).is_file():
            tasks_to_pack.append((t, local_file(str(Path(t.output_audio_path))), None))
        elif getattr(t, "output_image_paths", None):
            try:
                imgs = json.loads(t.output_image_paths) if isinstance(t.output_image_paths, str) else t.output_image_paths
                valid_imgs = [Path(x) for x in (imgs or []) if x and Path(x).is_file()]
                if len(valid_imgs) == 1:
                    tasks_to_pack.append((t, local_file(str(valid_imgs[0])), None))
                elif len(valid_imgs) > 1:
                    for s_idx, img_p in enumerate(valid_imgs, 1):
                        tasks_to_pack.append((t, local_file(str(img_p)), s_idx))
            except Exception:
                pass

    if not tasks_to_pack:
        raise HTTPException(status_code=400, detail="选中的任务中没有已完成可下载的媒体成片")

    # 严格按照镜头序号升序排序（镜头01、02、03A、03B... 无镜头的按创建时间升序排列）
    tasks_to_pack.sort(key=get_task_sort_key)

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="video_farm_batch_")
    temp_zip_path = Path(temp_zip.name)
    temp_zip.close()

    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
            for idx, item in enumerate(tasks_to_pack, 1):
                t, p = item[0], item[1]
                sub_idx = item[2] if len(item) > 2 else None
                arc_name = format_ordered_filename(t, index=idx, ext=p.suffix, sub_index=sub_idx)
                zf.write(p, arcname=arc_name)
    except Exception as e:
        if temp_zip_path.exists():
            temp_zip_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"打包压缩包失败: {e}")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    zip_name = f"Google_Video_Batch_{timestamp}_{len(tasks_to_pack)}files.zip"
    encoded_zip_name = urllib.parse.quote(zip_name)

    def cleanup_file():
        try:
            if temp_zip_path.exists():
                temp_zip_path.unlink()
        except Exception:
            pass

    return FileResponse(
        str(temp_zip_path),
        media_type="application/zip",
        filename=zip_name,
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_zip_name}"},
        background=BackgroundTask(cleanup_file)
    )



@app.get("/api/tasks/{task_id}")
def get_task_detail(task_id: str):
    t = db.get_task(task_id, DB_PATH)
    if not t:
        raise HTTPException(status_code=404, detail="Task未找到")

    events = db.list_task_events(task_id, DB_PATH)
    has_video = bool(t.output_video_path and Path(t.output_video_path).exists())
    video_filename = Path(t.output_video_path).name if has_video else None

    # Check QA files
    qa_task_dir = QA_DIR / task_id
    qa_files = {
        "first_frame": f"/media/qa/{task_id}/first_frame.png" if (qa_task_dir / "first_frame.png").exists() else None,
        "last_frame": f"/media/qa/{task_id}/last_frame.png" if (qa_task_dir / "last_frame.png").exists() else None,
        "watermark_corner": f"/media/qa/{task_id}/watermark_corner.png" if (qa_task_dir / "watermark_corner.png").exists() else None,
    }

    img_paths, img_urls = _resolve_output_images(t)
    return {
        "id": t.id,
        "prompt": t.prompt,
        "start_image_path": t.start_image_path,
        "end_image_path": t.end_image_path,
        "engine": getattr(t, "engine", "flow"),
        "task_type": getattr(t, "task_type", "video") or "video",
        "model": getattr(t, "model", "") or "",
        "image_paths": img_paths,
        "image_urls": img_urls,
        "input_video_path": getattr(t, "input_video_path", "") or "",
        "input_video_url": _resolve_image_url(getattr(t, "input_video_path", None), task_id, "input_video"),
        "output_audio_path": getattr(t, "output_audio_path", None),
        "has_audio": bool(getattr(t, "output_audio_path", None) and Path(t.output_audio_path).exists()),
        "audio_url": f"/media/outputs/{Path(t.output_audio_path).name}" if (getattr(t, "output_audio_path", None) and Path(t.output_audio_path).exists()) else None,
        "start_image_url": _resolve_image_url(t.start_image_path, task_id, "start"),
        "end_image_url": _resolve_image_url(t.end_image_path, task_id, "end"),
        "status": t.status,
        "aspect_ratio": t.aspect_ratio,
        "duration_sec": t.duration_sec,
        "assigned_profile_id": t.assigned_profile_id,
        "priority": t.priority,
        "retry_count": t.retry_count,
        "max_retries": t.max_retries,
        "submit_time": t.submit_time,
        "start_time": t.start_time,
        "finish_time": t.finish_time,
        "output_video_path": t.output_video_path,
        "video_url": f"/media/outputs/{video_filename}" if video_filename else None,
        "first_frame_ncc": t.first_frame_ncc,
        "last_frame_ncc": t.last_frame_ncc,
        "last_vs_start_ncc": t.last_vs_start_ncc,
        "first_frame_matched": t.first_frame_matched,
        "last_frame_matched": t.last_frame_matched,
        "watermark_check": t.watermark_check,
        "error_code": t.error_code,
        "error_message": t.error_message,
        "logs": t.logs,
        "qa_files": qa_files,
        "events": events
    }


def _scheduler_guard():
    return mgr.scheduler.lock if mgr.scheduler else _API_ACTION_LOCK


def require_task_released(task_id: str):
    # Call under _scheduler_guard so dispatch cannot race retry/delete/enqueue.
    if mgr.scheduler and task_id in mgr.scheduler.active_tasks:
        raise HTTPException(409, "任务执行线程尚未退出，正在停止；请等待资源释放后再操作")


def require_profile_released(profile: Profile):
    if profile.id in _PROFILE_ACTIONS:
        raise HTTPException(409, "账号正在探测、初始化或登录，请等待窗口关闭/操作结束")
    if profile.status == "busy":
        raise HTTPException(409, "账号仍被执行任务占用；请先停止任务并等待后台退出")
    if mgr.scheduler and any(active.get("profile") and active["profile"].id == profile.id
                             for active in mgr.scheduler.active_tasks.values()):
        raise HTTPException(409, "账号执行线程尚未退出，不能释放、重置或重新打开浏览器")
    from .gemini_worker import get_profile_lock
    if get_profile_lock(profile.name).locked():
        raise HTTPException(409, "账号仍有多模态会话正在执行，请先停止并等待退出")


def _selected_profile(value):
    value = str(value or "").strip()
    if value.lower() in ("", "auto", "none", "null"):
        return None
    profile = db.get_profile_by_id(value, DB_PATH) or db.get_profile_by_name(value, DB_PATH)
    if not profile or not profile.enabled:
        raise HTTPException(400, "所选账号不存在或已停用")
    return profile.id


def _asset_path(value):
    if not value or not str(value).strip():
        return ""
    path = Path(str(value).strip()).expanduser()
    return str((path if path.is_absolute() else BASE_DIR / path).resolve())


def _check_video(task):
    try:
        validate_video_request(task)
    except (VideoRequestError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


async def _save_task_upload(upload, directory, stem, limit):
    suffix = Path(upload.filename or "").suffix.lower()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (stem + suffix)
    try:
        size = 0
        with destination.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, "参考素材超过大小限制")
                target.write(chunk)
        if not size:
            raise HTTPException(400, "上传的参考素材为空")
        return str(destination.resolve())
    finally:
        await upload.close()


@app.post("/api/tasks/create")
async def create_task(
    prompt: str = Form(...), engine: str = Form("flow"), task_type: str = Form("video"),
    model: str = Form(""), start_image: Optional[UploadFile] = File(None),
    end_image: Optional[UploadFile] = File(None), start_image_path: Optional[str] = Form(None),
    end_image_path: Optional[str] = Form(None), input_video: Optional[UploadFile] = File(None),
    input_video_path: Optional[str] = Form(None), priority: int = Form(10),
    aspect_ratio: str = Form("9:16"), duration_sec: int = Form(8),
    assigned_profile_id: Optional[str] = Form(None), require_clean_watermark: bool = Form(False)
):
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    directory = UPLOADS_DIR / task_id
    task = Task(id=task_id, prompt=prompt.strip(), engine=engine.strip().lower(),
                task_type=task_type.strip().lower(), model=model.strip(),
                aspect_ratio=aspect_ratio, duration_sec=duration_sec, priority=priority,
                assigned_profile_id=_selected_profile(assigned_profile_id),
                require_clean_watermark=require_clean_watermark,
                start_image_path=_asset_path(start_image_path), end_image_path=_asset_path(end_image_path),
                input_video_path=_asset_path(input_video_path))
    try:
        for upload, attr, stem, limit in ((start_image, "start_image_path", "start", MAX_IMAGE_BYTES),
                                          (end_image, "end_image_path", "end", MAX_IMAGE_BYTES),
                                          (input_video, "input_video_path", "input", 200 * 1024 * 1024)):
            if upload and upload.filename:
                setattr(task, attr, await _save_task_upload(upload, directory, stem, limit))
        _check_video(task)
        db.add_task(task, DB_PATH)
    except Exception:
        # Only files written for this newly generated task ID are eligible for cleanup.
        if directory.exists():
            for saved in directory.iterdir():
                if saved.is_file():
                    saved.unlink()
            directory.rmdir()
        raise
    label = {"flow": "Google Flow", "vids": "Google Vids", "gemini": "Gemini 网页版"}[task.engine]
    db.log_task_event(task_id, "TASK_CREATED_WEB", f"通过Web控制台提交视频任务，引擎: {label}，模型: {task.model}", db_path=DB_PATH)
    return {"id": task_id, "status": "queued", "engine": task.engine, "task_type": "video", "message": f"{label}任务已加入队列"}

@app.post("/api/tasks/create-audio")
async def create_audio_task_endpoint():
    return {"id": "", "status": "disabled", "message": "本地配音功能已下线", "success": False}

@app.get("/api/image/options")
async def get_image_options():
    return image_options()


@app.post("/api/tasks/create-image")
async def create_image_task_endpoint(
    prompt: str = Form(...),
    engine: str = Form("flow"),
    model: Optional[str] = Form(None),
    aspect_ratio: str = Form("9:16"),
    ref_image: Optional[UploadFile] = File(None),
    ref_image_path: Optional[str] = Form(None),
    priority: int = Form(10),
    assigned_profile_id: Optional[str] = Form(None)
):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="生图提示词不能为空")
    try:
        engine, model, aspect_ratio = validate_image_settings(engine, model, aspect_ratio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target_prof_id = (assigned_profile_id or "").strip()
    if target_prof_id.lower() in ("", "auto", "none", "null"):
        target_prof_id = None
    elif not db.get_profile_by_id(target_prof_id, DB_PATH):
        raise HTTPException(status_code=400, detail="所选生图账号不存在")

    task_id = f"task_{uuid.uuid4().hex[:12]}"
    ref_dest_str = ""
    if ref_image and ref_image.filename:
        ref_ext = Path(ref_image.filename).suffix.lower()
        if ref_ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
            raise HTTPException(400, "参考图仅支持 PNG、JPEG、WebP、GIF 或 BMP")
        task_upload_dir = UPLOADS_DIR / task_id
        task_upload_dir.mkdir(parents=True, exist_ok=True)
        ref_dest = task_upload_dir / f"ref{ref_ext}"
        try:
            size = 0
            with ref_dest.open("wb") as output:
                while chunk := await ref_image.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        raise HTTPException(413, "参考图不能超过 32MB")
                    output.write(chunk)
            validate_image_file(ref_dest)
            ref_dest_str = str(ref_dest.resolve())
        except (ValueError, HTTPException) as exc:
            ref_dest.unlink(missing_ok=True)
            task_upload_dir.rmdir()
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(400, str(exc)) from exc
        finally:
            await ref_image.close()
    elif ref_image_path and ref_image_path.strip():
        ref_dest = local_file(ref_image_path)
        try:
            validate_image_file(ref_dest)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        ref_dest_str = str(ref_dest)

    task = Task(
        id=task_id, prompt=prompt.strip(), start_image_path=ref_dest_str,
        end_image_path="", engine=engine, task_type="image", model=model,
        aspect_ratio=aspect_ratio, duration_sec=0, status="queued",
        priority=priority, assigned_profile_id=target_prof_id
    )
    db.add_task(task, DB_PATH)
    mode_desc = "参考图生图" if ref_dest_str else "文生图"
    db.log_task_event(task_id, "TASK_CREATED_WEB",
                      f"图像任务 ({mode_desc})，网页通道: {engine}，模型/模式: {model}", db_path=DB_PATH)
    return {"id": task_id, "status": "queued", "task_type": "image",
            "engine": engine, "model": model, "message": "图像任务已加入队列"}

@app.post("/api/tasks/batch")
async def create_batch_tasks(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败: {str(e)}")

    raw_shots = []
    top_profile_id = ""
    top_engine = ""
    if isinstance(body, list):
        raw_shots = body
    elif isinstance(body, dict):
        top_profile_id = str(body.get("profile_id") or body.get("assigned_profile_id") or "").strip()
        top_engine = str(body.get("engine") or "").strip().lower()
        for k in ["shots", "tasks", "items", "data", "list", "scenes", "storyboard"]:
            if k in body and isinstance(body[k], list):
                raw_shots = body[k]
                break
        if not raw_shots and ("prompt" in body or "text" in body or "description" in body):
            raw_shots = [body]

    if not raw_shots:
        raise HTTPException(status_code=400, detail="分镜列表不能为空，需提供镜头数组")

    if len(raw_shots) > 100:
        raise HTTPException(400, "每次最多导入100个镜头")
    top_pid = _selected_profile(top_profile_id)
    tasks = []
    for index, item in enumerate(raw_shots, start=1):
        if not isinstance(item, dict):
            raise HTTPException(422, f"第{index}项必须是镜头对象；整批未提交")
        try:
            task = Task(
                id=f"task_{uuid.uuid4().hex[:12]}",
                prompt=str(item.get("prompt") or item.get("description") or item.get("text") or item.get("caption") or item.get("content") or "").strip(),
                engine=str(item.get("engine") or top_engine or "vids").strip().lower(),
                task_type=str(item.get("task_type") or "video").strip().lower(),
                model=str(item.get("model") or "").strip(),
                start_image_path=_asset_path(item.get("start_image_path") or item.get("start_image") or item.get("initial_frame") or item.get("start_frame") or item.get("first_frame") or item.get("first_image")),
                end_image_path=_asset_path(item.get("end_image_path") or item.get("end_image") or item.get("end_frame") or item.get("last_frame") or item.get("final_frame") or item.get("last_image")),
                input_video_path=_asset_path(item.get("input_video_path") or item.get("input_video") or item.get("reference_video")),
                aspect_ratio=str(item.get("aspect_ratio") or item.get("ratio") or "9:16").strip(),
                duration_sec=int(item.get("duration_sec", item.get("duration", item.get("seconds", 8)))),
                priority=int(item.get("priority", 10)),
                assigned_profile_id=_selected_profile(item.get("assigned_profile_id", item.get("profile_id", top_pid))),
                require_clean_watermark=bool(item.get("require_clean_watermark", False)),
            )
            _check_video(task)
        except HTTPException as exc:
            raise HTTPException(exc.status_code, f"第{index}项：{exc.detail}；整批未提交") from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, f"第{index}项字段格式错误：{exc}；整批未提交") from exc
        tasks.append(task)
    # All preflight checks precede a single transaction: no partial queue on item N failure.
    events = [(task.id, "TASK_CREATED_BATCH", f"JSON批量导入 ({task.engine})；" +
               ("指定账号" if task.assigned_profile_id else "动态账号池")) for task in tasks]
    db.add_tasks(tasks, DB_PATH, events=events)
    profile = db.get_profile_by_id(top_pid, DB_PATH) if top_pid else None
    label = profile.name if profile else "账号池动态调度"
    return {"created_count": len(tasks), "task_ids": [t.id for t in tasks],
            "assigned_profile_id": top_pid, "assigned_profile_name": label,
            "message": f"已校验并创建 {len(tasks)} 个任务；未指定账号的任务由账号池动态调度。"}

@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str):
    try:
        with _scheduler_guard():
            require_task_released(task_id)
            task = db.get_task(task_id, DB_PATH)
            if task and task.task_type == "video":
                _check_video(task)
            return db.transition_task(task_id, "retry", DB_PATH)
    except KeyError:
        raise HTTPException(404, "Task未找到")
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))

class BatchTasksReq(BaseModel):
    task_ids: list[str]

@app.post("/api/tasks/{task_id}/stop")
def stop_task_endpoint(task_id: str):
    """Signal cancellation; the owner releases the profile/slot in its finally block."""
    try:
        res = db.transition_task(task_id, "stop", DB_PATH)
        if mgr.scheduler:
            mgr.scheduler.cancel_task(task_id)
        db.log_task_event(task_id, "TASK_STOPPED", "用户请求停止；执行线程退出后释放资源", db_path=DB_PATH)
        return {"success": True, "task": res, "message": f"已发送任务 [{task_id}] 的停止请求；资源将在后台退出后释放"}
    except KeyError:
        raise HTTPException(404, "Task未找到")
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))

@app.post("/api/tasks/batch/cancel")
def batch_cancel_tasks(req: BatchTasksReq):
    cancelled, stopping, errors = [], [], []
    for tid in dict.fromkeys(req.task_ids):
        try:
            with _scheduler_guard():
                task = db.get_task(tid, DB_PATH)
                if not task:
                    raise KeyError(tid)
                active = bool(mgr.scheduler and tid in mgr.scheduler.active_tasks)
                action = "cancel" if task.status in ("queued", "retry_wait") and not active else "stop"
                db.transition_task(tid, action, DB_PATH)
            if mgr.scheduler:
                active = mgr.scheduler.cancel_task(tid) or active
            (stopping if active else cancelled).append(tid)
            db.log_task_event(tid, "STOP_REQUESTED" if active else "TASK_CANCELLED",
                "已发送停止信号，等待执行线程退出后释放资源" if active else "任务已取消",
                db_path=DB_PATH)
        except KeyError:
            errors.append({"task_id": tid, "status_code": 404, "message": "Task未找到"})
        except db.TaskOperationConflict as exc:
            errors.append({"task_id": tid, "status_code": 409, "message": str(exc)})
        except Exception as exc:
            errors.append({"task_id": tid, "status_code": 500, "message": str(exc)})
    return {"success": not errors, "cancelled_count": len(cancelled), "cancelled_ids": cancelled,
            "stopping_count": len(stopping), "stopping_ids": stopping, "errors": errors,
            "message": f"已取消 {len(cancelled)} 个，正在停止 {len(stopping)} 个，未处理 {len(errors)} 个"}

@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str, force: bool = False):
    try:
        action = "stop" if force else "cancel"
        res = db.transition_task(task_id, action, DB_PATH)
        if force and mgr.scheduler:
            mgr.scheduler.cancel_task(task_id)
        db.log_task_event(task_id, "TASK_CANCELLED", "用户手动取消任务", db_path=DB_PATH)
        return {"success": True, "task": res, "message": f"任务 [{task_id}] 已成功取消"}
    except KeyError:
        raise HTTPException(404, "Task未找到")
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))


class OpenFolderReq(BaseModel):
    target: str = "outputs"
    task_id: Optional[str] = None

@app.post("/api/system/open-folder")
def open_system_folder(req: OpenFolderReq):
    if req.task_id and (Path(req.task_id).name != req.task_id or any(c in req.task_id for c in "/\\:") or req.task_id in (".","..")):
        raise HTTPException(400, "非法任务ID")
    target_path = OUTPUTS_DIR
    if req.target == "qa":
        target_path = QA_DIR
    elif req.target == "tasks":
        target_path = DATA_DIR
    elif req.target == "uploads":
        target_path = UPLOADS_DIR
    elif req.target == "task_qa" and req.task_id:
        target_path = QA_DIR / req.task_id
        target_path.mkdir(parents=True, exist_ok=True)
    elif req.target == "task_video" and req.task_id:
        t = db.get_task(req.task_id, DB_PATH)
        if t and t.output_video_path and Path(t.output_video_path).exists():
            target_path = Path(t.output_video_path).parent

    try:
        if sys.platform == "win32":
            os.startfile(str(target_path.resolve()))
        else:
            subprocess.Popen(["xdg-open", str(target_path.resolve())])
        return {"success": True, "path": str(target_path.resolve())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开文件夹失败: {e}")

@app.get("/api/system/info")
def get_system_info():
    # Detect gflow git commit
    commit_sha = "unknown"
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(GFLOW_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0:
            commit_sha = res.stdout.strip()
    except Exception:
        pass

    return {
        "service": "Video Farm Control Studio",
        "gflow_commit": commit_sha,
        "gflow_version": "0.76.0+pr831 (nprQif)",
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "db_path": str(DB_PATH.resolve()),
        "output_dir": str(OUTPUTS_DIR.resolve()),
        "scheduler_running": mgr.is_running()
    }

# ==================== Media & Static Serving ====================


# ==========================================
# Production Pipeline (全自动流水线 API)
# ==========================================
from .pipeline import (
    PIPELINE_MANAGER,
    start_storyboard_pipeline_async,
    start_timeline_pipeline_async,
    start_smart_pipeline_async,
    start_animatic_pipeline_async,
    extract_tail_anchor_frame
)
from .timeline_spec import (
    TimelineSpec,
    IntentDetector,
    ContinuityAnchors,
    ShotSpec,
    VisualConfig,
    TracksSpec,
    VoiceTrack,
    BGMTrack,
    SubtitleTrack
)

class StoryboardPipelineReq(BaseModel):
    material_dir: Optional[str] = None
    image_paths: Optional[List[str]] = None
    script_text: Optional[str] = None
    bgm_path: Optional[str] = None
    target_duration: float = 45.0
    output_name: Optional[str] = "master_video_1080p.mp4"
    analysis_strategy: Optional[str] = "AUTO"   # AUTO | PASSTHROUGH | REPLAN
    voice_mode: Optional[str] = "auto"          # auto | none | tts
    subtitle_mode: Optional[str] = "auto"       # auto | none | forced
    aspect_ratio: Optional[str] = "16:9"        # 16:9 | 9:16

@app.post("/api/pipeline/storyboard/run")
def api_run_storyboard_pipeline(req: StoryboardPipelineReq):
    img_list = req.image_paths or []
    mat_dir = Path(req.material_dir) if req.material_dir else None

    if mat_dir and mat_dir.exists():
        if not img_list:
            # 优先检查 images 子目录与当前目录
            candidate_dirs = [mat_dir]
            for sub in ("images", "storyboard", "storyboards", "素材", "分镜"):
                if (mat_dir / sub).exists():
                    candidate_dirs.append(mat_dir / sub)

            for cdir in candidate_dirs:
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    for p in cdir.glob(ext):
                        ps = str(p).lower()
                        if "output" not in ps and "temp" not in ps and "build" not in ps:
                            img_list.append(str(p.resolve()))
                if img_list:
                    break

            # 如果 candidate_dirs 没找到，自动递归深层查找
            if not img_list and mat_dir.exists():
                for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                    for p in mat_dir.rglob(ext):
                        ps = str(p).lower()
                        if "output" not in ps and "temp" not in ps and "build" not in ps:
                            img_list.append(str(p.resolve()))

            # 只保留故事板大图或主要图片
            img_list = sorted(list(set(img_list)))
            # 如果存在 Storyboard_ 前缀的图，优先选用故事板
            sb_imgs = [x for x in img_list if "storyboard" in Path(x).name.lower()]
            if sb_imgs:
                img_list = sorted(sb_imgs)

        if not req.script_text:
            for txt_name in ("Narration_VO.txt", "voice.txt", "script.txt", "旁白.txt", "台词.txt", "文案.txt", "Narration.txt"):
                tf = mat_dir / txt_name
                if tf.exists():
                    try:
                        req.script_text = tf.read_text(encoding="utf-8")
                        break
                    except Exception:
                        pass
            if not req.script_text:
                for tf in mat_dir.glob("*.txt"):
                    if "output" not in str(tf).lower():
                        try:
                            req.script_text = tf.read_text(encoding="utf-8")
                            break
                        except Exception:
                            pass

    if not img_list:
        raise HTTPException(status_code=400, detail="未找到可用分镜图片素材，请检查目录或传入图片路径")

    script_lines = [line.strip() for line in (req.script_text or "").splitlines() if line.strip()]
    if not script_lines:
        script_lines = ["科学纪录片视觉呈现", "微观机制与应用效果解析"]

    if mat_dir and mat_dir.exists():
        out_dir = mat_dir / "output"
        work_dir = mat_dir / "pipeline_temp"
    else:
        out_dir = OUTPUTS_DIR / "pipeline_masters"
        work_dir = DATA_DIR / "pipeline_temp"

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / (req.output_name or "master_video_1080p.mp4")

    # 多分支模式适配
    final_script = script_lines
    if req.voice_mode == "none":
        final_script = []  # 纯音乐无配音模式：彻底关闭TTS

    job_id = start_storyboard_pipeline_async(
        grid_images=img_list,
        script_sentences=final_script,
        bgm_path=req.bgm_path,
        output_master_mp4=out_mp4,
        work_dir=work_dir,
        total_duration=req.target_duration
    )
    return {"status": "ok", "job_id": job_id, "output_path": str(out_mp4)}


class PipelineInspectReq(BaseModel):
    target_path: str
    user_instruction: Optional[str] = None

@app.post("/api/pipeline/inspect")
def api_pipeline_inspect(req: PipelineInspectReq):
    p = Path(req.target_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="指定素材路径不存在")
    report = IntentDetector.inspect_input(p, req.user_instruction)
    import urllib.parse
    for img in report.get("images", []):
        if img.get("path"):
            img["preview_url"] = f"/api/pipeline/file-preview?path={urllib.parse.quote(img['path'])}"
    for shot in report.get("suggested_shots", []):
        if shot.get("image_path"):
            shot["preview_url"] = f"/api/pipeline/file-preview?path={urllib.parse.quote(shot['image_path'])}"
    return {"status": "ok", "report": report}

class SmartPipelineReq(BaseModel):
    material_dir: Optional[str] = None
    image_paths: Optional[List[str]] = None
    script_text: Optional[str] = None
    mode: str = "custom"  # custom | ai_commercial | storyboard_motion | media_montage | veo_raw | post_wrap | long_series_30s | long_series_60s | one_shot_chain
    aspect_ratio: str = "16:9"   # 16:9 | 9:16 | 1:1
    duration_mode: str = "auto"  # auto | fixed
    total_duration: float = 30.0
    voice_mode: str = "auto"     # auto | none
    voice_name: str = "zh-CN-YunxiNeural"
    bgm_mode: str = "auto"       # auto | none | custom
    bgm_path: Optional[str] = None
    subtitle_mode: str = "auto"  # auto | none
    engine_choice: str = "local" # local | flow_veo | gemini | direct_cut
    grid_crop: Optional[bool] = None
    enable_inspect: bool = True
    shots_override: Optional[List[Dict[str, Any]]] = None
    continuity_anchors: Optional[Dict[str, Any]] = None

class ExtractTailFrameReq(BaseModel):
    video_path: str
    offset_frames: int = 4

@app.post("/api/pipeline/extract-tail-frame")
def api_pipeline_extract_tail_frame(req: ExtractTailFrameReq):
    """提取视频尾部稳定关键帧，供下一镜头衔接或预览"""
    vpath = Path(req.video_path)
    if not vpath.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    try:
        tail_img = extract_tail_anchor_frame(vpath, offset_frames=req.offset_frames)
        return {
            "status": "ok",
            "tail_image_path": str(tail_img),
            "preview_url": f"/api/pipeline/file-preview?path={urllib.parse.quote(str(tail_img))}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提取尾部稳定帧失败: {e}")

@app.post("/api/pipeline/smart-run")
def api_pipeline_smart_run(req: SmartPipelineReq):
    mat_dir = Path(req.material_dir) if req.material_dir else None
    img_list: List[str] = req.image_paths or []

    if req.shots_override:
        for s in req.shots_override:
            ip = s.get("image_path") or s.get("in_frame")
            if ip and Path(ip).exists():
                img_list.append(str(Path(ip).resolve()))
        img_list = list(dict.fromkeys(img_list))

    if not img_list and mat_dir and mat_dir.exists():
        img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        for root, _, files in os.walk(str(mat_dir)):
            r_lower = root.lower()
            if any(x in r_lower for x in ["output", "temp", "pipeline_temp", "cache"]):
                continue
            for f in files:
                if Path(f).suffix.lower() in img_exts:
                    img_list.append(str(Path(root) / f))
        img_list = sorted(list(set(img_list)))

    if not img_list:
        raise HTTPException(status_code=400, detail="未找到有效图片素材，请检查素材目录或传入图片")

    script_lines: List[str] = []
    if req.script_text and req.script_text.strip():
        script_lines = [l.strip() for l in req.script_text.splitlines() if l.strip()]
    elif mat_dir and mat_dir.exists():
        for txt_name in ("voice.txt", "script.txt", "Narration_VO.txt", "旁白.txt", "台词.txt", "文案.txt"):
            tf = mat_dir / txt_name
            if tf.exists():
                try:
                    script_lines = [l.strip() for l in tf.read_text(encoding="utf-8").splitlines() if l.strip()]
                    break
                except Exception:
                    pass

    final_bgm: Optional[str] = None
    if req.bgm_mode == "none":
        final_bgm = None
    elif req.bgm_mode == "custom" and req.bgm_path and Path(req.bgm_path).exists():
        final_bgm = str(Path(req.bgm_path).resolve())
    elif req.bgm_mode == "auto":
        if mat_dir and mat_dir.exists():
            for root, _, files in os.walk(str(mat_dir)):
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in (".mp3", ".wav", ".aac", ".m4a", ".flac"):
                        final_bgm = str(Path(root) / f)
                        break
                if final_bgm:
                    break

    now_ts = int(time.time())
    if mat_dir and mat_dir.exists():
        out_dir = mat_dir / "output"
        work_dir = mat_dir / "pipeline_temp"
    else:
        out_dir = OUTPUTS_DIR / "pipeline_masters"
        work_dir = DATA_DIR / f"smart_{now_ts}"

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"master_{req.mode}_{now_ts}.mp4"

    job_id = start_smart_pipeline_async(
        image_paths=img_list,
        script_sentences=script_lines,
        mode=req.mode,
        aspect_ratio=req.aspect_ratio,
        duration_mode=req.duration_mode,
        total_duration=req.total_duration,
        voice_mode=req.voice_mode,
        voice_name=req.voice_name,
        bgm_path=final_bgm,
        subtitle_mode=req.subtitle_mode,
        engine_choice=req.engine_choice,
        grid_crop=req.grid_crop,
        output_master_mp4=out_mp4,
        work_dir=work_dir,
        user_shots_override=req.shots_override,
        continuity_anchors=req.continuity_anchors
    )
    return {
        "status": "ok",
        "job_id": job_id,
        "output_path": str(out_mp4),
        "mode": req.mode,
        "shots_count": len(req.shots_override) if req.shots_override else len(img_list)
    }


@app.post("/api/pipeline/animatic-preview")
def api_pipeline_animatic_preview(req: SmartPipelineReq):
    """极速动态分镜预演：秒级生成高精运镜+配音预演，不消耗云端 Veo 算力"""
    mat_dir = Path(req.material_dir) if req.material_dir else None
    img_list: List[str] = req.image_paths or []

    if req.shots_override:
        for s in req.shots_override:
            ip = s.get("image_path") or s.get("in_frame")
            if ip and Path(ip).exists():
                img_list.append(str(Path(ip).resolve()))
        img_list = list(dict.fromkeys(img_list))

    if not img_list and mat_dir and mat_dir.exists():
        img_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        for root, _, files in os.walk(str(mat_dir)):
            r_lower = root.lower()
            if any(x in r_lower for x in ["output", "temp", "pipeline_temp", "cache"]):
                continue
            for f in files:
                if Path(f).suffix.lower() in img_exts:
                    img_list.append(str(Path(root) / f))
        img_list = sorted(list(set(img_list)))

    if not img_list:
        raise HTTPException(status_code=400, detail="未找到有效图片素材进行预演")

    script_lines: List[str] = []
    if req.script_text and req.script_text.strip():
        script_lines = [l.strip() for l in req.script_text.splitlines() if l.strip()]

    final_bgm: Optional[str] = None
    if req.bgm_mode == "custom" and req.bgm_path and Path(req.bgm_path).exists():
        final_bgm = str(Path(req.bgm_path).resolve())

    now_ts = int(time.time())
    out_dir = OUTPUTS_DIR / "pipeline_masters"
    work_dir = DATA_DIR / f"animatic_{now_ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = out_dir / f"animatic_preview_{now_ts}.mp4"

    job_id = start_animatic_pipeline_async(
        image_paths=img_list,
        script_sentences=script_lines,
        aspect_ratio=req.aspect_ratio,
        total_duration=req.total_duration,
        voice_mode=req.voice_mode,
        voice_name=req.voice_name,
        bgm_path=final_bgm,
        user_shots_override=req.shots_override,
        continuity_anchors=req.continuity_anchors
    )
    return {
        "status": "ok",
        "job_id": job_id,
        "output_path": str(out_mp4),
        "is_animatic": True
    }


class JobSpecValidateReq(BaseModel):
    job_spec: Dict[str, Any]


@app.post("/api/pipeline/job-spec/validate")
def api_pipeline_job_spec_validate(req: JobSpecValidateReq):
    """校验声明式 Job Spec 完整性，核对素材并返回规范化时间线"""
    try:
        spec = TimelineSpec.from_job_spec(req.job_spec)
        shots = spec.tracks.video_track
        missing_assets = []
        for s in shots:
            for p in (s.in_frame, s.out_frame, s.visual.start_image, s.visual.end_image):
                if p and not Path(p).exists():
                    missing_assets.append(p)
        missing_assets = list(set(missing_assets))
        total_dur = sum(s.duration for s in shots)
        return {
            "status": "ok",
            "valid": True,
            "project_name": spec.project_name,
            "aspect_ratio": spec.aspect_ratio,
            "resolution": spec.resolution,
            "shots_count": len(shots),
            "total_duration": round(total_dur, 2),
            "missing_assets": missing_assets,
            "continuity_anchors": spec.continuity_anchors.dict() if spec.continuity_anchors else None,
            "spec": spec.export_job_spec()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Job Spec 格式非法或解析失败: {e}")


@app.post("/api/pipeline/job-spec/export")
def api_pipeline_job_spec_export(req: SmartPipelineReq):
    """将当前工作台配置导出为跨机器通用的声明式 Job Spec JSON"""
    res_map = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    target_res = res_map.get(req.aspect_ratio, (1920, 1080))
    shots = []
    if req.shots_override:
        for idx, us in enumerate(req.shots_override):
            img_p = us.get("image_path") or us.get("in_frame", "")
            end_img_p = us.get("end_image") or us.get("end_image_path") or us.get("out_frame")
            txt = us.get("voice_text", "").strip()
            dur = float(us.get("duration", 2.5))
            motion = us.get("camera_motion") or us.get("motion", "zoom_in")
            continuity = us.get("continuity", "cut")
            shots.append(ShotSpec(
                id=f"shot_{idx+1:02d}",
                duration=dur,
                timing_policy="voice_driven" if req.voice_mode != "none" else "fixed",
                visual=VisualConfig(
                    provider="direct_cut" if req.engine_choice == "direct_cut" else ("veo" if req.engine_choice == "flow_veo" else "ken_burns"),
                    start_image=str(img_p) if img_p else None,
                    end_image=str(end_img_p) if end_img_p else None,
                    camera_motion=motion,
                    motion_preset=motion,
                    continuity=continuity
                ),
                continuity=continuity,
                camera_motion=motion,
                in_frame=str(img_p) if img_p else None,
                out_frame=str(end_img_p) if end_img_p else None,
                drift_warning=us.get("drift_warning"),
                locked=bool(us.get("locked", False)),
                voice_text=txt,
                subtitle_text=txt
            ))

    ca_obj = None
    if req.continuity_anchors:
        ca_obj = ContinuityAnchors(
            subject_anchor=req.continuity_anchors.get("subject_anchor"),
            scene_anchor=req.continuity_anchors.get("scene_anchor"),
            style_anchor=req.continuity_anchors.get("style_anchor", "商业影视大片质感, 8K超高清, 细腻材质光影, 景深通透"),
            state_anchor=req.continuity_anchors.get("state_anchor"),
            locked=bool(req.continuity_anchors.get("locked", True))
        )

    spec = TimelineSpec(
        project_id=f"spec_{int(time.time())}",
        project_name="Exported Job Spec",
        aspect_ratio=req.aspect_ratio,
        resolution=list(target_res),
        fps=30,
        continuity_anchors=ca_obj,
        tracks=TracksSpec(
            video_track=shots,
            voice_track=VoiceTrack(enabled=(req.voice_mode != "none"), voice_name=req.voice_name),
            bgm_track=BGMTrack(enabled=bool(req.bgm_path), file_path=req.bgm_path),
            subtitle_track=SubtitleTrack(enabled=(req.subtitle_mode != "none"))
        )
    )
    return {"status": "ok", "job_spec": spec.export_job_spec()}

@app.post("/api/pipeline/timeline/run")
def api_pipeline_timeline_run(spec: TimelineSpec):
    validate_pipeline_spec(spec)
    if not spec.project_id:
        spec.project_id = "proj_" + uuid.uuid4().hex[:12]
    work_dir = DATA_DIR / f"pipeline_{spec.project_id}_{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    if not spec.output_master_path:
        out_dir = OUTPUTS_DIR / "pipeline_masters"
        out_dir.mkdir(parents=True, exist_ok=True)
        spec.output_master_path = str(out_dir / f"{spec.project_id}_master.mp4")
    job_id = start_timeline_pipeline_async(spec, work_dir)
    return {"status": "ok", "job_id": job_id, "output_path": spec.output_master_path}

@app.get("/api/pipeline/jobs")
def api_list_pipeline_jobs():
    return {"status": "ok", "jobs": PIPELINE_MANAGER.list_jobs()}

@app.get("/api/pipeline/job/{job_id}")
def api_get_pipeline_job(job_id: str):
    job = PIPELINE_MANAGER.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="流水线作业未找到")
    res = dict(job)
    if res.get("output_video") and Path(res["output_video"]).exists():
        res["video_url"] = f"/api/pipeline/video/{job_id}"
        res["download_url"] = f"/api/pipeline/download?job_id={job_id}"
    return {"status": "ok", "job": res}

@app.get("/api/pipeline/download")
def api_pipeline_download(job_id: Optional[str] = None, path: Optional[str] = None):
    target_path = None
    filename = "video.mp4"
    if job_id:
        job = PIPELINE_MANAGER.get_job(job_id)
        if job and job.get("output_video"):
            target_path = Path(job["output_video"]).resolve()
            filename = target_path.name
    elif path:
        p = local_file(path, downloads=True, managed_root=DATA_DIR)
        if p.is_file():
            target_path = p
            filename = target_path.name

    if not target_path or not target_path.is_file():
        raise HTTPException(status_code=404, detail="下载文件不存在")
    return FileResponse(str(target_path), filename=filename, media_type=media_type(target_path))

@app.get("/api/pipeline/video/{job_id}")
def api_serve_pipeline_video(job_id: str):
    job = PIPELINE_MANAGER.get_job(job_id)
    if not job or not job.get("output_video"):
        raise HTTPException(status_code=404, detail="视频尚未生成")
    vp = Path(job["output_video"]).resolve()
    if not vp.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(str(vp), media_type="video/mp4")

@app.get("/media/outputs/{filename:path}")
def serve_output_file(filename: str):
    p = (OUTPUTS_DIR / filename).resolve()
    if not p.is_file() or OUTPUTS_DIR.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail="文件未找到")
    return FileResponse(str(p), media_type=media_type(p))

@app.get("/media/qa/{task_id}/{filename}")
def serve_qa_file(task_id: str, filename: str):
    p = (QA_DIR / task_id / filename).resolve()
    if not p.is_file() or QA_DIR.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail="质检切片未找到")
    return FileResponse(str(p), media_type=media_type(p))

@app.get("/media/uploads/{task_id}/{filename}")
def serve_upload_file(task_id: str, filename: str):
    p = (UPLOADS_DIR / task_id / filename).resolve()
    if not p.is_file() or UPLOADS_DIR.resolve() not in p.parents:
        raise HTTPException(status_code=404, detail="上传素材未找到")
    return FileResponse(str(p), media_type=media_type(p))

@app.get("/api/pipeline/file-preview")
def api_pipeline_file_preview(path: str = Query(...)):
    p = local_file(path)
    return FileResponse(str(p), media_type=media_type(p))

@app.get("/media/file")
def serve_arbitrary_local_file(path: str = Query(...)):
    p = local_file(path)
    return FileResponse(str(p), media_type=media_type(p))


from .vids_router import router as vids_router
app.include_router(vids_router)


# ============================================================
# Gemini 多模态综合工作台 API (对话、视频配音、AI绘画与多账号管理)
# ============================================================

_CHAT_LOCK = threading.Lock()
_CHAT_EXECUTIONS = {}
_API_ACTION_LOCK = threading.RLock()
CHAT_TIMEOUT_SEC = 120


def run_in_clean_thread(fn, *args, wait_timeout=180, on_timeout=None, on_finish=None, **kwargs):
    """Timeout requests cancellation; only the owner thread can release resources."""
    res_box, err_box = {}, {}
    def _runner():
        try:
            res_box['data'] = fn(*args, **kwargs)
        except Exception as exc:
            err_box['err'] = exc
        finally:
            if on_finish:
                on_finish()
    th = threading.Thread(target=_runner, daemon=True)
    try:
        th.start()
    except Exception:
        if on_finish:
            on_finish()
        raise
    th.join(timeout=wait_timeout)
    if th.is_alive():
        if on_timeout:
            on_timeout()
        return {"success": False, "error_code": "EXECUTION_TIMEOUT",
                "error_message": "多模态执行超时，已请求停止；后台退出前账号仍保留占用。"}
    if 'err' in err_box:
        raise err_box['err']
    return res_box.get('data') or {"success": False, "error_message": "执行未返回有效结果"}


@app.get("/api/gemini/sessions/{session_id}/status")
def gemini_session_status(session_id: str):
    with _CHAT_LOCK:
        entry = _CHAT_EXECUTIONS.get(session_id)
        if not entry:
            return {"active": False, "state": "idle"}
        return {"active": True, "state": entry['state'],
                "execution_id": entry['execution_id'], "profile_id": entry['profile_id']}


@app.post("/api/gemini/sessions/{session_id}/stop")
def stop_gemini_session(session_id: str):
    with _CHAT_LOCK:
        entry = _CHAT_EXECUTIONS.get(session_id)
        if not entry:
            return {"success": True, "active": False, "message": "会话已经结束"}
        entry['state'] = 'stopping'
        entry['event'].set()
        # Event is registered before the browser worker starts. No cross-thread
        # Playwright calls and no early slot release, even during launch.
        return {"success": True, "active": True, "state": "stopping",
                "message": "已请求停止；等待后台退出。平台已提交的生成可能继续。"}


def _release_chat_session(session_id, execution_id):
    with _scheduler_guard():
        with _CHAT_LOCK:
            entry = _CHAT_EXECUTIONS.get(session_id)
            if not entry or entry['execution_id'] != execution_id:
                return
            current = db.get_profile_by_id(entry['profile_id'], DB_PATH)
            if current and current.status == 'busy':
                db.update_profile_status(current.id, status='idle', db_path=DB_PATH)
            del _CHAT_EXECUTIONS[session_id]


def _reserve_chat_session(session_id, selected, worker):
    with _scheduler_guard():
        with _CHAT_LOCK:
            if session_id in _CHAT_EXECUTIONS:
                raise HTTPException(409, "此会话仍在执行或停止中，请等待后台退出")
            target = None
            if selected and selected.lower() not in ('auto', 'none', 'null'):
                target = db.get_profile_by_id(selected, DB_PATH) or db.get_profile_by_name(selected, DB_PATH)
                if not target or not target.enabled:
                    raise HTTPException(400, "所选账号不存在或已停用")
            else:
                prior = db.list_gemini_messages(session_id=session_id, limit=8, db_path=DB_PATH)
                binding = next((m.get('profile_id') for m in prior if m.get('profile_id')), None)
                if binding:
                    target = db.get_profile_by_id(binding, DB_PATH)
                    if not target or not target.enabled:
                        raise HTTPException(409, "会话绑定账号已停用，请明确选择新账号")
            if target:
                # Inline checks while holding the registry lock (do not call
                # require_profile_released, which also checks this registry).
                if target.status != 'idle':
                    raise HTTPException(409, "会话绑定账号当前不可用；请等待或明确更换账号")
                from .gemini_worker import get_profile_lock
                if get_profile_lock(target.name).locked():
                    raise HTTPException(409, "账号正在执行其他多模态会话")
            target = db.acquire_idle_profile(profile_id=target.id if target else None, db_path=DB_PATH)
            if not target:
                raise HTTPException(409, "暂无空闲且已启用的账号，请稍后再试")
            execution_id = 'chat_' + uuid.uuid4().hex
            event = threading.Event()
            try:
                worker.prepare_task(execution_id, event)
                _CHAT_EXECUTIONS[session_id] = {'execution_id': execution_id, 'profile_id': target.id,
                                               'event': event, 'state': 'running'}
            except Exception:
                db.update_profile_status(target.id, status='idle', db_path=DB_PATH)
                raise
            return target, execution_id

@app.post("/api/profiles/{profile_id}/unlock")
def unlock_profile_endpoint(profile_id: str):
    with _scheduler_guard():
        p = db.get_profile_by_id(profile_id, DB_PATH) or db.get_profile_by_name(profile_id, DB_PATH)
        if not p:
            raise HTTPException(status_code=404, detail="Profile未找到")
        require_profile_released(p)
        killed = close_chrome_for_profile(p)
        return {"success": True, "killed_processes": killed, "message": f"已关闭账号 [{p.name}] 的专属浏览器；未删除目录锁"}


@app.post("/api/profiles/{profile_id}/launch-chrome")
def launch_chrome_for_gemini(profile_id: str):
    return _launch_profile_login(profile_id, "https://gemini.google.com/app")


@app.get("/api/gemini/messages")
def get_gemini_messages(session_id: str = "default", limit: int = 100):
    msgs = db.list_gemini_messages(session_id=session_id, limit=limit, db_path=DB_PATH)
    return {"messages": msgs}

@app.delete("/api/gemini/messages")
def delete_gemini_messages(session_id: str = "default"):
    with _CHAT_LOCK:
        if session_id in _CHAT_EXECUTIONS:
            raise HTTPException(409, "会话仍在执行，请先停止并等待退出后清空")
        count = db.clear_gemini_messages(session_id=session_id, db_path=DB_PATH)
    return {"success": True, "deleted_count": count}

@app.get("/api/gemini/images")
def get_gemini_images(limit: int = 60):
    imgs = db.list_gemini_images(db_path=DB_PATH, limit=limit)
    return {"images": imgs}

@app.post("/api/profiles/{profile_id}/test-gemini")
def test_gemini_profile(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    if check_chrome_running_for_profile(p.name):
        return {
            "success": False,
            "error_code": "PROFILE_LOCKED",
            "message": f"账号 [{p.name}] 正在被运行中的 Chrome 窗口占用。请关闭该 Chrome 窗口或在控制台点击【⏹ 释放占用】。"
        }
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    profile_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{p.name}"
    exists = profile_dir.exists()
    return {
        "success": True,
        "profile_id": p.id,
        "profile_name": p.name,
        "profile_path": str(profile_dir),
        "dir_exists": exists,
        "message": f"账号 [{p.name}] 检测就绪，可调度发起多模态创作"
    }

@app.post("/api/gemini/chat")
def gemini_chat_endpoint(
    message: str = Form(""),
    session_id: str = Form("default"),
    profile_id: Optional[str] = Form(None),
    mode: str = Form("chat"),
    voice: str = Form("zh-CN-YunxiNeural"),
    aspect_ratio: str = Form("16:9"),
    video: Optional[UploadFile] = File(None),
    video_path: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    image_path: Optional[str] = Form(None)
):
    message = message.strip() if message else ""
    session_id = session_id.strip() if session_id else "default"
    mode = mode.strip() if mode else "chat"
    voice = voice.strip() if voice else "zh-CN-YunxiNeural"
    aspect_ratio = aspect_ratio.strip() if aspect_ratio else "16:9"
    if profile_id:
        profile_id = profile_id.strip()

    chat_upload_dir = UPLOADS_DIR / "gemini_chat"
    chat_upload_dir.mkdir(parents=True, exist_ok=True)

    video_dest_str = ""
    video_url = None
    if video and video.filename:
        v_ext = Path(video.filename).suffix or ".mp4"
        v_dest = chat_upload_dir / f"vid_{uuid.uuid4().hex[:8]}_{Path(video.filename).name}"
        with open(v_dest, "wb") as f:
            shutil.copyfileobj(video.file, f)
        video_dest_str = str(v_dest.resolve())
        video_url = f"/media/uploads/gemini_chat/{v_dest.name}"
    elif video_path:
        v_cand = video_path.strip()
        v_resolved = None
        if v_cand.startswith("/media/outputs/"):
            fn = v_cand[len("/media/outputs/"):]
            p = OUTPUTS_DIR / fn
            if p.exists():
                v_resolved = p
        elif v_cand.startswith("/media/uploads/"):
            rel = v_cand[len("/media/uploads/"):]
            p = UPLOADS_DIR / rel
            if p.exists():
                v_resolved = p
        elif Path(v_cand).exists():
            v_resolved = Path(v_cand)
        if v_resolved:
            video_dest_str = str(v_resolved.resolve())
            video_url = f"/media/file?path={video_dest_str}"

    image_dest_str = ""
    image_url = None
    if image and image.filename:
        i_ext = Path(image.filename).suffix or ".png"
        i_dest = chat_upload_dir / f"img_{uuid.uuid4().hex[:8]}_{Path(image.filename).name}"
        with open(i_dest, "wb") as f:
            shutil.copyfileobj(image.file, f)
        image_dest_str = str(i_dest.resolve())
        image_url = f"/media/uploads/gemini_chat/{i_dest.name}"
    elif image_path:
        i_cand = image_path.strip()
        i_resolved = None
        if i_cand.startswith("/media/outputs/"):
            fn = i_cand[len("/media/outputs/"):]
            p = OUTPUTS_DIR / fn
            if p.exists():
                i_resolved = p
        elif i_cand.startswith("/media/uploads/"):
            rel = i_cand[len("/media/uploads/"):]
            p = UPLOADS_DIR / rel
            if p.exists():
                i_resolved = p
        elif Path(i_cand).exists():
            i_resolved = Path(i_cand)
        if i_resolved:
            image_dest_str = str(i_resolved.resolve())
            image_url = f"/media/file?path={image_dest_str}"

    attachments = []
    if video_dest_str:
        attachments.append({
            "type": "video",
            "name": Path(video_dest_str).name,
            "path": video_dest_str,
            "url": video_url or f"/media/file?path={video_dest_str}"
        })
    if image_dest_str:
        attachments.append({
            "type": "image",
            "name": Path(image_dest_str).name,
            "path": image_dest_str,
            "url": image_url or f"/media/file?path={image_dest_str}"
        })

    worker = mgr.scheduler.gemini_worker if (mgr.scheduler and hasattr(mgr.scheduler, "gemini_worker")) else GeminiWebWorker(output_dir=OUTPUTS_DIR)
    target_profile, execution_id = _reserve_chat_session(session_id, profile_id, worker)
    try:
        user_msg = db.add_gemini_message({
            "session_id": session_id, "profile_id": target_profile.id,
            "profile_name": target_profile.name, "role": "user", "mode": mode,
            "content": message, "attachments_json": json.dumps(attachments, ensure_ascii=False),
            "status": "completed"
        }, DB_PATH)
        actual_prompt = message
        if mode == "chat" and not attachments:
            prior = db.list_gemini_messages(session_id=session_id, limit=8, db_path=DB_PATH)
            turns = [m for m in prior if m.get('id') != user_msg['id'] and m.get('content') and m.get('status') == 'completed'][-4:]
            if turns:
                history = "\n".join(("用户" if m['role'] == 'user' else 'Gemini') + ': ' + m['content'][:300] for m in turns)
                actual_prompt = f"【前序对话记录】\n{history}\n\n【用户最新问题】\n{message}"
    except Exception:
        worker.cancel_task(execution_id)
        worker.discard_prepared_task(execution_id)
        _release_chat_session(session_id, execution_id)
        raise

    def invoke_chat():
        res = worker.execute_multimodal_interaction(
            profile=target_profile, prompt=actual_prompt, mode=mode, video_path=video_dest_str,
            image_path=image_dest_str, voice=voice, aspect_ratio=aspect_ratio,
            timeout_sec=CHAT_TIMEOUT_SEC, execution_id=execution_id)
        ai_text = res.get('text') or ('⚠️ ' + res.get('error_message', '执行失败') if not res.get('success')
                                    else '（多模态产物已生成）' if res.get('audio_url') or res.get('image_urls') else 'Gemini 已处理完成')
        if res.get('warning'):
            ai_text += '\n\n⚠️ ' + res['warning']
        ai_msg = db.add_gemini_message({
            "session_id": session_id, "profile_id": target_profile.id, "profile_name": target_profile.name,
            "role": "assistant", "mode": mode, "content": ai_text,
            "audio_url": res.get('audio_url'), "audio_path": res.get('audio_path'),
            "image_urls_json": json.dumps(res.get('image_urls') or [], ensure_ascii=False),
            "status": 'completed' if res.get('success') else 'failed', "error_message": res.get('error_message')
        }, DB_PATH)
        return {"success": res.get('success', False), "user_message": user_msg,
                "assistant_message": ai_msg, "error_message": res.get('error_message'),
                "error_code": res.get('error_code'), "warning": res.get('warning')}

    res = run_in_clean_thread(invoke_chat, wait_timeout=CHAT_TIMEOUT_SEC + 10,
                             on_timeout=lambda: stop_gemini_session(session_id),
                             on_finish=lambda: _release_chat_session(session_id, execution_id))
    res.setdefault('user_message', user_msg)
    res['execution_id'] = execution_id
    return res


@app.get("/vids")
def serve_vids_page():
    vids_file = STATIC_DIR / "vids.html"
    if not vids_file.exists():
        return JSONResponse({"message": "Google Vids Studio static/vids.html is not created yet."})
    return FileResponse(str(vids_file), headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"})

class NoCacheStaticFiles(StaticFiles):
    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"message": "Video Farm Studio Web API is running, but static/index.html is not created yet."})
    return FileResponse(str(index_file), headers={"Cache-Control": "no-cache, no-store, must-revalidate, max-age=0", "Pragma": "no-cache"})

def main():
    import argparse
    parser = argparse.ArgumentParser(description="启动 Video Farm 网页管理控制台")
    parser.add_argument("--port", type=int, default=8088, help="服务端口 (默认 8088)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定主机地址 (默认 127.0.0.1)")
    args = parser.parse_args()

    print(f"============================================================")
    print(f"  🎬 Video Farm 首尾帧视频农场 · 本地控制台")
    print(f"  👉 本地访问地址: http://{args.host}:{args.port}")
    print(f"============================================================")
    uvicorn.run("video_farm.web:app", host=args.host, port=args.port, reload=False)

if __name__ == "__main__":
    main()
