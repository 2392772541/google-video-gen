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
from typing import Optional, List, Dict, Any

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response as FastAPIResponse
from .local_security import LocalBrowserBoundary, local_file, media_type
from pydantic import BaseModel

from . import db
from .models import Task, Profile
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


def close_chrome_for_profile(profile_name: str) -> int:
    closed_count = 0
    target_substr = f"profile_{profile_name}".lower()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()
                if target_substr in cmd_str:
                    proc.kill()
                    closed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    if closed_count > 0:
        time.sleep(0.5)
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    p_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile_name}"
    for lock_name in ["lockfile", "SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lf = p_dir / lock_name
        if lf.exists():
            try:
                lf.unlink()
            except Exception:
                pass
    return closed_count

def check_chrome_running_for_profile(profile_name: str) -> bool:
    target_substr = f"profile_{profile_name}".lower()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                cmdline = proc.info.get('cmdline') or []
                cmd_str = " ".join(cmdline).lower()
                if target_substr in cmd_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def watch_chrome_login_exit(profile_id: str, profile_name: str, db_path: Path):
    def _worker():
        time.sleep(5.0)
        while True:
            if not check_chrome_running_for_profile(profile_name):
                print(f"[LoginWatcher] 检测到账号 [{profile_name}] 的 Chrome 登录窗口已关闭，正在启动后台全自动 Onboarding (协议确认与工程创建)...")
                try:
                    from .onboard import ensure_profile_onboarded
                    bound_project = ensure_profile_onboarded(profile_name)
                    if bound_project:
                        print(f"[LoginWatcher] 账号 [{profile_name}] 协议与专属工程已全自动绑定完毕: [{bound_project}]")
                    else:
                        print(f"[LoginWatcher] 账号 [{profile_name}] 未能获取到工程，等待任务运行时自愈")
                except Exception as oe:
                    print(f"[LoginWatcher] 账号 [{profile_name}] 后台自动 Onboarding 警告: {oe}")

                p = db.get_profile_by_id(profile_id, db_path)
                if p and p.status in ("cooldown", "busy", "auth_expired"):
                    db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=db_path)
                    conn = db.get_db_connection(db_path)
                    with conn:
                        conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
                    conn.close()
                    print(f"[LoginWatcher] 账号 [{profile_name}] 状态已自动恢复为空闲就绪")
                break
            time.sleep(3.0)
    t = threading.Thread(target=_worker, daemon=True, name=f"LoginWatcher-{profile_name}")
    t.start()

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
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
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
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    count = close_chrome_for_profile(p.name)
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
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    
    if check_chrome_running_for_profile(p.name):
        return {
            "valid": False,
            "error_code": "PROFILE_LOCKED",
            "message": f"账号 [{p.name}] 的 Chrome 窗口当前正在桌面上运行，请先在桌面关闭该 Chrome 窗口，或点击【⏹ 关占用 Chrome】后重试验证。"
        }

    # 使用无头浏览器综合探测 Gemini 网页版与 Google Flow 登录状态
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    profile_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{p.name}"
    
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            launch_args = [
                                "--no-sandbox"
            ]
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir.resolve()),
                channel="chrome",
                headless=True,
                args=launch_args
            )
            try:
                page = browser.new_page()
                
                # 1. 探测 Gemini 状态
                gemini_ok = False
                try:
                    page.goto("https://gemini.google.com/app", timeout=20000)
                    page.wait_for_timeout(2000)
                    input_selector = 'div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"], textarea'
                    try:
                        page.wait_for_selector(input_selector, timeout=6000)
                        gemini_ok = True
                    except Exception:
                        gemini_ok = False
                except Exception:
                    gemini_ok = False

                # 2. 探测 Flow 状态 (优先 flow.google.com，兼容 labs.google)
                flow_ok = False
                try:
                    page.goto("https://flow.google.com/", timeout=25000, wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    if "accounts.google.com" not in page.url and ("flow.google.com" in page.url or "project" in page.url):
                        flow_ok = True
                    else:
                        r = page.request.get("https://labs.google/fx/api/auth/session")
                        if r.status == 200 and '"email"' in r.text():
                            flow_ok = True
                except Exception:
                    flow_ok = False
                
                if gemini_ok or flow_ok:
                    # 至少有一路就绪，重置为空闲可用状态
                    db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=DB_PATH)
                    conn = db.get_db_connection(DB_PATH)
                    try:
                        with conn:
                            conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
                    finally:
                        conn.close()
                    
                    status_parts = []
                    if gemini_ok:
                        status_parts.append("Gemini: ✅已登录")
                    else:
                        status_parts.append("Gemini: ⚠️未登录")
                    if flow_ok:
                        status_parts.append("Google Flow: ✅已登录")
                    else:
                        status_parts.append("Google Flow: ⚠️未登录")

                    return {
                        "valid": True,
                        "status": "idle",
                        "message": f"🎉 验证成功！账号 [{p.name}] 授权有效 ({', '.join(status_parts)})，已重置为空闲就绪！"
                    }
                else:
                    # 尝试自动消除一次性服务协议/引导弹窗并激活
                    browser.close()
                    onboard_res = auto_onboard_profile(p.name)
                    if onboard_res.get("success"):
                        db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=DB_PATH)
                        conn = db.get_db_connection(DB_PATH)
                        try:
                            with conn:
                                conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
                        finally:
                            conn.close()
                        return {
                            "valid": True,
                            "status": "idle",
                            "message": f"🎉 自动完成服务条款同意与项目初始化！账号 [{p.name}] 已成功转为空闲就绪！"
                        }
                    else:
                        db.update_profile_status(profile_id, status="auth_expired", cooldown_until=None, db_path=DB_PATH)
                        return {
                            "valid": False,
                            "error_code": "AUTH_EXPIRED",
                            "message": f"账号未检测到有效登录态或条款未同意。请点击【🔑 登录 Flow】在打开的 Chrome 中点击一次【同意/继续】，随后关闭 Chrome 即可。"
                        }
            finally:
                browser.close()
    except Exception as e:
        err_str = str(e).lower()
        if any(k in err_str for k in ["target closed", "lock", "singleton", "already running", "in use"]):
            return {
                "valid": False,
                "error_code": "PROFILE_LOCKED",
                "message": f"Chrome Profile 正在被独占打开，请先关闭桌面 Chrome 窗口或点击【⏹ 关占用 Chrome】后再试。"
            }
        return {
            "valid": False,
            "error_code": "VERIFY_ERROR",
            "message": f"探测登录态时发生异常: {e}"
        }


