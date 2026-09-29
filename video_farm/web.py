from __future__ import annotations
from .onboard import auto_onboard_profile
import os
import sys
import time
import json
import uuid
import shutil
import threading
import subprocess
import psutil
import urllib.parse
from pathlib import Path
from typing import Optional, List, Dict, Any

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import db
from .models import Task, Profile
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
                    proc.terminate()
                    closed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    if closed_count > 0:
        time.sleep(1.0)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    tasks = db.list_tasks(limit=500, db_path=DB_PATH)
    
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
    
    task_stats = {
        "total": len(tasks),
        "queued": sum(1 for t in tasks if t.status in ("queued", "retry_wait")),
        "running": sum(1 for t in tasks if t.status in ("dispatching", "running", "verifying")),
        "completed": sum(1 for t in tasks if t.status == "completed"),
        "failed": sum(1 for t in tasks if t.status == "failed"),
        "cancelled": sum(1 for t in tasks if t.status == "cancelled")
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
                "--disable-blink-features=AutomationControlled",
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
def get_tasks(status: Optional[str] = None, limit: int = 100):
    tasks = db.list_tasks(status=status, limit=limit, db_path=DB_PATH)
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
        img_paths, img_urls = _resolve_output_images(t)
        
        qa_task_dir = QA_DIR / t.id
        first_frame_url = f"/media/qa/{t.id}/first_frame.png" if (qa_task_dir / "first_frame.png").exists() else None
        last_frame_url = f"/media/qa/{t.id}/last_frame.png" if (qa_task_dir / "last_frame.png").exists() else None
        start_img_url = _resolve_image_url(t.start_image_path, t.id, "start")
        end_img_url = _resolve_image_url(t.end_image_path, t.id, "end")

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
    model: str = Form("veo-lite"),
    start_image: Optional[UploadFile] = File(None),
    end_image: Optional[UploadFile] = File(None),
    start_image_path: Optional[str] = Form(None),
    end_image_path: Optional[str] = Form(None),
    priority: int = Form(10),
    aspect_ratio: str = Form("9:16"),
    duration_sec: int = Form(8),
    assigned_profile_id: Optional[str] = Form(None),
    require_clean_watermark: bool = Form(False)
):
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")
    
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task_upload_dir = UPLOADS_DIR / task_id
    task_upload_dir.mkdir(parents=True, exist_ok=True)
    
    start_dest_str = ""
    end_dest_str = ""
    
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
    
    if engine == "flow":
        # Google Flow 支持 首尾帧插值(i2v with end frame)、单首帧(i2v)或纯文生视频(t2v)
        pass

    task = Task(
        id=task_id,
        prompt=prompt.strip(),
        start_image_path=start_dest_str,
        end_image_path=end_dest_str,
        engine=engine,
        task_type="video",
        model=model.strip() if model else "veo-lite",
        aspect_ratio=aspect_ratio,
        duration_sec=duration_sec,
        status="queued",
        priority=priority,
        require_clean_watermark=require_clean_watermark,
        assigned_profile_id=assigned_profile_id or None
    )
    
    db.add_task(task, DB_PATH)
    engine_desc = "Google Flow (首尾帧模式)" if engine == "flow" else "Gemini 网页版"
    db.log_task_event(task_id, "TASK_CREATED_WEB", f"通过Web控制台提交视频任务，引擎: {engine_desc}，模型: {task.model}", db_path=DB_PATH)
    return {"id": task_id, "status": "queued", "engine": engine, "message": f"{engine_desc}任务创建成功并已加入队列"}

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
        assigned_profile_id=assigned_profile_id or None
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
    if isinstance(body, list):
        raw_shots = body
    elif isinstance(body, dict):
        top_profile_id = str(body.get("profile_id") or body.get("assigned_profile_id") or "").strip()
        for k in ["shots", "tasks", "items", "data", "list", "scenes", "storyboard"]:
            if k in body and isinstance(body[k], list):
                raw_shots = body[k]
                break
        if not raw_shots and ("prompt" in body or "text" in body or "description" in body):
            raw_shots = [body]

    if not raw_shots:
        raise HTTPException(status_code=400, detail="分镜列表不能为空，需提供镜头数组")

    # 确定整批任务绑定的专属执行账号（避免中途跳换账号）
    target_prof = None
    if top_profile_id and top_profile_id.lower() not in ("auto", "none", "null"):
        target_prof = db.get_profile_by_id(top_profile_id, DB_PATH) or db.get_profile_by_name(top_profile_id, DB_PATH)

    if not target_prof:
        # 自动锁定当前最优空闲主账号（优先无水印、空闲就绪）
        target_prof = db.pick_best_profile(require_clean=True, db_path=DB_PATH) or db.pick_best_profile(require_clean=False, db_path=DB_PATH)

    locked_profile_id = target_prof.id if target_prof else None
    locked_profile_name = target_prof.name if target_prof else "系统调度"

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

        engine = str(item.get("engine") or "flow").strip().lower()
        if engine not in ["flow", "gemini"]:
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

        # 单项显式指定优先，未指定则统一锁定到当前主账号
        item_pid = str(item.get("assigned_profile_id") or item.get("profile_id") or "").strip()
        final_assigned_profile = item_pid or locked_profile_id

        t_id = f"task_{uuid.uuid4().hex[:12]}"
        task = Task(
            id=t_id,
            prompt=prompt,
            start_image_path=s_path_str,
            end_image_path=e_path_str,
            engine=engine,
            task_type="video",
            model=model,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            status="queued",
            priority=priority,
            assigned_profile_id=final_assigned_profile
        )
        db.add_task(task, DB_PATH)
        db.log_task_event(t_id, "TASK_CREATED_BATCH", f"通过Web控制台批量导入分镜 ({engine})，已锁定绑定账号: [{locked_profile_name}]", db_path=DB_PATH)
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
    t = db.get_task(task_id, DB_PATH)
    if not t:
        raise HTTPException(status_code=404, detail="Task未找到")
    
    conn = db.get_db_connection(DB_PATH)
    try:
        with conn:
            conn.execute("""
            UPDATE tasks
            SET status = 'queued', assigned_profile_id = NULL, retry_count = 0, error_code = NULL, error_message = NULL, updated_at = ?
            WHERE id = ?
            """, (time.strftime("%Y-%m-%dT%H:%M:%S%z"), task_id))
    finally:
        conn.close()
        
    db.log_task_event(task_id, "MANUAL_RETRY", "用户通过Web控制台手动触发重试", db_path=DB_PATH)
    return {"id": task_id, "status": "queued"}

