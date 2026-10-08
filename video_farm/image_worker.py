"""Task-owned browser subprocesses. No profile-wide kills, hidden fallback or retries."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .image_modes import validate_image_settings, validate_image_file, validate_image_result
from .execution_control import terminate_owned_process

_IMAGE_BROWSER_SLOT = threading.BoundedSemaphore(1)
RESULT_PREFIX = "IMAGE_RESULT="


class BrowserImageWorker:
    def __init__(self, output_dir, timeout_sec=360, python_bin=None, headless=True):
        self.output_dir = Path(output_dir).resolve()
        self.root = Path(__file__).resolve().parents[1]
        venv = self.root / "gflow-cli" / ".venv" / "Scripts" / "python.exe"
        self.python_bin = str(python_bin or (venv if venv.is_file() else sys.executable))
        self.timeout_sec = timeout_sec
        self.headless = headless
        self._sessions = {}
        self._lock = threading.Lock()

    def prepare_task(self, task_id, cancel_event):
        with self._lock:
            self._sessions[task_id] = {"event": cancel_event, "proc": None}

    @staticmethod
    def _terminate(proc):
        return terminate_owned_process(proc)

    def has_live_execution(self, task_id):
        with self._lock:
            session = self._sessions.get(task_id)
            if not session:
                return False
            proc = session.get("proc")
            if proc is not None and proc.poll() is None:
                return True
            self._sessions.pop(task_id, None)
            if session.get("slot_owned"):
                _IMAGE_BROWSER_SLOT.release()
        return False

    def cancel_task(self, task_id):
        # Only signal here; the worker thread owns termination and wait().
        with self._lock:
            session = self._sessions.get(task_id)
            if not session:
                return False
            session["event"].set()
        return True

    def execute_image_task(self, task, profile):
        logs, proc, acquired, launched = "", None, False, False
        directory = None
        outcome = {}
        deadline = time.monotonic() + self.timeout_sec
        stage = "input"

        def failure(code, message):
            outcome.update(success=False, error_code=code, error_message=message,
                           logs=logs[-12000:], pid=proc.pid if proc else None,
                           submission_possible=launched)
            return outcome

        try:
            engine, model, aspect = validate_image_settings(task.engine, task.model, task.aspect_ratio)
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task.id):
                raise ValueError("非法图片任务 ID")
            if task.start_image_path:
                validate_image_file(task.start_image_path)
            with self._lock:
                session = self._sessions.setdefault(task.id, {"event": threading.Event(), "proc": None})
                cancel_event = session["event"]
            while not _IMAGE_BROWSER_SLOT.acquire(timeout=0.25):
                if cancel_event.is_set():
                    return failure("USER_CANCELLED", "图片任务已停止；尚未提交")
                if time.monotonic() >= deadline:
                    return failure("LOCAL_IMAGE_BUSY", "本机生图通道繁忙，等待已超时；尚未提交网页生成，可安全重新排队。")
            acquired = True
            with self._lock:
                session["slot_owned"] = True
            if cancel_event.is_set():
                return failure("USER_CANCELLED", "图片任务已停止；尚未提交")
            stage = "execution"
            directory = self.output_dir / task.id / ("attempt_" + uuid.uuid4().hex)
            directory.mkdir(parents=True, exist_ok=False)
            profile_dir = Path(profile.profile_path) if profile.profile_path else (
                Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
                / "ffroliva" / "gflow-cli" / f"profile_{profile.name}")
            spec = {"engine": engine, "model": model, "aspect_ratio": aspect, "prompt": task.prompt,
                    "reference": task.start_image_path or "", "profile_dir": str(profile_dir.resolve()),
                    "project_id": task.project_id or "", "profile_name": profile.name, "output_dir": str(directory),
                    "timeout_sec": max(1, deadline - time.monotonic() - 5), "headless": self.headless}
            spec_path = directory / "image_request.json"
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            env["PYTHONPATH"] = str(self.root) + os.pathsep + str(self.root / "gflow-cli" / "src") + os.pathsep + env.get("PYTHONPATH", "")
            with self._lock:
                if cancel_event.is_set():
                    return failure("USER_CANCELLED", "图片任务已停止；尚未提交")
                proc = subprocess.Popen([self.python_bin, "-m", "video_farm.image_web_runner", str(spec_path)],
                    cwd=str(self.root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                launched = True
                session["proc"] = proc
            while True:
                if cancel_event.is_set():
                    return failure("USER_CANCELLED", "图片任务本地执行已停止；云端已提交的生成可能继续")
                if time.monotonic() >= deadline:
                    return failure("IMAGE_RESULT_UNCONFIRMED", "图片任务达到总时限。请检查原网页结果，避免重复消耗额度。")
                try:
                    logs, _ = proc.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    continue
            result_lines = [line[len(RESULT_PREFIX):] for line in logs.splitlines() if line.startswith(RESULT_PREFIX)]
            if not result_lines:
                return failure("IMAGE_RESULT_UNCONFIRMED", "图片执行器未返回可核验结果；请检查原网页，不自动重复生成。")
            result = json.loads(result_lines[-1])
            outcome.update(result, pid=proc.pid, attempt_dir=str(directory))
            outcome.setdefault("submission_possible", True)
            outcome["logs"] = result.get("logs", "") + "\n" + "\n".join(line for line in logs.splitlines() if not line.startswith(RESULT_PREFIX))[-12000:]
            if outcome.get("success"):
                stage = "output"
                validate_image_result(outcome, task, self.output_dir)
            return outcome
        except Exception as exc:
            return failure("INVALID_IMAGE_REQUEST" if stage == "input" else "IMAGE_OUTPUT_INVALID" if stage == "output" else "IMAGE_RESULT_UNCONFIRMED", str(exc))
        finally:
            cleaned = proc is None or proc.poll() is not None
            if not cleaned:
                cleaned = self._terminate(proc)
            outcome["cleanup_confirmed"] = bool(cleaned)
            if not cleaned:
                outcome.update(success=False, error_code="PROCESS_CLEANUP_FAILED",
                    error_message="图片执行进程未确认退出；账号与生图通道已隔离，请核对原网页，不重复提交。")
            else:
                with self._lock:
                    self._sessions.pop(task.id, None)
                    if acquired:
                        _IMAGE_BROWSER_SLOT.release()