@app.post("/api/profiles/{profile_id}/auto-onboard")
def api_auto_onboard(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    
    res = auto_onboard_profile(p.name)
    if res.get("success"):
        db.update_profile_status(profile_id, status="idle", cooldown_until=None, db_path=DB_PATH)
        conn = db.get_db_connection(DB_PATH)
        try:
            with conn:
                conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (profile_id,))
        finally:
            conn.close()
    return res

@app.post("/api/profiles/auto-onboard-all")
def api_auto_onboard_all():
    profiles = db.list_profiles(DB_PATH)
    results = []
    for p in profiles:
        if p.status == "busy":
            continue
        res = auto_onboard_profile(p.name)
        if res.get("success"):
            db.update_profile_status(p.id, status="idle", cooldown_until=None, db_path=DB_PATH)
            conn = db.get_db_connection(DB_PATH)
            try:
                with conn:
                    conn.execute("UPDATE profiles SET cooldown_until = NULL WHERE id = ?", (p.id,))
            finally:
                conn.close()
        results.append({"profile_id": p.id, "name": p.name, "result": res})
    return {"results": results}

@app.post("/api/profiles/{profile_id}/launch-gemini-login")
def launch_gemini_login(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    profile_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{p.name}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    chrome_paths = [
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"
    ]
    chrome_bin = None
    for cp in chrome_paths:
        if cp.exists():
            chrome_bin = cp
            break
            
    if not chrome_bin:
        raise HTTPException(status_code=500, detail="系统未找到 Google Chrome 可执行文件")

    cmd = [
        str(chrome_bin),
        f"--user-data-dir={str(profile_dir.resolve())}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gemini.google.com/app"
    ]
    try:
        subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        watch_chrome_login_exit(profile_id, p.name, DB_PATH)
        return {"success": True, "message": f"已启动独立 Chrome 打开 Gemini 网页版 [{p.name}]，请完成 Google 登录授权"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动登录窗口失败: {e}")

@app.post("/api/profiles/{profile_id}/launch-login")
def launch_login(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    
    python_bin = GFLOW_DIR / ".venv" / "Scripts" / "python.exe"
    if not python_bin.exists():
        python_bin = Path(sys.executable)

    cmd = [str(python_bin), "-m", "gflow_cli", "auth", "login", "--profile", p.name]
    try:
        # Launch independently on Windows without blocking
        subprocess.Popen(
            cmd,
            cwd=str(GFLOW_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        watch_chrome_login_exit(profile_id, p.name, DB_PATH)
        return {"success": True, "message": f"已启动独立 Chrome 窗口进行账号 [{p.name}] 登录"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动登录窗口失败: {e}")

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
        if OUTPUTS_DIR in p.parents or p.parent == OUTPUTS_DIR:
            urls.append(f"/media/outputs/{p.name}")
        else:
            urls.append(f"/media/file?path={p.as_posix()}")
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
            "error_code": t.error_code,
            "error_message": t.error_message
        })
    return res

class BatchTasksReq(BaseModel):
    task_ids: List[str]


@app.delete("/api/tasks/{task_id}")
def delete_single_task(task_id: str):
    try:
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


def format_ordered_filename(task, index: Optional[int] = None, ext: Optional[str] = None) -> str:
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

    return f"{prefix}_{desc}_{eng}_{ratio}{ext}"

def get_task_sort_key(task_tuple):
    t = task_tuple[0] if isinstance(task_tuple, (tuple, list)) else task_tuple
    raw_prompt = getattr(t, 'prompt', None) or (t.get('prompt') if isinstance(t, dict) else '') or ''
    created_at = getattr(t, 'created_at', None) or (t.get('created_at') if isinstance(t, dict) else '') or ''
    shot_num, sub = parse_shot_info(raw_prompt)
    if shot_num is not None:
        return (0, shot_num, sub, str(created_at))
    else:
        return (1, 999999, '', str(created_at))


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
            if imgs and Path(imgs[0]).is_file():
                file_path = Path(imgs[0])
                media_type = "image/png"
                ext = file_path.suffix or ".png"
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
        p = None
        if t.output_video_path and Path(t.output_video_path).is_file():
            p = Path(t.output_video_path)
        elif getattr(t, "output_audio_path", None) and Path(t.output_audio_path).is_file():
            p = Path(t.output_audio_path)
        elif getattr(t, "output_image_paths", None):
            try:
                imgs = json.loads(t.output_image_paths) if isinstance(t.output_image_paths, str) else t.output_image_paths
                if imgs and Path(imgs[0]).is_file():
                    p = Path(imgs[0])
            except Exception:
                pass
        if p and p.is_file():
            tasks_to_pack.append((t, local_file(str(p))))
            
    if not tasks_to_pack:
        raise HTTPException(status_code=400, detail="选中的任务中没有已完成可下载的媒体成片")
        
    # 严格按照镜头序号升序排序（镜头01、02、03A、03B... 无镜头的按创建时间升序排列）
    tasks_to_pack.sort(key=get_task_sort_key)

    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="video_farm_batch_")
    temp_zip_path = Path(temp_zip.name)
    temp_zip.close()
    
    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
            for idx, (t, p) in enumerate(tasks_to_pack, 1):
                arc_name = format_ordered_filename(t, index=idx, ext=p.suffix)
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


@app.post("/api/tasks/create")
async def create_task(
    prompt: str = Form(...),
    engine: str = Form("flow"),
    task_type: str = Form("video"),
    model: str = Form("veo-lite"),
    start_image: Optional[UploadFile] = File(None),
    end_image: Optional[UploadFile] = File(None),
    start_image_path: Optional[str] = Form(None),
    end_image_path: Optional[str] = Form(None),
    input_video: Optional[UploadFile] = File(None),
    input_video_path: Optional[str] = Form(None),
    priority: int = Form(10),
    aspect_ratio: str = Form("9:16"),
    duration_sec: int = Form(8),
    assigned_profile_id: Optional[str] = Form(None),
    require_clean_watermark: bool = Form(False)
):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")
    if task_type == "audio":
        raise HTTPException(status_code=400, detail="本地配音功能已下线，不支持提交音频配音任务")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_upload_dir = UPLOADS_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    
    start_dest_str = ""
    end_dest_str = ""
    input_video_dest_str = ""
    
    # 优先解析上传的文件；若无上传文件，则使用传入的本地文件路径
    if start_image and start_image.filename:
        start_ext = Path(start_image.filename or "start.png").suffix or ".png"
        start_dest = task_upload_dir / f"start{start_ext}"
        with open(start_dest, "wb") as f:
            shutil.copyfileobj(start_image.file, f)
        start_dest_str = str(start_dest.resolve())
    elif start_image_path and Path(start_image_path).exists():
        start_dest_str = str(Path(start_image_path).resolve())

    if end_image and end_image.filename:
        end_ext = Path(end_image.filename or "end.png").suffix or ".png"
        end_dest = task_upload_dir / f"end{end_ext}"
        with open(end_dest, "wb") as f:
            shutil.copyfileobj(end_image.file, f)
        end_dest_str = str(end_dest.resolve())
    elif end_image_path and Path(end_image_path).exists():
        end_dest_str = str(Path(end_image_path).resolve())

    if input_video and input_video.filename:
        vid_ext = Path(input_video.filename or "input_video.mp4").suffix or ".mp4"
        vid_dest = task_upload_dir / f"input_video{vid_ext}"
        with open(vid_dest, "wb") as f:
            shutil.copyfileobj(input_video.file, f)
        input_video_dest_str = str(vid_dest.resolve())
    elif input_video_path and Path(input_video_path).exists():
        input_video_dest_str = str(Path(input_video_path).resolve())
    

    target_prof_id = assigned_profile_id.strip() if assigned_profile_id and assigned_profile_id.strip() else None
    if not target_prof_id or target_prof_id.lower() in ("auto", "none", "null"):
        best_p = db.pick_best_profile(require_clean=require_clean_watermark, db_path=DB_PATH) or db.pick_best_profile(require_clean=False, db_path=DB_PATH)
        if best_p:
            target_prof_id = best_p.id

    task = Task(
        id=task_id,
        prompt=prompt.strip(),
        start_image_path=start_dest_str,
        end_image_path=end_dest_str,
        input_video_path=input_video_dest_str,
        engine=engine,
        task_type=task_type,
        model=model.strip() if model else ("gemini-audio" if task_type == "audio" else "veo-lite"),
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
        status="queued",
        priority=priority,
        require_clean_watermark=require_clean_watermark,
        assigned_profile_id=target_prof_id
    )
    
    db.add_task(task, DB_PATH)
    if task_type == "audio":
        engine_desc = "Gemini 多模态音频/配音工作台"
    else:
        engine_desc = "Google Flow (首尾帧模式)" if engine == "flow" else "Gemini 网页版"
    db.log_task_event(task_id, "TASK_CREATED_WEB", f"通过Web控制台提交任务[{task_type}]，引擎: {engine_desc}，模型: {task.model}", db_path=DB_PATH)
    return {"id": task_id, "status": "queued", "engine": engine, "task_type": task_type, "message": f"{engine_desc}任务创建成功并已加入队列"}

@app.post("/api/tasks/create-audio")
async def create_audio_task_endpoint():
    return {"id": "", "status": "disabled", "message": "本地配音功能已下线", "success": False}

@app.post("/api/tasks/create-image")
async def create_image_task_endpoint(
    prompt: str = Form(...),
    model: str = Form("nano-pro"),
    aspect_ratio: str = Form("9:16"),
    ref_image: Optional[UploadFile] = File(None),
    ref_image_path: Optional[str] = Form(None),
    priority: int = Form(10),
    assigned_profile_id: Optional[str] = Form(None)
):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="生图提示词不能为空")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_upload_dir = UPLOADS_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    
    ref_dest_str = ""
    if ref_image and ref_image.filename:
        ref_ext = Path(ref_image.filename or "ref.png").suffix or ".png"
        ref_dest = task_upload_dir / f"ref{ref_ext}"
        with open(ref_dest, "wb") as f:
            shutil.copyfileobj(ref_image.file, f)
        ref_dest_str = str(ref_dest.resolve())
    elif ref_image_path and Path(ref_image_path).exists():
        ref_dest_str = str(Path(ref_image_path).resolve())

    target_prof_id = assigned_profile_id.strip() if assigned_profile_id and assigned_profile_id.strip() else None
    if not target_prof_id or target_prof_id.lower() in ("auto", "none", "null"):
        best_p = db.pick_best_profile(require_clean=False, db_path=DB_PATH)
        if best_p:
            target_prof_id = best_p.id

    task = Task(
        id=task_id,
        prompt=prompt.strip(),
        start_image_path=ref_dest_str,
        end_image_path="",
        engine="flow",
        task_type="image",
        model=model.strip() if model else "nano-pro",
        aspect_ratio=aspect_ratio,
        duration_sec=0,
        status="queued",
        priority=priority,
        assigned_profile_id=target_prof_id
    )
    
    db.add_task(task, DB_PATH)
    mode_desc = "图生图 (i2i)" if ref_dest_str else "文生图 (t2i)"
    db.log_task_event(task_id, "TASK_CREATED_WEB", f"通过Web控制台提交图像任务 ({mode_desc})，模型: {task.model}", db_path=DB_PATH)
    return {"id": task_id, "status": "queued", "task_type": "image", "message": f"图像任务创建成功，已提交调度排队"}

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

    # 确定整批任务绑定的专属执行账号（未显式指定时采用动态负载均衡，避免单账号阻塞整批队列）
    target_prof = None
    if top_profile_id and top_profile_id.lower() not in ("auto", "none", "null", ""):
        target_prof = db.get_profile_by_id(top_profile_id, DB_PATH) or db.get_profile_by_name(top_profile_id, DB_PATH)

    locked_profile_id = target_prof.id if target_prof else None
    locked_profile_name = target_prof.name if target_prof else "账号池动态调度"

    created_ids = []
    for item in raw_shots:
        if not isinstance(item, dict):
            continue
        prompt = (item.get("prompt") or item.get("description") or item.get("text") or item.get("caption") or item.get("content") or "").strip()
        if not prompt:
            continue

        raw_start = (item.get("start_image_path") or item.get("start_image") or item.get("initial_frame") or item.get("start_frame") or item.get("first_frame") or item.get("first_image") or "").strip()
        raw_end = (item.get("end_image_path") or item.get("end_image") or item.get("end_frame") or item.get("last_frame") or item.get("final_frame") or item.get("last_image") or "").strip()

        s_path_str = ""
        if raw_start:
            s_path = Path(raw_start)
            if not s_path.is_absolute():
                s_path = (BASE_DIR / s_path).resolve()
            s_path_str = str(s_path)

        e_path_str = ""
        if raw_end:
            e_path = Path(raw_end)
            if not e_path.is_absolute():
                e_path = (BASE_DIR / e_path).resolve()
            e_path_str = str(e_path)

        engine = str(item.get("engine") or top_engine or "flow").strip().lower()
        if engine not in ["flow", "vids", "gemini"]:
            engine = "flow"

        model = str(item.get("model") or "").strip()
        aspect_ratio = str(item.get("aspect_ratio") or item.get("ratio") or "9:16").strip()

        try:
            duration_sec = int(item.get("duration_sec") or item.get("duration") or item.get("seconds") or 8)
        except Exception:
            duration_sec = 8

        try:
            priority = int(item.get("priority") or 10)
        except Exception:
            priority = 10

        # 单项显式指定优先；若未指定则设为 None，由账号池空闲账号动态抢占调度
        item_pid = str(item.get("assigned_profile_id") or item.get("profile_id") or "").strip()
        final_assigned_profile = item_pid or locked_profile_id or None

        task_type = str(item.get("task_type") or "video").strip().lower()
        if task_type not in ["video", "image", "audio"]:
            task_type = "video"

        raw_input_vid = (item.get("input_video_path") or item.get("input_video") or item.get("reference_video") or "").strip()
        input_vid_str = ""
        if raw_input_vid:
            v_path = Path(raw_input_vid)
            if not v_path.is_absolute():
                v_path = (BASE_DIR / v_path).resolve()
            input_vid_str = str(v_path)

        if task_type == "audio":
            engine = "gemini"
            if not model or model == "veo-lite":
                model = "gemini-audio"
        elif engine == "vids":
            if not model:
                model = "Omni (1080p)"

        t_id = f"task_{uuid.uuid4().hex[:12]}"
        task = Task(
            id=t_id,
            prompt=prompt,
            start_image_path=s_path_str,
            end_image_path=e_path_str,
            input_video_path=input_vid_str,
            engine=engine,
            task_type=task_type,
            model=model,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            status="queued",
            priority=priority,
            assigned_profile_id=final_assigned_profile
        )
        db.add_task(task, DB_PATH)
        db.log_task_event(t_id, "TASK_CREATED_BATCH", f"通过Web控制台批量导入分镜 ({engine})，分配策略: [{'锁定专属账号: ' + locked_profile_name if locked_profile_id else '账号池动态负载均衡'}]", db_path=DB_PATH)
        created_ids.append(t_id)

    if not created_ids:
        raise HTTPException(status_code=400, detail="未能识别到有效分镜，每项至少需包含 prompt 提示词")

    return {
        "created_count": len(created_ids),
        "task_ids": created_ids,
        "assigned_profile_id": locked_profile_id,
        "assigned_profile_name": locked_profile_name,
        "message": f"成功创建 {len(created_ids)} 个分镜任务！已全量锁定使用账号 [{locked_profile_name}] 顺次排队生成，中途绝不跳号。"
    }

@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str):
    try:
        return db.transition_task(task_id, "retry", DB_PATH)
    except KeyError:
        raise HTTPException(404, "Task未找到")
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))

