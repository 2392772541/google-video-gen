from __future__ import annotations

import os
import math
import sys
import json
import re
import subprocess
import uuid
import shutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from .models import Task, Profile
from .execution_control import ExecutionControl, ExecutionStopped
from .image_worker import BrowserImageWorker
from .owned_process import OwnedProcess
from .output_publication import publish_video
from .flow_errors import (
    FLOW_RESPONSE_UNREADABLE,
    FLOW_RESPONSE_UNREADABLE_MESSAGE,
    is_flow_response_unreadable,
)

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
        self._current_procs: Dict[str, OwnedProcess] = {}
        self._procs_lock = threading.Lock()
        self._cancel_events = {}
        self._image_worker = BrowserImageWorker(self.output_dir, timeout_sec, self.python_bin)

    def prepare_task(self, task_id: str, cancel_event: threading.Event) -> None:
        with self._procs_lock:
            self._cancel_events[task_id] = cancel_event

    def cancel_task(self, task_id: str) -> bool:
        image = self._image_worker.cancel_task(task_id)
        with self._procs_lock:
            event = self._cancel_events.get(task_id)
            if event is not None:
                event.set()
        return image or event is not None

    def has_live_execution(self, task_id: str) -> bool:
        """A root exit cannot release an account with living descendants."""
        with self._procs_lock:
            proc = self._current_procs.get(task_id)
        if proc is not None:
            try:
                if proc.is_alive() or not proc.cleanup():
                    return True
            except Exception:
                return True
            with self._procs_lock:
                if self._current_procs.get(task_id) is proc:
                    self._current_procs.pop(task_id, None)
                    self._cancel_events.pop(task_id, None)
        return self._image_worker.has_live_execution(task_id)

    @staticmethod
    def _terminate(proc):
        return proc.cleanup()

    def _launch_cli(self, command, *, stdout, stderr):
        # The service must not accumulate a hung CLI's full output in PIPEs.
        # Inherited file handles also avoid descendants keeping communicate open.
        return OwnedProcess(command, cwd=str(self.gflow_dir), stdout=stdout, stderr=stderr)

    @staticmethod
    def _read_log_tail(path, byte_limit=64 * 1024):
        if path is None:
            return ""
        try:
            with Path(path).open("rb") as stream:
                size = stream.seek(0, os.SEEK_END)
                stream.seek(max(0, size - byte_limit))
                content = stream.read(byte_limit).decode("utf-8", errors="replace")
            return ("[log truncated; full log retained in attempt directory]\n" if size > byte_limit else "") + content
        except OSError as exc:
            return "[log unavailable: " + str(exc) + "]"

    def _attempt_logs(self, proc, stdout_path, stderr_path):
        return (f"=== PID: {proc.pid if proc else '-'} ===\n=== STDOUT ===\n"
                + self._read_log_tail(stdout_path, byte_limit=12000)
                + "\n=== STDERR ===\n" + self._read_log_tail(stderr_path, byte_limit=12000))

    @staticmethod
    def _receipt(stdout):
        try:
            value = json.loads(stdout.strip())
            if isinstance(value, dict):
                return value
        except (ValueError, TypeError):
            pass
        for line in reversed(stdout.splitlines()):
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    return value
            except (ValueError, TypeError):
                continue
        return {}

    def _validate_output(self, path, task, control):
        probe = shutil.which("ffprobe")
        if not probe:
            raise ValueError("缺少 ffprobe，不能验证 Flow 成片")
        control.check()
        result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=min(15, control.remaining))
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        w, h = stream.get("width", 0), stream.get("height", 0)
        duration = 0.0
        for raw in (stream.get("duration"), data.get("format", {}).get("duration")):
            try:
                value = float(raw)
            except (ValueError, TypeError):
                continue
            if math.isfinite(value) and value > 0:
                duration = value
                break
        aspect = 16 / 9 if task.aspect_ratio == "16:9" else 9 / 16
        is_veo = any(k in (task.model or "").lower() for k in ("veo", "lite", "fast", "quality"))
        duration_match = (abs(duration - task.duration_sec) <= 0.6) or (is_veo and duration >= 3.0)
        if result.returncode or min(w, h) < 720 or abs(w / max(h, 1) - aspect) > 0.03 or not duration_match:
            raise ValueError(f"实际 Flow 成片 {w}×{h}/{duration:.2f}s 与请求 {task.aspect_ratio}/{task.duration_sec}s 不符")
        control.check()

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
        """One owned CLI attempt; ambiguous outcomes must never trigger a new spend."""
        with self._procs_lock:
            event = self._cancel_events.setdefault(task.id, threading.Event())
        control = ExecutionControl(event, self.timeout_sec)
        proc, logs, launched = None, "", False
        outcome = {}
        output_to_publish = None
        stdout_path = stderr_path = None
        spool_handles = []

        def failure(code, message, submission_possible=None):
            sub_pos = launched if submission_possible is None else submission_possible
            outcome.update(success=False, pid=proc.pid if proc else None,
                           error_code=code, error_message=message,
                           output_video_path=None, logs=logs,
                           submission_possible=sub_pos)
            return outcome

        try:
            control.check()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task.id):
                return failure("INVALID_VIDEO_REQUEST", "非法任务 ID")
            if self.mock_sample_video:
                target = self.output_dir / task.id / ("mock_" + uuid.uuid4().hex + ".mp4")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self.mock_sample_video, target)
                control.check()
                output_to_publish = target
                outcome.update(success=True, pid=os.getpid(), output_video_path=str(target), logs="Explicit mock sample", submission_possible=False)
                return outcome
            self._ensure_profile_marker(profile.name)
            ref_imgs = [Path(p.strip()).resolve() for p in (task.start_image_path or "").split(";") if p.strip()]
            end_img = Path(task.end_image_path).resolve() if task.end_image_path else None
            for idx, r_img in enumerate(ref_imgs):
                if not r_img.is_file():
                    return failure("START_IMAGE_NOT_FOUND", f"图片不存在：{r_img}")
            if end_img and not end_img.is_file():
                return failure("END_IMAGE_NOT_FOUND", f"图片不存在：{end_img}")
            if end_img and not ref_imgs:
                return failure("INVALID_VIDEO_REQUEST", "尾帧必须与首帧一起提供")
            
            project_id = task.project_id or ""
            if not project_id:
                from .onboard import get_profile_flow_project_id, ensure_profile_onboarded
                project_id = get_profile_flow_project_id(profile.name) or ensure_profile_onboarded(profile.name) or ""
            if not project_id:
                return failure("PROJECT_INIT_REQUIRED", "该账号没有已绑定的 Flow 工程；请手动绑定后再生成。未提交网页请求。")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(project_id)):
                return failure("INVALID_VIDEO_REQUEST", "Flow 工程 ID 不合法；未提交请求")
            directory = self.output_dir / task.id / ("attempt_" + uuid.uuid4().hex)
            directory.mkdir(parents=True, exist_ok=False)
            start_img = ref_imgs[0] if ref_imgs else ""
            end_img = task.end_image_path or ""
            is_r2v = len(ref_imgs) > 1 and not end_img

            if is_r2v:
                cmd = [str(self.python_bin), "-m", "gflow_cli", "video", "r2v"]
                for r_path in ref_imgs:
                    cmd.extend(["--ref", str(r_path)])
            elif start_img:
                cmd = [str(self.python_bin), "-m", "gflow_cli", "video", "i2v", "--initial-frame", str(start_img)]
                if end_img:
                    cmd.extend(["--end-frame", str(end_img)])
            else:
                cmd = [str(self.python_bin), "-m", "gflow_cli", "video", "t2v"]
            cmd.extend(["--aspect", task.aspect_ratio or "16:9", "--profile", profile.name,
                        "--out-dir", str(directory), "--json", "--project", str(project_id)])
            flow_model = None
            if task.model:
                raw_m = str(task.model).strip().lower()
                if "quality" in raw_m:
                    flow_model = "veo-quality"
                elif "fast" in raw_m:
                    flow_model = "veo-fast"
                elif "lp" in raw_m:
                    flow_model = "veo-lite-lp"
                elif "lite" in raw_m:
                    flow_model = "veo-lite"
                elif "omni" in raw_m or "flash" in raw_m:
                    flow_model = "omni-flash"
                elif raw_m in ("omni-flash", "veo-lite", "veo-fast", "veo-quality", "veo-lite-lp"):
                    flow_model = raw_m
            if not flow_model:
                flow_model = "omni-flash"
            if int(task.duration_sec) == 10:
                flow_model = "omni-flash"
            cmd.extend(["--model", flow_model])
            # Flow 时长适配：Veo Lite/Fast/Quality 支持 4s/6s/8s；Omni Flash 支持 4s/6s/8s/10s
            # 正常向 CLI 传递用户请求的有效时长参数
            if task.duration_sec and int(task.duration_sec) in (4, 6, 8, 10):
                cmd.extend(["--duration", str(int(task.duration_sec))])
            # 生成条数参数支持 (1~4)
            count_val = getattr(task, "count", 1) or 1
            if count_val in (1, 2, 3, 4):
                cmd.extend(["--count", str(count_val)])
            cmd.append(task.prompt)
            control.check()
            stdout_path, stderr_path = directory / "stdout.log", directory / "stderr.log"
            stdout_file = stdout_path.open("wb")
            spool_handles.append(stdout_file)
            stderr_file = stderr_path.open("wb")
            spool_handles.append(stderr_file)
            proc = self._launch_cli(cmd, stdout=stdout_file, stderr=stderr_file)
            launched = True
            with self._procs_lock:
                self._current_procs[task.id] = proc
            if event.is_set():
                return failure("USER_CANCELLED", "本地任务已停止；云端已提交的生成可能继续")
            while True:
                control.check()
                try:
                    proc.wait(timeout=min(0.2, control.remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            for stream in spool_handles:
                stream.flush()
            stdout, stderr = self._read_log_tail(stdout_path), self._read_log_tail(stderr_path)
            logs = self._attempt_logs(proc, stdout_path, stderr_path)
            control.check()
            receipt = self._receipt(stdout)
            if proc.returncode == 0 and receipt.get("status") == "ok" and receipt.get("succeeded") is True:
                try:
                    output = Path(receipt.get("local_path") or "").resolve()
                    if not output.is_relative_to(directory.resolve()) or not output.is_file():
                        raise ValueError("Flow 返回的视频不属于本次执行目录；拒绝拿其他任务产物回显")
                    self._validate_output(output, task, control)
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    return failure("VIDEO_OUTPUT_INVALID", str(exc))
                output_to_publish = output
                outcome.update(success=True, pid=proc.pid, output_video_path=str(output),
                               error_code=None, error_message=None, logs=logs, submission_possible=True)
                return outcome
            raw_code = f"EXIT_{proc.returncode}"
            if is_flow_response_unreadable(raw_code, "", logs):
                return failure(FLOW_RESPONSE_UNREADABLE, FLOW_RESPONSE_UNREADABLE_MESSAGE)
            content = (stdout + "\n" + stderr).lower()
            error_class = (receipt.get("error") or {}).get("class", "")
            if error_class == "ProfileLockedError" or any(k in content for k in ("profilelocked", "already in use", "singletonlock", "is locked")):
                return failure("PROFILE_LOCKED", "Flow 账号目录已被其他窗口占用；未获得浏览器执行权")
            if proc.returncode == 11 or (proc.returncode == 23 and ("duration_tab" in content or "duration" in content)):
                return failure(
                    "DURATION_CONTROL_ABSENT",
                    "当前 Google Flow 账号页面未渲染时长选择滑块（上游灰度策略导致），不支持指定精确秒数。建议在视频设置中勾选【使用平台默认时长 (~6s/8s)】或切换账号重试。",
                    submission_possible=False
                )
            if proc.returncode == 25:
                return failure("AGENTIC_UI_BLOCKED", "Flow 被协议或界面遮挡；系统未同意协议、未再次提交")
            if proc.returncode == 7 and ("wireformaterror" in content or "wire-format" in content):
                return failure("WIRE_FORMAT_MISMATCH", "Flow 格式校验失败；请核对原工程，不自动重复提交")
            if proc.returncode in (1, 2) and any(kw in content for kw in ("caps at", "usage:", "only available for", "invalid value", "error: the default model")):
                err_lines = [line.strip() for line in (stderr + "\n" + stdout).splitlines() if line.strip().startswith("Error:") or "caps at" in line or "only available for" in line]
                err_detail = err_lines[0] if err_lines else "参数与当前模型不兼容"
                return failure("CONFIG_ERROR", f"Flow CLI 参数校验失败（未提交请求，未扣除额度）：{err_detail}", submission_possible=False)
            # Authentication/transport failures can occur after an accepted submit.
            # Without a pre-submit receipt, no account failover/retry is safe.
            return failure("FLOW_RESULT_UNCONFIRMED", "Flow 未返回可验证成片；请先核对原工程，可能已经消耗额度，不会自动重发")
        except ExecutionStopped as exc:
            code = exc.code if exc.code == "USER_CANCELLED" or not launched else "FLOW_RESULT_UNCONFIRMED"
            return failure(code, str(exc) + (" 请核对原工程；不会重复提交。" if launched else " 尚未启动生成。"))
        except Exception as exc:
            return failure("FLOW_RESULT_UNCONFIRMED" if launched else "INVALID_VIDEO_REQUEST", str(exc))
        finally:
            try:
                cleaned = proc is None or self._terminate(proc)
            except Exception:
                cleaned = False
            # Close our handles even when ownership must be retained: the child
            # owns separate inherited handles and can still be cleaned up later.
            for stream in spool_handles:
                try:
                    stream.close()
                except OSError:
                    pass
            if stdout_path is not None:
                logs = self._attempt_logs(proc, stdout_path, stderr_path)
                outcome["logs"] = logs
            outcome["cleanup_confirmed"] = bool(cleaned)
            if not cleaned:
                failure("PROCESS_CLEANUP_FAILED",
                        "本地执行进程树未确认退出；账号已隔离，其他账号可继续。请核对原工程结果，不要重复提交。")
            else:
                try:
                    if outcome.get("success") and output_to_publish:
                        outcome["output_video_path"] = publish_video(output_to_publish, self.output_dir, task.id, control)
                except ExecutionStopped as exc:
                    failure("USER_CANCELLED" if exc.code == "USER_CANCELLED" else "FLOW_RESULT_UNCONFIRMED",
                            str(exc) + " 成片保留在独占目录，未发布成功，不会重发。")
                except Exception as exc:
                    failure("VIDEO_OUTPUT_INVALID", "成片发布失败，未标记成功：" + str(exc))
                finally:
                    with self._procs_lock:
                        self._current_procs.pop(task.id, None)
                        if self._cancel_events.get(task.id) is event:
                            self._cancel_events.pop(task.id, None)

    def prepare_image_task(self, task_id: str, cancel_event: threading.Event) -> None:
        self._image_worker.prepare_task(task_id, cancel_event)

    def execute_image_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        return self._image_worker.execute_image_task(task, profile)
