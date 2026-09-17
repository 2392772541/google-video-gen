from __future__ import annotations

import os
import sys
import json
import subprocess
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from .models import Task, Profile

def heal_profile_flow_ui(profile_name: str, project_id: Optional[str] = None) -> bool:
    """
    自动自愈 Google Flow 界面阻断状态：
    1. 确保写入 .gflow_browser_strategy 为 chrome
    2. 关闭可能遮挡底栏的会话侧边栏 (.header-action)
    3. 自动点击并消除 '您正在使用我们最新的视频模型...' 引导浮层 (button: '知道了' / 'Got it')
    4. 若智能体 (Agent mode) 被选中，自动点击解除选中状态，确保经典底栏 (.settings-trigger-button) 显示
    """
    try:
        from playwright.sync_api import sync_playwright
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        gflow_base = Path(appdata) / "ffroliva" / "gflow-cli"
        profile_dir = gflow_base / f"profile_{profile_name}"
        
        marker = profile_dir / ".gflow_browser_strategy"
        marker.write_text("chrome", encoding="utf-8")
        
        if not project_id:
            gflow_db = gflow_base / "gflow.db"
            if gflow_db.exists():
                with sqlite3.connect(str(gflow_db)) as conn:
                    row = conn.execute(
                        "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY rowid DESC LIMIT 1",
                        (profile_name,)
                    ).fetchone()
                    if row and row[0]:
                        project_id = row[0]
                        
        url = f"https://flow.google.com/project/{project_id}" if project_id else "https://flow.google.com/"
        
        with sync_playwright() as pw:
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)
                
                # 1. 消除前置协议遮罩
                for _ in range(3):
                    pane = page.query_selector(".cdk-overlay-pane")
                    if not pane:
                        break
                    next_btn = pane.query_selector("button:has-text('下一步'), button:has-text('Next')")
                    if next_btn and not next_btn.evaluate("el => el.disabled"):
                        next_btn.click()
                        page.wait_for_timeout(1500)
                        continue
                    page.evaluate("""() => {
                        const el = document.querySelector('.privacy-content') || document.querySelector('.cdk-overlay-pane div[style*="overflow"]');
                        if (el) { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); }
                    }""")
                    cont_btn = pane.query_selector("button:has-text('继续'), button:has-text('Continue'), button:has-text('完成'), button:has-text('开始')")
                    if cont_btn and not cont_btn.evaluate("el => el.disabled || el.getAttribute('disabled')"):
                        cont_btn.click()
                        page.wait_for_timeout(2000)
                        
                # 2. 关闭右侧会话栏
                close_btn = page.query_selector("button.header-action:has-text('close'), button[aria-label='关闭'], button[aria-label='Close']")
                if close_btn:
                    try:
                        close_btn.click()
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass
                        
                # 3. 消除引导气泡
                got_it = page.query_selector("button:has-text('知道了'), button:has-text('Got it')")
                if got_it:
                    try:
                        got_it.click()
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass
                        
                # 4. 关闭智能体模式
                chip = page.query_selector("button.agent-mode-chip[aria-pressed='true']")
                if chip:
                    try:
                        chip.click()
                        page.wait_for_timeout(1500)
                    except Exception:
                        pass
                        
                btn = page.query_selector(".settings-trigger-button")
                return btn.is_visible() if btn else False
            finally:
                browser.close()
    except Exception as exc:
        print(f"[heal_profile_flow_ui] 自动修复 profile [{profile_name}] 异常: {exc}")
        return False