class BatchTasksReq(BaseModel):
    task_ids: list[str]

@app.post("/api/tasks/{task_id}/stop")
def stop_task_endpoint(task_id: str):
    """强行中止正在运行或排队中的任务，立即终止执行进程并释放账号与槽位"""
    try:
        res = db.transition_task(task_id, "stop", DB_PATH)
        if mgr.scheduler:
            mgr.scheduler.cancel_task(task_id)
        db.log_task_event(task_id, "TASK_STOPPED", "用户手动强行中止任务并释放资源", db_path=DB_PATH)
        return {"success": True, "task": res, "message": f"任务 [{task_id}] 已成功强行中止"}
    except KeyError:
        raise HTTPException(404, "Task未找到")
    except db.TaskOperationConflict as e:
        raise HTTPException(409, str(e))

@app.post("/api/tasks/batch/cancel")
def batch_cancel_tasks(req: BatchTasksReq):
    cancelled = []
    for tid in req.task_ids:
        try:
            db.transition_task(tid, "stop", DB_PATH)
            if mgr.scheduler:
                mgr.scheduler.cancel_task(tid)
            db.log_task_event(tid, "TASK_CANCELLED", "用户批量强行中止任务并释放资源", db_path=DB_PATH)
            cancelled.append(tid)
        except Exception:
            pass
    return {"success": True, "cancelled_count": len(cancelled), "cancelled_ids": cancelled, "message": f"已成功停止/取消 {len(cancelled)} 个任务"}

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

