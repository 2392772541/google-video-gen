from __future__ import annotations
import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from .models import Task, Profile

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

    def execute_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """
        Executes gflow-cli video i2v for a given task and profile.
        Returns execution result dictionary.
        """
        worker_name = threading.current_thread().name
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
                            "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY id DESC LIMIT 1",
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
            "--duration", str(task.duration_sec),
            "--out-dir", str(self.output_dir),
            "--json",
        ]
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