class VideoWorker:
    def __init__(
        self,
        gflow_dir: Path = Path("gflow-cli"),
        output_dir: Path = Path("video_farm_data/outputs"),
        timeout_sec: int = 360,
        mock_sample_video: Optional[str] = None
    ):
        self.mock_sample_video = mock_sample_video
        self.gflow_dir = gflow_dir.resolve()
        self.python_bin = self.gflow_dir / ".venv" / "Scripts" / "python.exe"
        if not self.python_bin.exists():
            # Fallback to current python if virtualenv not found
            self.python_bin = Path(sys.executable)
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = timeout_sec

    def _ensure_profile_marker(self, profile_name: str):
        try:
            appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            profile_dir = Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile_name}"
            profile_dir.mkdir(parents=True, exist_ok=True)
            marker = profile_dir / ".gflow_browser_strategy"
            if not marker.exists() or marker.read_text(encoding="utf-8").strip() != "chrome":
                marker.write_text("chrome", encoding="utf-8")
        except Exception:
            pass

    def execute_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """
        Executes gflow-cli video i2v for a given task and profile.
        Returns execution result dictionary.
        """
        worker_name = threading.current_thread().name
        self._ensure_profile_marker(profile.name)
        if self.mock_sample_video:
            import time, shutil
            time.sleep(1.0)
            target = self.output_dir / f"{task.id}.mp4"
            shutil.copy2(self.mock_sample_video, target)
            return {
                "success": True,
                "pid": os.getpid(),
                "error_code": None,
                "error_message": None,
                "output_video_path": str(target.resolve()),
                "logs": f"Mock executed with sample: {self.mock_sample_video}"
            }

        start_img = Path(task.start_image_path).resolve()
        end_img = Path(task.end_image_path).resolve()

        if not start_img.exists():
            return {
                "success": False,
                "pid": None,
                "error_code": "START_IMAGE_NOT_FOUND",
                "error_message": f"Start image not found: {start_img}",
                "output_video_path": None,
                "logs": ""
            }
        if not end_img.exists():
            return {
                "success": False,
                "pid": None,
                "error_code": "END_IMAGE_NOT_FOUND",
                "error_message": f"End image not found: {end_img}",
                "output_video_path": None,
                "logs": ""
            }

        # 兼容 flow.google.com 迁移架构：若无 project_id，自动从 gflow 本地工程库探测已有工程，避免调用废弃的 labs createProject RPC
        project_id = getattr(task, "project_id", None) or ""
        if not project_id:
            try:
                appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                gflow_db = Path(appdata) / "ffroliva" / "gflow-cli" / "gflow.db"
                if gflow_db.exists():
                    import sqlite3
                    with sqlite3.connect(str(gflow_db)) as c_conn:
                        row = c_conn.execute(
                            "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY rowid DESC LIMIT 1",
                            (profile.name,)
                        ).fetchone()
                        if row and row[0]:
                            project_id = row[0]
            except Exception as e:
                print(f"[{worker_name}] 查找 profile [{profile.name}] 已有 project 异常: {e}")

        cmd = [
            str(self.python_bin),
            "-m", "gflow_cli",
            "video", "i2v",
            "--initial-frame", str(start_img),
            "--end-frame", str(end_img),
            "--aspect", task.aspect_ratio,
            "--profile", profile.name,
            "--out-dir", str(self.output_dir),
            "--json",
        ]
        if getattr(task, "model", None) and task.model:
            cmd.extend(["--model", task.model])
        # 注意：新版 flow.google.com 上 Veo 3.1 Lite 界面往往无 8s 选项，强加 --duration 会触发 Configuration error
        # 仅当任务非默认值且非 8 时才尝试传入；若为空或 8，则省略 --duration 遵循 Flow 默认时长 (官方建议)
        if task.duration_sec and task.duration_sec not in (0, 8):
            cmd.extend(["--duration", str(task.duration_sec)])
        if project_id:
            cmd.extend(["--project", str(project_id)])
        cmd.append(task.prompt)

        # Record pre-existing files in output_dir to identify newly created file if needed
        existing_files = set(self.output_dir.glob("*.mp4"))

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.gflow_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            pid = proc.pid
            print(f"[{worker_name}] 启动 gflow 进程 (PID={pid}) -> Profile=[{profile.name}] Task=[{task.id}]")

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": "TIMEOUT",
                    "error_message": f"Execution timed out after {self.timeout_sec}s (PID={pid} terminated)",
                    "output_video_path": None,
                    "logs": f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}"
                }

            logs = f"=== PID: {pid} ===\n=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}"

            if proc.returncode != 0:
                err_code = f"EXIT_{proc.returncode}"
                err_msg = f"Process exited with code {proc.returncode}\n{stderr[:400]}"
                if proc.returncode == 11 or any(k in stderr.lower() for k in ["profilelocked", "already in use", "is locked", "lockfile"]):
                    err_code = "PROFILE_LOCKED"
                    err_msg = f"Profile [{profile.name}] 被当前打开的 Chrome 窗口独占锁定。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 关闭占用 Chrome】后系统将自动恢复任务。"
                elif proc.returncode == 25 or any(k in stderr.lower() for k in ["flowagentuierror", "agentic ui", "settings-trigger-button"]):
                    err_code = "AGENTIC_UI_BLOCKED"
                    err_msg = f"Google Flow 处于智能体或遮罩状态。系统已执行自动去遮罩自愈，请重试。"
                    try:
                        heal_profile_flow_ui(profile.name, project_id)
                    except Exception:
                        pass
                elif "renders no duration control" in stderr.lower() or "configuration error" in stderr.lower():
                    err_code = "CONFIG_ERROR"
                    err_msg = f"Google Flow 界面未开放该时长选项，建议使用 Flow 默认时长生成。"
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": err_code,
                    "error_message": err_msg,
                    "output_video_path": None,
                    "logs": logs
                }

            # Try parsing JSON output from stdout
            output_video_path = None
            try:
                lines = stdout.strip().splitlines()
                for line in reversed(lines):
                    line_str = line.strip()
                    if line_str.startswith("{") and line_str.endswith("}"):
                        data = json.loads(line_str)
                        if "local_path" in data and data["local_path"]:
                            output_video_path = data["local_path"]
                            break
                        elif "path" in data:
                            output_video_path = data["path"]
                            break
                        elif "saved_path" in data:
                            output_video_path = data["saved_path"]
                            break
                        elif "output" in data:
                            output_video_path = data["output"]
                            break
            except Exception:
                pass

            if not output_video_path or not Path(output_video_path).exists():
                # Detect newest .mp4 in output_dir
                new_files = set(self.output_dir.glob("*.mp4")) - existing_files
                if new_files:
                    latest = max(new_files, key=lambda p: p.stat().st_mtime)
                    output_video_path = str(latest)

            if output_video_path and Path(output_video_path).exists():
                return {
                    "success": True,
                    "pid": pid,
                    "error_code": None,
                    "error_message": None,
                    "output_video_path": str(Path(output_video_path).resolve()),
                    "logs": logs
                }
            else:
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": "OUTPUT_NOT_FOUND",
                    "error_message": "Command succeeded but no output mp4 found",
                    "output_video_path": None,
                    "logs": logs
                }

        except Exception as exc:
            return {
                "success": False,
                "pid": None,
                "error_code": "EXCEPTION",
                "error_message": str(exc),
                "output_video_path": None,
                "logs": str(exc)
            }
    def execute_image_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """
        Executes gflow-cli image t2i (文生图) or i2i (图生图) for a given task and profile.
        Returns execution result dictionary with output_image_paths list.
        """
        worker_name = threading.current_thread().name
        self._ensure_profile_marker(profile.name)
        is_i2i = bool(task.start_image_path and Path(task.start_image_path).exists())
        subcmd = "i2i" if is_i2i else "t2i"

        # 探测已存在的 project_id 避免废弃接口
        project_id = getattr(task, "project_id", None) or ""
        if not project_id:
            try:
                appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                gflow_db = Path(appdata) / "ffroliva" / "gflow-cli" / "gflow.db"
                if gflow_db.exists():
                    import sqlite3
                    with sqlite3.connect(str(gflow_db)) as c_conn:
                        row = c_conn.execute(
                            "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY rowid DESC LIMIT 1",
                            (profile.name,)
                        ).fetchone()
                        if row and row[0]:
                            project_id = row[0]
            except Exception as e:
                print(f"[{worker_name}] 查找 profile [{profile.name}] 已有 project 异常: {e}")

        cmd = [
            str(self.python_bin),
            "-m", "gflow_cli",
            "image", subcmd,
            "--aspect", task.aspect_ratio or "9:16",
            "--profile", profile.name,
            "--out", str(self.output_dir),
            "--json",
        ]
        if is_i2i:
            cmd.extend(["--ref", str(Path(task.start_image_path).resolve())])
        if getattr(task, "model", None) and task.model:
            cmd.extend(["--model", task.model])
        if project_id:
            cmd.extend(["--project", str(project_id)])
        cmd.append(task.prompt)

        existing_imgs = set(self.output_dir.glob("*.png")) | set(self.output_dir.glob("*.jpg")) | set(self.output_dir.glob("*.jpeg")) | set(self.output_dir.glob("*.webp"))

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.gflow_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            pid = proc.pid
            mode_desc = f"图生图 (i2i, 垫图={Path(task.start_image_path).name})" if is_i2i else "文生图 (t2i)"
            print(f"[{worker_name}] 启动 gflow 图像进程 (PID={pid}) -> {mode_desc} Profile=[{profile.name}] Task=[{task.id}]")

            try:
                stdout, stderr = proc.communicate(timeout=self.timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": "TIMEOUT",
                    "error_message": f"图像生成超时（超过 {self.timeout_sec}s，PID={pid} 已终止）",
                    "output_image_paths": [],
                    "logs": f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}"
                }

            logs = f"=== PID: {pid} ===\n=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}"

            if proc.returncode != 0:
                err_code = f"EXIT_{proc.returncode}"
                err_msg = f"进程退出码 {proc.returncode}\n{stderr[:400]}"
                if proc.returncode == 36 or "FlowHostMigratedError" in stdout or "not ported yet" in stdout or "not ported yet" in stderr:
                    err_code = "UNSUPPORTED_FEATURE"
                    err_msg = "Google Flow (flow.google.com) 当前仅支持 Nano Banana Pro (nano-pro) 与 Nano Banana 2 (nano2) 生图模型；Imagen 3.5 官方尚未适配，请切换模型为 Nano Banana Pro。"
                elif proc.returncode == 25 or any(k in stderr.lower() for k in ["flowagentuierror", "agentic ui", "settings-trigger-button"]):
                    err_code = "AGENTIC_UI_BLOCKED"
                    err_msg = f"Google Flow 处于智能体或遮罩状态。系统已执行自动去遮罩自愈，请重试。"
                    try:
                        heal_profile_flow_ui(profile.name, project_id)
                    except Exception:
                        pass
                elif proc.returncode == 11 or any(k in stderr.lower() for k in ["profilelocked", "already in use", "is locked", "lockfile"]):
                    err_code = "PROFILE_LOCKED"
                    err_msg = f"Profile [{profile.name}] 被当前打开的 Chrome 窗口独占锁定。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 关闭占用 Chrome】后系统将自动恢复任务。"
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": err_code,
                    "error_message": err_msg,
                    "output_image_paths": [],
                    "logs": logs
                }

            # 尝试从 stdout 解析输出图片路径列表
            found_paths = []
            try:
                lines = stdout.strip().splitlines()
                for line in reversed(lines):
                    line_str = line.strip()
                    if line_str.startswith("{") and line_str.endswith("}"):
                        data = json.loads(line_str)
                        if "images" in data and isinstance(data["images"], list):
                            for img in data["images"]:
                                if isinstance(img, dict) and "local_path" in img and img["local_path"]:
                                    lp = Path(img["local_path"]).resolve()
                                    if lp.exists():
                                        found_paths.append(str(lp))
                            if found_paths:
                                break
                        elif "saved_paths" in data and isinstance(data["saved_paths"], list):
                            found_paths = [str(Path(p).resolve()) for p in data["saved_paths"] if Path(p).exists()]
                            if found_paths:
                                break
                        elif "paths" in data and isinstance(data["paths"], list):
                            found_paths = [str(Path(p).resolve()) for p in data["paths"] if Path(p).exists()]
                            if found_paths:
                                break
                        elif "local_path" in data and data["local_path"] and Path(data["local_path"]).exists():
                            found_paths = [str(Path(data["local_path"]).resolve())]
                            break
            except Exception:
                pass

            if not found_paths:
                # 对比现有图像识别出新落盘的文件
                current_imgs = set(self.output_dir.glob("*.png")) | set(self.output_dir.glob("*.jpg")) | set(self.output_dir.glob("*.jpeg")) | set(self.output_dir.glob("*.webp"))
                new_files = sorted(list(current_imgs - existing_imgs), key=lambda p: p.stat().st_mtime, reverse=True)
                if new_files:
                    found_paths = [str(p.resolve()) for p in new_files]

            if found_paths:
                return {
                    "success": True,
                    "pid": pid,
                    "error_code": None,
                    "error_message": None,
                    "output_image_paths": found_paths,
                    "logs": logs
                }
            else:
                return {
                    "success": False,
                    "pid": pid,
                    "error_code": "OUTPUT_NOT_FOUND",
                    "error_message": "生图命令执行成功，但未在输出目录找到生成的图像文件",
                    "output_image_paths": [],
                    "logs": logs
                }

        except Exception as exc:
            return {
                "success": False,
                "pid": None,
                "error_code": "EXCEPTION",
                "error_message": str(exc),
                "output_image_paths": [],
                "logs": str(exc)
            }