@app.get("/media/outputs/{filename}")
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

def run_in_clean_thread(fn, *args, **kwargs):
    res_box = {}
    err_box = {}
    def _runner():
        try:
            res_box['data'] = fn(*args, **kwargs)
        except Exception as e:
            err_box['err'] = e
    th = threading.Thread(target=_runner, daemon=True)
    th.start()
    th.join(timeout=180)
    if th.is_alive():
        return {"success": False, "error_message": "多模态执行超时（超过180秒）"}
    if 'err' in err_box:
        raise err_box['err']
    return res_box.get('data') or {"success": False, "error_message": "执行未返回有效结果"}

@app.post("/api/profiles/{profile_id}/unlock")
def unlock_profile_endpoint(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH) or db.get_profile_by_name(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    killed = close_chrome_for_profile(p.name)
    return {"success": True, "killed_processes": killed, "message": f"已成功释放账号 [{p.name}] 占用并清理目录锁"}

@app.post("/api/profiles/{profile_id}/launch-chrome")
def launch_chrome_for_gemini(profile_id: str):
    p = db.get_profile_by_id(profile_id, DB_PATH) or db.get_profile_by_name(profile_id, DB_PATH)
    if not p:
        raise HTTPException(status_code=404, detail="Profile未找到")
    close_chrome_for_profile(p.name)
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    profile_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{p.name}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not Path(chrome_path).exists():
        chrome_path = "chrome"
    subprocess.Popen([
        chrome_path,
        f"--user-data-dir={str(profile_dir)}",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gemini.google.com/app"
    ])
    return {"success": True, "message": f"已在桌面启动账号 [{p.name}] 独立 Chrome 窗口，请在浏览器中登录 Google/Gemini。"}

@app.get("/api/gemini/messages")
def get_gemini_messages(session_id: str = "default", limit: int = 100):
    msgs = db.list_gemini_messages(session_id=session_id, limit=limit, db_path=DB_PATH)
    return {"messages": msgs}

@app.delete("/api/gemini/messages")
def delete_gemini_messages(session_id: str = "default"):
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

    # 解析目标 Profile（严格锁定账号，严禁随机轮转打乱对话上下文）
    target_profile = None
    if profile_id and profile_id.strip() and profile_id.lower() not in ("auto", "none", "null"):
        target_profile = db.get_profile_by_id(profile_id.strip(), DB_PATH) or db.get_profile_by_name(profile_id.strip(), DB_PATH)

    # 若未明确指定新账号，自动继承当前 session 既有绑定的 Profile，保持对话上下文严格在同一账号下
    if not target_profile:
        prior_msgs = db.list_gemini_messages(session_id=session_id, limit=8, db_path=DB_PATH)
        for pm in prior_msgs:
            if pm.get("profile_id"):
                cand = db.get_profile_by_id(pm["profile_id"], DB_PATH) or db.get_profile_by_name(pm.get("profile_name", ""), DB_PATH)
                if cand:
                    target_profile = cand
                    break

    # 若为全新的会话且未指定账号，默认固定使用第一个已启用的账号，严禁动态切号
    if not target_profile:
        all_profs = db.list_profiles(DB_PATH)
        if all_profs:
            target_profile = all_profs[0]

    prof_name = target_profile.name if target_profile else "Auto"
    prof_id = target_profile.id if target_profile else None

    # 保存用户消息
    user_msg = db.add_gemini_message({
        "session_id": session_id,
        "profile_id": prof_id,
        "profile_name": prof_name,
        "role": "user",
        "mode": mode,
        "content": message.strip(),
        "attachments_json": json.dumps(attachments, ensure_ascii=False),
        "status": "completed"
    }, DB_PATH)

    if not target_profile:
        ai_msg = db.add_gemini_message({
            "session_id": session_id,
            "role": "assistant",
            "mode": mode,
            "content": "系统未检测到可用 Google Profile，请先在【账号管理】添加或初始化 Profile。",
            "status": "failed"
        }, DB_PATH)
        return {"success": False, "user_message": user_msg, "assistant_message": ai_msg}

    # 针对纯文字自由对话模式，组装前序对话上下文（提取最近历史轮次），赋予 Gemini 网页端连贯记忆
    actual_prompt = message.strip()
    if mode == "chat" and not video_dest_str and not image_dest_str:
        prior_history = db.list_gemini_messages(session_id=session_id, limit=8, db_path=DB_PATH)
        context_turns = [
            m for m in prior_history 
            if m.get("id") != user_msg.get("id") and m.get("content") and not m.get("content", "").startswith("⚠️")
        ]
        if context_turns:
            history_lines = []
            for m in context_turns[-4:]:
                r_label = "用户" if m.get("role") == "user" else "Gemini"
                c_snippet = m.get("content", "").strip().replace("\n", " ")
                if len(c_snippet) > 100:
                    c_snippet = c_snippet[:100] + "..."
                history_lines.append(f"{r_label}: {c_snippet}")
            if history_lines:
                history_block = "\n".join(history_lines)
                actual_prompt = f"【前序对话记录】\n{history_block}\n\n【用户最新问题】\n{message.strip()}"

    # 调用 Gemini 多模态工作台 Worker（在纯净独立线程中运行，完全隔离 FastAPI 的 asyncio loop）
    worker = mgr.scheduler.gemini_worker if (mgr.scheduler and hasattr(mgr.scheduler, "gemini_worker")) else GeminiWebWorker(output_dir=OUTPUTS_DIR)
    res = run_in_clean_thread(
        worker.execute_multimodal_interaction,
        profile=target_profile,
        prompt=actual_prompt,
        mode=mode,
        video_path=video_dest_str,
        image_path=image_dest_str,
        voice=voice,
        aspect_ratio=aspect_ratio
    )

    ai_text = res.get("text")
    if not ai_text:
        if not res.get("success") and res.get("error_message"):
            ai_text = f"⚠️ {res.get('error_message')}"
        elif res.get("audio_url") or res.get("image_urls"):
            ai_text = "（多模态产物已生成，请在下方试听或查看）"
        else:
            ai_text = "Gemini 已处理完成"
    if res.get("warning"):
        ai_text += f"\n\n> ⚠️ {res.get('warning')}"

    ai_msg = db.add_gemini_message({
        "session_id": session_id,
        "profile_id": target_profile.id,
        "profile_name": target_profile.name,
        "role": "assistant",
        "mode": mode,
        "content": ai_text,
        "audio_url": res.get("audio_url"),
        "audio_path": res.get("audio_path"),
        "image_urls_json": json.dumps(res.get("image_urls") or [], ensure_ascii=False),
        "status": "completed" if res.get("success") else "failed",
        "error_message": res.get("error_message")
    }, DB_PATH)

    # 本地音频配音功能已下线，不登记音频任务

    return {
        "success": res.get("success", False),
        "user_message": user_msg,
        "assistant_message": ai_msg,
        "error_message": res.get("error_message"),
        "warning": res.get("warning")
    }


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
