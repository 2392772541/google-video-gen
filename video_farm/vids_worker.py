"""Google Vids native adapter: explicit capabilities and current-result ownership.

No Flow fallback, automatic agreement acceptance, profile unlock, or speculative
success based on network traffic / an old Insert button.
"""
from __future__ import annotations
import base64
import sys
import uuid
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit

from .execution_control import ExecutionControl, ExecutionStopped
from .models import Task, Profile
from .owned_process import OwnedProcess
from .output_publication import publish_video
from .video_contract import validate_video_request, VideoRequestError


class VidsUIError(RuntimeError):
    def __init__(self, message, code="VIDS_UI_ERROR"):
        super().__init__(message)
        self.code = code


class VidsWorker:
    def __init__(self, output_dir=Path("video_farm_data/outputs"), timeout_sec=360,
                 headless=True, mock_sample_video: Optional[str] = None,
                 python_bin=None, submission_state_path=None):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec, self.headless = timeout_sec, headless
        self.mock_sample_video = mock_sample_video
        self.python_bin = str(python_bin or sys.executable)
        self.submission_state_path = Path(submission_state_path) if submission_state_path else None
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._sessions_lock = threading.Lock()

    def prepare_task(self, task_id, cancel_event):
        with self._sessions_lock:
            self._active_sessions.setdefault(task_id, {}).update(
                cancel_event=cancel_event, cancelled=cancel_event.is_set())

    def begin_task(self, task_id):
        with self._sessions_lock:
            session = self._active_sessions.setdefault(task_id, {})
            event = session.setdefault("cancel_event", threading.Event())
            if session.get("cancelled"):
                event.set()
            control = ExecutionControl(event, self.timeout_sec)
            session["control"] = control
            return control

    def cancel_task(self, task_id):
        with self._sessions_lock:
            session = self._active_sessions.get(task_id)
            if session is None:
                return False
            session["cancelled"] = True
            session.setdefault("cancel_event", threading.Event()).set()
            return True

    def _mark_submission(self, task_id):
        # Durable marker BEFORE the click. A killed/lost click cannot be retried.
        if self.submission_state_path:
            temp = self.submission_state_path.with_suffix(".tmp")
            temp.write_text(json.dumps({"task_id": task_id, "submission_possible": True}), encoding="utf8")
            temp.replace(self.submission_state_path)
        with self._sessions_lock:
            self._active_sessions.get(task_id, {})["submitted"] = True

    def has_live_execution(self, task_id):
        # Never wait for process cleanup while holding the shared session lock:
        # another account's cancellation must not queue behind this tree.
        with self._sessions_lock:
            session = self._active_sessions.get(task_id)
            if not session:
                return False
            proc = session.get("proc")
        if proc is None or proc.is_alive():
            return True
        if not proc.cleanup():
            return True
        with self._sessions_lock:
            if self._active_sessions.get(task_id) is session:
                self._active_sessions.pop(task_id, None)
        return False

    def _publish_output(self, source, task, control):
        return publish_video(source, self.output_dir, task.id, control)

    provider_label = "Vids"
    mock_env_var = "VIDS_MOCK_MODE"
    unconfirmed_code = "VIDS_RESULT_UNCONFIRMED"

    def _validate_request(self, task):
        validate_video_request(task)
        if task.engine != "vids":
            raise VideoRequestError("VidsWorker 只接受显式 Google Vids 请求")
        if task.project_id and not str(task.project_id).startswith("https://docs.google.com/videos/"):
            # task.project_id is an external canvas affinity ID; clear it for Vids worker so navigation creates a new doc
            task.project_id = ""

    def _runner_command(self, request_path):
        return [self.python_bin, "-m", "video_farm.vids_web_runner", str(request_path)]

    def _launch_runner(self, request_path, log_file):
        root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
        return OwnedProcess(self._runner_command(request_path), cwd=str(root), env=env,
                            stdout=log_file, stderr=subprocess.STDOUT)

    def execute_task(self, task: Task, profile: Profile):
        """Bounded parent supervisor; no synchronous browser code in the server."""
        control = self.begin_task(task.id)
        outcome, proc, attempt = {}, None, None
        result_received = False
        stopped = None
        log_file = None
        output_to_publish = None
        def failure(code, message):
            outcome.update(success=False, error_code=code, error_message=message,
                           output_video_path=None)
            return outcome
        try:
            control.check()
            self._validate_request(task)
            if self.mock_sample_video and os.environ.get(self.mock_env_var) == "1":
                outcome.update(self._execute_browser_task(task, profile))
                result_received = True
                return outcome
            attempt = self.output_dir / task.id / ("attempt_" + uuid.uuid4().hex)
            attempt.mkdir(parents=True, exist_ok=False)
            fields = ("id", "prompt", "engine", "task_type", "model", "project_id",
                      "start_image_path", "end_image_path", "input_video_path", "aspect_ratio", "duration_sec")
            spec = {"task": {key: getattr(task, key) for key in fields},
                    "profile": {"id": profile.id, "name": profile.name, "profile_path": str(self._resolve_profile_dir(profile))},
                    "output_dir": str(attempt), "timeout_sec": max(0.1, control.remaining - 3),
                    "headless": self.headless, "submission_state_path": str(attempt / "submission.json")}
            request_path = attempt / "request.json"
            request_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf8")
            log_file = (attempt / "runner.log").open("wb")
            with self._sessions_lock:
                control.check()
                proc = self._launch_runner(request_path, log_file)
                self._active_sessions[task.id]["proc"] = proc
            while True:
                control.check()
                try:
                    exit_code = proc.wait(timeout=min(0.2, control.remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            control.check()
            if exit_code != 0:
                return failure(self.unconfirmed_code, f"{self.provider_label} 执行器异常退出（{exit_code}）；不接受成功标志，请核对原项目，系统不会重发。")
            result_path = attempt / "result.json"
            if not result_path.is_file() or result_path.stat().st_size > 1024 * 1024:
                return failure(self.unconfirmed_code, f"{self.provider_label} 执行器未返回可核验结果；请核对原项目，系统不会自动重发。")
            result = json.loads(result_path.read_text(encoding="utf8"))
            if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                raise ValueError(f"Invalid {self.provider_label} runner response")
            outcome.update(result)
            result_received = True
            if outcome["success"]:
                expected = (attempt / f"{task.id}.mp4").resolve()
                if Path(outcome.get("output_video_path") or "").resolve() != expected or not expected.is_file():
                    return failure("VIDEO_OUTPUT_INVALID", "成片不是本次任务独占目录的结果，未标记成功。")
                self._validate_output(expected, task, control, [])
                output_to_publish = expected
            return outcome
        except VideoRequestError as exc:
            return failure("INVALID_VIDEO_REQUEST", str(exc))
        except ExecutionStopped as exc:
            stopped = exc
            code = "USER_CANCELLED" if exc.code == "USER_CANCELLED" else self.unconfirmed_code
            return failure(code, str(exc) + " 浏览器执行将被定向终止；已提交的云端生成可能继续，请先核对原项目。")
        except Exception as exc:
            code = "VIDEO_OUTPUT_INVALID" if result_received and outcome.get("success") else self.unconfirmed_code if proc else "CONFIG_ERROR"
            message = re.sub(r"https?://\S+", "[URL省略]", str(exc).split("Call log:", 1)[0])
            return failure(code, message)
        finally:
            try:
                cleaned = proc is None or proc.cleanup()
            except Exception:
                cleaned = False  # Unknown tree state must keep the owner isolated.
            outcome["cleanup_confirmed"] = bool(cleaned)
            outcome["pid"] = proc.pid if proc else None
            if not result_received:
                outcome["submission_possible"] = bool(proc)
            # Check the durable click receipt only AFTER the entire child tree
            # is reaped. A live child may still publish the receipt during stop.
            marker_absent = proc is None
            if attempt:
                outcome["attempt_dir"] = str(attempt)
                try:
                    (attempt / "submission.json").stat()
                except FileNotFoundError:
                    marker_absent = True
                except OSError:
                    marker_absent = False  # Unreadable is not proof of absence.
                    outcome["submission_possible"] = True
                else:
                    marker_absent = False
                    outcome["submission_possible"] = True
            if stopped is not None and cleaned and not result_received and marker_absent:
                # Only an explicit, fully reaped stop can prove no click. Crash,
                # nonzero exit and malformed/missing replies still fail closed.
                outcome["submission_possible"] = False
                code = "USER_CANCELLED" if stopped.code == "USER_CANCELLED" else "PRE_SUBMIT_TIMEOUT"
                failure(code, "本地执行已停止；确认未提交云端生成，可修改参数后手动重试。" if code == "USER_CANCELLED"
                        else "提交前执行超时；确认未提交云端生成，不自动重试，可检查登录和网页后手动重试。")
            if attempt:
                if log_file:
                    try:
                        log_file.close()
                    except OSError:
                        pass
                try:
                    with (attempt / "runner.log").open("rb") as f:
                        f.seek(max(0, f.seek(0, 2) - 12000))
                        tail = f.read().decode("utf8", "replace")
                    tail = re.sub(r"https?://\S+", "[URL省略]", tail)
                    outcome["logs"] = (str(outcome.get("logs") or "") + "\n" + tail)[-24000:]
                except OSError:
                    pass
            if not cleaned:
                failure("PROCESS_CLEANUP_FAILED", f"{self.provider_label} 执行进程树未确认退出；账号已隔离，其他空闲账号可继续工作。")
            else:
                try:
                    if outcome.get("success") and output_to_publish:
                        outcome["output_video_path"] = self._publish_output(output_to_publish, task, control)
                except ExecutionStopped as exc:
                    code = "USER_CANCELLED" if exc.code == "USER_CANCELLED" else self.unconfirmed_code
                    failure(code, str(exc) + " 本次成片保留在独占目录，未发布成功；不会自动重发。")
                except Exception as exc:
                    failure("VIDEO_OUTPUT_INVALID", "成片发布失败，未标记成功：" + str(exc))
                finally:
                    with self._sessions_lock:
                        self._active_sessions.pop(task.id, None)

    def _resolve_profile_dir(self, profile):
        if profile.profile_path:
            return Path(profile.profile_path).resolve()
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
        return Path(root) / "ffroliva/gflow-cli" / f"profile_{profile.name}"

    @staticmethod
    def media_identity(url):
        """Strip expiring credentials, but retain the content identifier."""
        if not url:
            return ""
        if url.startswith("blob:"):
            return url
        parts = urlsplit(url)
        values = dict(parse_qsl(parts.query))
        if "id" in values:
            return f"{parts.path}?id={values['id']}"
        if parts.path == "/download" and "c" in values:
            return f"{parts.hostname}{parts.path}?c={values['c']}"
        volatile = {"expire", "expires", "sig", "signature", "token", "authuser", "opi"}
        query = sorted((k, v) for k, v in parse_qsl(parts.query)
                       if k.lower() not in volatile and not k.lower().startswith("x-goog-"))
        return f"{parts.hostname}{parts.path}?{urlencode(query)}"

    @staticmethod
    def _trusted_media(url):
        if url.startswith("blob:"):
            return True
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and (
            host == "drive.google.com" or host.endswith(".drive.google.com") or
            host.endswith(".usercontent.google.com") or host.endswith(".googleusercontent.com"))

    @classmethod
    def pick_current_media(cls, rows, baseline, prompt=None):
        for row in rows:
            url = row.get("src") or ""
            if not row.get("sidebar") or not row.get("ready") or not cls._trusted_media(url):
                continue
            if cls.media_identity(url) in baseline:
                continue
            if prompt and (row.get("label") or "").strip():
                p_clean = prompt.strip()
                label = (row.get("label") or "").strip()
                # 兼容 Google Vids aria-label 对超长提示词的前缀截断与省略号
                prefix = p_clean[:25].strip()
                if p_clean not in label and prefix not in label and label not in p_clean:
                    continue
            return url
        return None

    @staticmethod
    def _media_rows(page):
        return page.evaluate("""() => Array.from(document.querySelectorAll('video')).map(v => ({
            src: v.currentSrc || v.src,
            sidebar: !!v.closest('[role="complementary"][class*="Videogensidebar"]'),
            ready: v.readyState >= 2 && v.videoWidth > 0,
            label: v.getAttribute('aria-label') || '',
            width: v.videoWidth, height: v.videoHeight, duration: v.duration
        }))""")

    @staticmethod
    def _wait(page, control, predicate, message, seconds=12):
        until = time.monotonic() + seconds
        while True:
            control.check()
            result = predicate()
            if result:
                return result
            if time.monotonic() >= until:
                raise VidsUIError(message)
            control.pause(page, 0.2)

    @staticmethod
    def _visible(locator):
        return locator.count() > 0 and locator.first.is_visible()

    def _dismiss_overlays(self, page, logs, control):
        # Only known, non-binding welcome controls. Never remove dialog DOM or
        # click Agree/Accept/同意 on the user's behalf.
        dismiss_patterns = [
            re.compile(r"^(Close|关闭|Skip|跳过|Got it|知道了|Dismiss|Not now|稍后再说)$", re.I),
            re.compile(r"^(Blank vid|空白视频)$", re.I),
        ]
        dialogs = page.locator('[role="dialog"], .modal, [aria-modal="true"]')
        count = dialogs.count()
        for d_idx in range(count):
            dlg = dialogs.nth(d_idx)
            if not self._visible(dlg):
                continue
            for pat in dismiss_patterns:
                btns = dlg.get_by_role("button", name=pat)
                for b_idx in range(btns.count()):
                    b = btns.nth(b_idx)
                    if self._visible(b):
                        control.check()
                        b.click(timeout=control.timeout_ms())
                        logs.append("关闭非协议的新手引导")
                        control.pause(page, 0.5)
                        break
            close_icon = dlg.locator('button[aria-label*="Close" i], button[aria-label*="关闭" i], [aria-label="Close" i], [aria-label="关闭" i]')
            for b_idx in range(close_icon.count()):
                b = close_icon.nth(b_idx)
                if self._visible(b):
                    control.check()
                    b.click(timeout=control.timeout_ms())
                    logs.append("关闭非协议的新手引导")
                    control.pause(page, 0.5)
                    break
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        agreement = page.locator('[role="dialog"]').get_by_role(
            "button", name=re.compile(r"^(I agree|Agree|Accept|同意)$", re.I))
        if self._visible(agreement):
            raise VidsUIError("Google 要求您在原生网页确认协议；请求尚未提交。", "USER_ACTION_REQUIRED")

    def _configure(self, page, sidebar, task, control, logs):
        button = sidebar.get_by_role("button", name=re.compile(r"^(生成设置|Generation settings)", re.I))
        self._wait(page, control, lambda: self._visible(button), "未找到 Vids 原生生成设置")
        button.first.click(timeout=control.timeout_ms())
        resolution = "1080p" if "1080" in (task.model or "") else "720p"
        option = page.get_by_role("menuitemradio", name=resolution, exact=True)
        if not self._visible(option):
            dropdown = page.get_by_role("button", name=re.compile(r"^(720p|1080p)$"))
            self._wait(page, control, lambda: self._visible(dropdown), "画质下拉框不可用")
            dropdown.first.click(timeout=control.timeout_ms())
            self._wait(page, control, lambda: self._visible(option), f"原生网页没有 {resolution} 选项")
        option.first.click(timeout=control.timeout_ms())
        landscape = task.aspect_ratio == "16:9"
        radio = page.get_by_role("radio", name=re.compile(r"^(横屏|Landscape)$" if landscape else r"^(竖屏|Portrait)$", re.I))
        self._wait(page, control, lambda: self._visible(radio), "画幅控件不可用")
        radio.first.check(timeout=control.timeout_ms())
        slider = page.get_by_role("slider", name=re.compile(r"视频时长|Video duration", re.I))
        self._wait(page, control, lambda: self._visible(slider), "时长控件不可用")
        bounds = slider.first.evaluate("e => ({min:Number(e.min),max:Number(e.max),step:Number(e.step||1)})")
        if bounds != {"min": 3, "max": 10, "step": 1}:
            raise VidsUIError("原生时长控件发生变化；未提交生成", "VIDS_SETTINGS_UNCONFIRMED")
        slider.first.press("Home", timeout=control.timeout_ms())
        for _ in range(int(task.duration_sec) - 3):
            control.check()
            slider.first.press("ArrowRight", timeout=control.timeout_ms())
        actual = slider.first.input_value(timeout=control.timeout_ms())
        if actual != str(int(task.duration_sec)):
            raise VidsUIError("Vids 时长设置未生效", "VIDS_SETTINGS_UNCONFIRMED")
        page.keyboard.press("Escape")
        label = button.first.get_attribute("aria-label") or ""
        aspect_ok = bool(re.search(r"横屏|Landscape", label, re.I)) if landscape else bool(re.search(r"竖屏|Portrait", label, re.I))
        duration_ok = bool(re.search(rf"\b{int(task.duration_sec)}\s*(秒|seconds?|s)\b", label, re.I))
        # Chinese does not have an ASCII word boundary after 秒.
        duration_ok = duration_ok or f"{int(task.duration_sec)} 秒" in label
        if resolution not in label or not aspect_ok or not duration_ok or "Omni" not in label:
            raise VidsUIError(f"生成设置无法确认：{label}", "VIDS_SETTINGS_UNCONFIRMED")
        logs.append(f"原生设置已回读确认：{label}")

    def _upload_multiple_assets(self, page, sidebar, paths, control, logs):
        clear_btn = sidebar.get_by_role("button", name=re.compile(r"^(清除|Clear)$", re.I))
        if self._visible(clear_btn):
            clear_btn.first.click(timeout=control.timeout_ms())
            control.pause(page, 0.5)

        for idx, p in enumerate(paths, 1):
            control.check()
            resolved_p = str(Path(p).resolve())
            if idx == 1:
                btn = sidebar.get_by_role("button", name=re.compile(r"^(素材|Assets?|Ingredients?)$", re.I))
                if not self._visible(btn):
                    btn = sidebar.locator(
                        'button[aria-label*="素材" i], button[aria-label*="Ingredient" i], '
                        'button:has-text("素材"), button:has-text("Ingredients")'
                    )
                self._wait(page, control, lambda: self._visible(btn), "未找到‘素材’上传入口", seconds=20)
                try:
                    with page.expect_file_chooser(timeout=control.timeout_ms(7000)) as chooser:
                        btn.first.click(timeout=control.timeout_ms())
                    chooser.value.set_files(resolved_p, timeout=control.timeout_ms(10000))
                except Exception as fc_err:
                    logs.append(f"首次素材上传触发 filechooser 异常，尝试通过原生 input 设置: {fc_err}")
                    file_input = page.locator('input[type="file"]')
                    if file_input.count() > 0:
                        file_input.first.set_input_files(resolved_p, timeout=control.timeout_ms(10000))
                    else:
                        raise
            else:
                add_btn = sidebar.locator(
                    'button[aria-label*="avatar or ingredients" i], button[aria-label*="虚拟形象或素材" i], '
                    'button:has-text("Add"), button:has-text("添加")'
                )
                self._wait(page, control, lambda: self._visible(add_btn), f"未找到添加第 {idx} 张素材的入口", seconds=25)
                add_btn.first.click(timeout=control.timeout_ms())
                control.pause(page, 0.8)

                file_inputs = page.locator('input[type="file"]')
                if file_inputs.count() > 0:
                    file_inputs.last.set_input_files(resolved_p, timeout=control.timeout_ms(10000))
                else:
                    upload_card = page.locator(
                        'button.videoGenCreationViewFileInputsInputSelectButton, '
                        'button[aria-label="Upload" i], button[aria-label="上传" i], '
                        'button:has-text("Upload"), button:has-text("上传")'
                    )
                    self._wait(page, control, lambda: self._visible(upload_card), "未找到素材‘上传’选项卡片", seconds=10)
                    with page.expect_file_chooser(timeout=control.timeout_ms(7000)) as chooser:
                        upload_card.first.click(timeout=control.timeout_ms())
                    chooser.value.set_files(resolved_p, timeout=control.timeout_ms(10000))

                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

            preview = sidebar.locator(
                f'[aria-label*="移除图片 {idx}"], [aria-label*="移除图片"], '
                f'[aria-label*="Remove image {idx}" i], [aria-label*="Remove image" i], '
                'img.inputPreviewItemPreview'
            )
            self._wait(page, control, lambda: self._visible(preview) and preview.count() >= idx,
                       f"第 {idx} 张素材未完成上传绑定", seconds=35)
            logs.append(f"第 {idx} 张素材已成功绑定至 Vids（@图片 {idx}）：{Path(p).name}")
        self._dismiss_overlays(page, logs, control)
        logs.append(f"Vids 多素材上传完成，共绑定 {len(paths)} 张参考帧")

    def _upload(self, page, sidebar, path, control, logs):
        remove = sidebar.get_by_role("button", name=re.compile(r"^(移除图片|Remove image)$", re.I))
        if self._visible(remove):
            remove.first.click(timeout=control.timeout_ms())
        add = sidebar.get_by_role("button", name=re.compile(r"^(添加图片|Add image)$", re.I))
        self._wait(page, control, lambda: self._visible(add), "未找到添加图片入口")
        control.check()
        with page.expect_file_chooser(timeout=control.timeout_ms(7000)) as chooser:
            add.first.click(timeout=control.timeout_ms())
        chooser.value.set_files(str(Path(path).resolve()), timeout=control.timeout_ms(10000))
        image = sidebar.locator('img.inputPreviewItemPreview')
        self._wait(page, control, lambda: self._visible(image) and image.first.evaluate(
            "e => e.complete && e.naturalWidth > 0") and self._visible(remove),
            "图片未完成上传或未绑定到 Vids 添加动画面板；请求未提交", seconds=35)
        self._dismiss_overlays(page, logs, control)
        logs.append("首帧/参考图真实上传完成，已确认原生预览与移除图片控件")

    def _validate_output(self, path, task, control, logs):
        probe = shutil.which("ffprobe")
        if not probe:
            raise VidsUIError("缺少 ffprobe，不能验证成片规格", "VIDEO_OUTPUT_INVALID")
        control.check()
        result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=min(15, control.remaining))
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        w, h = stream.get("width", 0), stream.get("height", 0)
        # ffprobe may report stream.duration="N/A" even for a valid MP4.
        # Prefer a finite, positive stream value; otherwise try the container.
        duration = 0.0
        for value in (stream.get("duration"), data.get("format", {}).get("duration")):
            try:
                candidate = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(candidate) and candidate > 0:
                duration = candidate
                break
        size = 1080 if "1080" in (task.model or "") else 720
        expected = (size * 16 // 9, size) if task.aspect_ratio == "16:9" else (size, size * 16 // 9)
        if result.returncode or not duration or (w, h) != expected or abs(duration - task.duration_sec) > 0.6:
            raise VidsUIError(f"实际成片 {w}×{h}/{duration:.2f}s 与请求 {expected}/{task.duration_sec}s 不符；未标记成功", "VIDEO_OUTPUT_INVALID")
        control.check()
        logs.append(f"真实成片规格通过：{w}×{h} / {duration:.3f}s")

    def run_page(self, page, task, control, logs):
        """One native submission; separable for live DOM regression tests."""
        self._dismiss_overlays(page, logs, control)
        sidebar = page.locator('[role="complementary"][class*="Videogensidebar"]')
        if not self._visible(sidebar):
            entry = page.locator('#content-library-rail-video-generation-element')
            self._wait(page, control, lambda: self._visible(entry), "未找到 Google Vids AI 视频入口", seconds=25)
            try:
                entry.first.click(timeout=control.timeout_ms())
            except Exception as click_err:
                logs.append(f"AI视频入口初次点击被遮挡或超时，尝试清除遮罩后重试: {click_err}")
                self._dismiss_overlays(page, logs, control)
                entry.first.click(timeout=control.timeout_ms())
            self._wait(page, control, lambda: self._visible(sidebar), "AI 视频侧边栏未展开")
        sidebar = sidebar.first
        # 汇总当前任务资产列表（支持 1~3 张图片多素材绑定）
        asset_paths = []
        if getattr(task, "image_paths", None) and isinstance(task.image_paths, list):
            asset_paths = [str(p) for p in task.image_paths if p]
        else:
            if task.start_image_path:
                for p in str(task.start_image_path).split(";"):
                    if p.strip() and p.strip() not in asset_paths:
                        asset_paths.append(p.strip())
            if getattr(task, "ref_image_path", None) and task.ref_image_path:
                for p in str(task.ref_image_path).split(";"):
                    if p.strip() and p.strip() not in asset_paths:
                        asset_paths.append(p.strip())
            if task.end_image_path and str(task.end_image_path) not in asset_paths:
                for p in str(task.end_image_path).split(";"):
                    if p.strip() and p.strip() not in asset_paths:
                        asset_paths.append(p.strip())
        asset_paths = asset_paths[:3]
        has_assets = len(asset_paths) > 0

        # 仅当任务明确指定为 animate 动图模式，或在没有提示词且仅有1张图片时，才进入“添加动画|Animate”
        # 只要存在提示词或明确是参考图生成，即使只有 1 张参考图，也必须保持在“创建|Create”模式下挂载素材
        is_animate_only = getattr(task, "generation_mode", "") == "animate" or (not task.prompt.strip() and len(asset_paths) == 1)
        if is_animate_only:
            mode = "添加动画|Animate"
        else:
            mode = "创建|Create"
        tab = sidebar.get_by_role("tab", name=re.compile(rf"^({mode})$", re.I))
        self._wait(page, control, lambda: self._visible(tab), "未找到所请求的 Vids 原生模式")
        tab.first.click(timeout=control.timeout_ms())
        expand = sidebar.get_by_role("button", name=re.compile(r"^(展开|Expand)$", re.I))
        if self._visible(expand):
            expand.first.click(timeout=control.timeout_ms())
        if mode == "添加动画|Animate":
            self._upload(page, sidebar, asset_paths[0], control, logs)
        elif has_assets:
            self._upload_multiple_assets(page, sidebar, asset_paths, control, logs)
        self._configure(page, sidebar, task, control, logs)
        prompt = sidebar.get_by_role("tabpanel").get_by_role("textbox")
        self._wait(page, control, lambda: self._visible(prompt), "未找到当前模式的提示词输入框")
        p_clean = task.prompt.strip()
        if has_assets and mode != "添加动画|Animate":
            prompt.first.click(timeout=control.timeout_ms())
            prompt.first.press("End", timeout=control.timeout_ms())
            prompt.first.press_sequentially(f" {p_clean}", timeout=control.timeout_ms())
        else:
            prompt.first.fill(p_clean, timeout=control.timeout_ms())
        raw_text = prompt.first.inner_text().strip()
        prefix = p_clean[:25].strip()
        if p_clean not in raw_text and prefix not in raw_text and prompt.first.input_value().strip() != p_clean:
            raise VidsUIError("提示词写入未生效，未提交生成")
        baseline = {self.media_identity(r['src']) for r in self._media_rows(page)}
        generate = sidebar.locator(
            'button[aria-label="Generate" i], button[aria-label="生成" i], '
            'button:has-text("Generate"), button:has-text("生成")'
        )
        if not self._visible(generate):
            generate = sidebar.get_by_role("tabpanel").get_by_role("button", name=re.compile(r"^(生成|Generate)$", re.I))
        self._wait(page, control, lambda: self._visible(generate) and generate.first.is_enabled(), "生成按钮仍不可用；检查素材/额度")
        control.check()
        # Set before click: a lost click response must not cause a second spend.
        self._mark_submission(task.id)
        started = time.monotonic()
        generate.first.click(timeout=control.timeout_ms())
        logs.append("已在 docs.google.com/videos 提交一次，等待本次侧栏新结果（不会自动再次提交）")
        reported = -1
        while True:
            control.check()
            rows = self._media_rows(page)
            media = self.pick_current_media(rows, baseline, task.prompt)
            if media:
                logs.append(f"本次侧栏新结果已就绪；云端等待 {time.monotonic()-started:.1f}s")
                return media
            text = sidebar.inner_text(timeout=control.timeout_ms())
            if re.search(r"against our terms|content policy|违反服务条款|不符合.*条款", text, re.I):
                raise VidsUIError("Google Vids 内容政策拦截；提示词未被擅自改写", "SAFETY_FILTER_BLOCKED")
            if re.search(r"unusual activity|异常活动", text, re.I):
                raise VidsUIError("Google 检测到异常活动，请核对原项目", "UNUSUAL_ACTIVITY")
            if re.search(r"couldn.t generate|generation failed|生成失败|未能生成|无法生成", text, re.I):
                raise VidsUIError("Vids 页面报告生成失败；请核对原项目后再手动提交", "VIDS_RESULT_UNCONFIRMED")
            elapsed = int(time.monotonic()-started)
            if elapsed // 15 != reported:
                reported = elapsed // 15
                logs.append(f"云端等待 {elapsed}s；尚无本次新成片")
            control.pause(page, 1)

    def _execute_browser_task(self, task: Task, profile: Profile):
        logs, browser, playwright_ctx, page = [], None, None, None
        control = self.begin_task(task.id)
        stage = "preflight"
        output = self.output_dir / f"{task.id}.mp4"
        part = self.output_dir / f"{task.id}.part.mp4"
        started = time.monotonic()
        try:
            control.check()
            validate_video_request(task)
            if task.engine != "vids":
                raise VideoRequestError("VidsWorker 只接受显式 Google Vids 请求")
            profile_dir = self._resolve_profile_dir(profile)
            profile_dir.mkdir(parents=True, exist_ok=True)
            logs.append(f"Google Vids · {task.id} · {profile.name}；完整超时 {self.timeout_sec}s")
            if self.mock_sample_video and Path(self.mock_sample_video).is_file() and os.environ.get("VIDS_MOCK_MODE") == "1":
                shutil.copyfile(self.mock_sample_video, part)
                self._validate_output(part, task, control, logs)
                part.replace(output)
                return {"success": True, "output_video_path": str(output), "logs": "\n".join(logs), "mock": True, "submission_possible": False}
            from playwright.sync_api import sync_playwright
            stage = "browser_launch"
            playwright_ctx = sync_playwright().start()
            browser = playwright_ctx.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), channel="chrome", headless=self.headless,
                timeout=control.timeout_ms(15000), args=["--disable-infobars"])
            with self._sessions_lock:
                self._active_sessions[task.id].update(browser=browser, profile=profile)
            control.check()
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.set_default_timeout(5000)
            stage = "navigation"
            target = task.project_id if (task.project_id and str(task.project_id).startswith("https://docs.google.com/videos/")) else "https://docs.google.com/videos/create"
            if not target.startswith("https://docs.google.com/videos/"):
                raise VideoRequestError("Vids 工程必须为 docs.google.com/videos 的 HTTPS 地址")
            page.goto(target, timeout=control.timeout_ms(30000), wait_until="domcontentloaded")
            control.check()
            if "accounts.google.com" in page.url:
                raise VidsUIError("Google 登录态失效，请重新登录 Vids", "AUTH_EXPIRED")
            stage = "native_generation"
            media = self.run_page(page, task, control, logs)
            control.check()
            stage = "download"
            # Archive while the owned session is alive. URLs are never logged.
            if media.startswith("blob:"):
                encoded = page.evaluate("""async url => {
                    const blob = await (await fetch(url)).blob();
                    if (blob.size > 64*1024*1024) throw Error('视频超过64MiB归档上限');
                    return await new Promise((resolve,reject)=>{let r=new FileReader();
                        r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob);});
                }""", media)
                part.write_bytes(base64.b64decode(encoded.split(",", 1)[1]))
            else:
                response = page.request.get(media, timeout=control.timeout_ms(25000))
                try:
                    if response.status != 200:
                        raise VidsUIError(f"Vids 下载返回 HTTP {response.status}", "VIDS_RESULT_UNCONFIRMED")
                    part.write_bytes(response.body())
                finally:
                    response.dispose()
            control.check()
            stage = "media_validation"
            self._validate_output(part, task, control, logs)
            part.replace(output)
            logs.append(f"生成与本地归档完成，总耗时 {time.monotonic()-started:.1f}s")
            return {"success": True, "pid": os.getpid(), "output_video_path": str(output), "logs": "\n".join(logs), "submission_possible": True}
        except Exception as exc:
            with self._sessions_lock:
                submitted = self._active_sessions.get(task.id, {}).get("submitted", False)
            code = getattr(exc, "code", "VIDS_EXEC_EXCEPTION")
            if isinstance(exc, VideoRequestError):
                code = "INVALID_VIDEO_REQUEST"
            elif code != "USER_CANCELLED" and submitted and code not in ("SAFETY_FILTER_BLOCKED", "VIDEO_OUTPUT_INVALID"):
                code = "VIDS_RESULT_UNCONFIRMED"
            elif not submitted and re.search(r"singleton|profile.*in use|already running|processsingleton", str(exc), re.I):
                code = "PROFILE_LOCKED"
            message = str(exc).split("Call log:", 1)[0]
            # Playwright failures may contain a signed URL; do not persist it.
            message = re.sub(r"https?://\S+", "[URL省略]", message)
            logs.append(f"阶段 {stage} 失败（{code}），总耗时 {time.monotonic()-started:.1f}s：{message}")
            if page:
                try:
                    qa = self.output_dir.parent / "qa" / f"{task.id}_vids_failure.png"
                    qa.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(qa), timeout=3000)
                    logs.append(f"诊断截图：{qa}")
                except Exception:
                    pass
            return {"success": False, "pid": os.getpid(), "error_code": code,
                    "error_message": message, "output_video_path": None, "logs": "\n".join(logs),
                    "submission_possible": bool(submitted)}
        finally:
            # Only the owner closes its own context; preserve cancellation until
            # it exits, so retry/delete cannot race an old worker.
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_ctx:
                try:
                    playwright_ctx.stop()
                except Exception:
                    pass
            with self._sessions_lock:
                self._active_sessions.pop(task.id, None)
            part.unlink(missing_ok=True)