@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    t = db.get_task(task_id, DB_PATH)
    if not t:
        raise HTTPException(status_code=404, detail="Task未找到")
    
    conn = db.get_db_connection(DB_PATH)
    try:
        with conn:
            conn.execute("UPDATE tasks SET status = 'cancelled', updated_at = ? WHERE id = ?",
                         (time.strftime("%Y-%m-%dT%H:%M:%S%z"), task_id))
    finally:
        conn.close()
        
    db.log_task_event(task_id, "MANUAL_CANCEL", "用户通过Web控制台手动取消任务", db_path=DB_PATH)
    return {"id": task_id, "status": "cancelled"}

class OpenFolderReq(BaseModel):
    target: str = "outputs"
    task_id: Optional[str] = None

@app.post("/api/system/open-folder")
def open_system_folder(req: OpenFolderReq):
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
    work_dir = DATA_DIR / f"pipeline_{spec.project_id}"
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
        p = Path(path).resolve()
        if p.exists() and p.is_file():
            target_path = p
            filename = target_path.name

    if not target_path or not target_path.exists():
        raise HTTPException(status_code=404, detail="下载文件不存在")
    return FileResponse(str(target_path), filename=filename, media_type="application/octet-stream")

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
    if not p.exists() or OUTPUTS_DIR not in p.parents:
        raise HTTPException(status_code=404, detail="文件未找到")
    if p.suffix.lower() == ".mp4":
        return FileResponse(str(p), media_type="video/mp4")
    elif p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        return FileResponse(str(p), media_type="image/png")
    return FileResponse(str(p), media_type="application/octet-stream")

@app.get("/media/qa/{task_id}/{filename}")
def serve_qa_file(task_id: str, filename: str):
    p = (QA_DIR / task_id / filename).resolve()
    if not p.exists() or QA_DIR not in p.parents:
        raise HTTPException(status_code=404, detail="质检切片未找到")
    media_type = "image/png" if p.suffix == ".png" else "application/octet-stream"
    return FileResponse(str(p), media_type=media_type)

@app.get("/media/uploads/{task_id}/{filename}")
def serve_upload_file(task_id: str, filename: str):
    p = (UPLOADS_DIR / task_id / filename).resolve()
    if not p.exists() or UPLOADS_DIR not in p.parents:
        raise HTTPException(status_code=404, detail="上传素材未找到")
    media_type = "image/png" if p.suffix in (".png", ".jpg", ".jpeg", ".webp") else "application/octet-stream"
    return FileResponse(str(p), media_type=media_type)

@app.get("/api/pipeline/file-preview")
def api_pipeline_file_preview(path: str = Query(...)):
    p = Path(path).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = p.suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".mp4", ".mp3", ".wav"}
    if ext not in allowed:
        raise HTTPException(status_code=400, detail="不支持此类型文件回显预览")
    media_type = "image/png"
    if ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".webp":
        media_type = "image/webp"
    elif ext == ".gif":
        media_type = "image/gif"
    elif ext == ".mp4":
        media_type = "video/mp4"
    elif ext in (".mp3", ".wav"):
        media_type = "audio/mpeg"
    return FileResponse(str(p), media_type=media_type)

@app.get("/media/file")
def serve_arbitrary_local_file(path: str = Query(...)):
    p = Path(path).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = p.suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".mp4", ".mp3", ".wav"}
    if ext not in allowed:
        if not (BASE_DIR in p.parents or p == BASE_DIR or DATA_DIR in p.parents):
            raise HTTPException(status_code=403, detail="禁止跨工作区访问未受控文件")
    media_type = "application/octet-stream"
    if ext in (".png", ".webp", ".bmp"):
        media_type = "image/png"
    elif ext in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif ext == ".mp4":
        media_type = "video/mp4"
    return FileResponse(str(p), media_type=media_type)

from .vids_router import router as vids_router
app.include_router(vids_router)

@app.get("/vids")
def serve_vids_page():
    vids_file = STATIC_DIR / "vids.html"
    if not vids_file.exists():
        return JSONResponse({"message": "Google Vids Studio static/vids.html is not created yet."})
    return FileResponse(str(vids_file))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse({"message": "Video Farm Studio Web API is running, but static/index.html is not created yet."})
    return FileResponse(str(index_file))

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
