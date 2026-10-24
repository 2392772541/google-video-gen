from __future__ import annotations
import os
import sys
import time
import json
import re
import math
import base64
import urllib.request
import threading
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from .models import Task, Profile
from .image_worker import BrowserImageWorker
from .execution_control import ExecutionControl, ExecutionStopped
from .video_contract import validate_video_request, VideoRequestError
from .vids_worker import VidsWorker
import psutil

_PROFILE_LOCKS = {}
_PROFILE_LOCKS_GUARD = threading.Lock()

def get_profile_lock(profile_name: str) -> threading.Lock:
    with _PROFILE_LOCKS_GUARD:
        if profile_name not in _PROFILE_LOCKS:
            _PROFILE_LOCKS[profile_name] = threading.Lock()
        return _PROFILE_LOCKS[profile_name]

class GeminiVideoSettingsError(RuntimeError):
    """A requested native setting cannot be verified; never submit speculatively."""

    def __init__(self, message: str, code: str = "UNSUPPORTED_FEATURE"):
        super().__init__(message)
        self.code = code


class GeminiWebWorker(VidsWorker):
    """
    Worker for orchestrating video generation on gemini.google.com/videos via persistent Chrome profiles.
    - Zero cookie leakage: uses local isolated Chrome profile directories.
    - Automatic overlay / discovery-card dismissal to prevent pointer event interception.
    - Direct navigation to https://gemini.google.com/videos with native [Videos] mode capsule.
    - Native UI aspect ratio selection: Landscape (16:9) vs Portrait (9:16).
    - Native UI model selection: 3.8 Flash, 3.1 Pro, Extended thinking, etc.
    - Early refusal / text-script detection to prevent idle timeout loops.
    - Dual-track video extraction: authenticated in-page blob fetch & native download button capture.
    """
    def __init__(
        self,
        output_dir: Path = Path("video_farm_data/outputs"),
        timeout_sec: int = 360,
        headless: bool = True,
        python_bin=None,
        submission_state_path=None,
        mock_sample_video=None,
    ):
        super().__init__(output_dir, timeout_sec, headless, mock_sample_video,
                         python_bin, submission_state_path)
        self._execution = threading.local()
        self._image_worker = BrowserImageWorker(self.output_dir, timeout_sec, headless=headless)

    provider_label = "Gemini"
    unconfirmed_code = "GEMINI_RESULT_UNCONFIRMED"
    mock_env_var = "GEMINI_MOCK_MODE"

    def _validate_request(self, task):
        validate_video_request(task)
        if task.engine != "gemini":
            raise VideoRequestError("GeminiWebWorker 只接受显式 Gemini 请求")

    def _runner_command(self, request_path):
        return [self.python_bin, "-m", "video_farm.gemini_web_runner", str(request_path)]

    def has_live_execution(self, task_id: str) -> bool:
        return super().has_live_execution(task_id) or self._image_worker.has_live_execution(task_id)

    def _validate_output(self, path, task, control, logs):
        """Bounded independent probe; Gemini does not inherit Vids resolution rules."""
        probe = shutil.which("ffprobe")
        if not probe:
            raise GeminiVideoSettingsError("缺少 ffprobe，不能验证成片规格", "VIDEO_OUTPUT_INVALID")
        control.check()
        result = subprocess.run(
            [probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height,duration:format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=min(15, control.remaining))
        data = json.loads(result.stdout or "{}")
        stream = (data.get("streams") or [{}])[0]
        width, height = stream.get("width", 0), stream.get("height", 0)
        if (result.returncode or not isinstance(width, (int, float))
                or not isinstance(height, (int, float))
                or not all(math.isfinite(v) and v > 0 for v in (width, height))):
            raise GeminiVideoSettingsError("成片没有可核验的视频尺寸", "VIDEO_OUTPUT_INVALID")
        expected_ratio = 16 / 9 if task.aspect_ratio == "16:9" else 9 / 16
        if abs(width / height - expected_ratio) / expected_ratio > 0.02:
            raise GeminiVideoSettingsError(
                f"实际成片 {width}×{height} 与请求画幅 {task.aspect_ratio} 不符", "VIDEO_ASPECT_MISMATCH")
        duration = 0.0
        for value in (stream.get("duration"), data.get("format", {}).get("duration")):
            try:
                candidate = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(candidate) and candidate > 0:
                duration = candidate
                break
        if not duration:
            raise GeminiVideoSettingsError("成片没有可核验的时长", "VIDEO_OUTPUT_INVALID")
        if abs(duration - task.duration_sec) > 0.5:
            raise GeminiVideoSettingsError(
                f"实际成片 {duration:.3f}s 与请求 {task.duration_sec}s 不符", "VIDEO_DURATION_MISMATCH")
        control.check()
        logs.append(f"真实成片规格通过：{width}×{height} / {duration:.3f}s")

    def prepare_image_task(self, task_id: str, cancel_event: threading.Event) -> None:
        self._image_worker.prepare_task(task_id, cancel_event)

    def execute_image_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        return self._image_worker.execute_image_task(task, profile)

    def prepare_task(self, task_id: str, cancel_event: threading.Event) -> None:
        with self._sessions_lock:
            self._active_sessions.setdefault(task_id, {}).update(cancel_event=cancel_event, cancelled=cancel_event.is_set())

    def discard_prepared_task(self, task_id: str) -> bool:
        """Remove a reservation only before an execution owner has started."""
        with self._sessions_lock:
            session = self._active_sessions.get(task_id)
            if not session or session.get("control") or session.get("browser") or session.get("proc"):
                return False
            self._active_sessions.pop(task_id, None)
            return True

    def begin_task(self, task_id, timeout_sec=None):
        with self._sessions_lock:
            session = self._active_sessions.setdefault(task_id, {})
            event = session.setdefault("cancel_event", threading.Event())
            if session.get("cancelled"):
                event.set()
            control = ExecutionControl(event, self.timeout_sec if timeout_sec is None else timeout_sec)
            session["control"] = control
            self._execution.control = control
            return control

    def _pause(self, page, seconds):
        control = getattr(self._execution, "control", None)
        if control:
            control.pause(page, seconds)
        else:
            page.wait_for_timeout(seconds * 1000)

    def _timeout(self, maximum=5000):
        control = getattr(self._execution, "control", None)
        return control.timeout_ms(maximum) if control else maximum

    def _wait_for_attachments(self, page, expected_count, image_count=0):
        """Do not submit a partial upload, a spinner, or a broken preview."""
        until = time.monotonic() + getattr(self, "_attachment_upload_timeout_sec", 45)
        while True:
            control = getattr(self._execution, "control", None)
            if control:
                control.check()
            previews = page.query_selector_all("uploader-file-preview")
            if not previews:
                # Fallback class names can occur on both parent and child nodes.
                previews = [node for node in page.query_selector_all('[class*="file-preview"]')
                            if node.evaluate("e => !e.parentElement?.closest('[class*=file-preview]')")]
            spinners = page.query_selector_all(
                'uploader-file-preview mat-spinner, uploader-file-preview [role="progressbar"], '
                'uploader-file-preview .loading, [class*="file-preview"] mat-spinner, '
                '[class*="file-preview"] [role="progressbar"], [class*="file-preview"] .loading')
            images = [image for preview in previews for image in preview.query_selector_all("img")]
            if (len(previews) == expected_count and not spinners and len(images) >= image_count
                    and all(image.evaluate("e => e.complete && e.naturalWidth > 0") for image in images)):
                return
            if time.monotonic() >= until:
                raise GeminiVideoSettingsError(
                    f"参考素材尚未全部上传就绪（需要 {expected_count} 个）；请求未发送，请检查文件或网络。",
                    "ATTACHMENT_NOT_READY")
            self._pause(page, 0.5)

    def cancel_task(self, task_id: str) -> bool:
        """Never call synchronous Playwright from another thread."""
        if self._image_worker.cancel_task(task_id):
            return True
        with self._sessions_lock:
            session = self._active_sessions.get(task_id)
            if not session:
                return False
            session["cancelled"] = True
            if session.get("cancel_event"):
                session["cancel_event"].set()
            return True

    def _resolve_profile_dir(self, profile: Profile) -> Path:
        if profile.profile_path:
            return Path(profile.profile_path).resolve()
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile.name}"

    def _dismiss_overlays(self, page, logs: list) -> None:
        """主动检测并关闭欢迎弹窗、条款提示、新功能推荐遮罩层，防止拦截输入与点击。"""
        for selector in ("[role='dialog'] button:has-text('I agree')", "[role='dialog'] button:has-text('Agree')",
                         "[role='dialog'] button:has-text('同意')", "[role='dialog'] button:has-text('Accept all')"):
            button = page.query_selector(selector)
            if button and button.is_visible():
                raise GeminiVideoSettingsError("网页要求同意协议/授权；请在原网页手动处理后重试。", "USER_ACTION_REQUIRED")
        dismiss_selectors = [
            "mat-dialog-container button[aria-label*='Close']",
            "mat-dialog-container button[aria-label*='close']",
            "[role='dialog'] button:has-text('Got it')",
            "[role='dialog'] button:has-text('Dismiss')",
            "[role='dialog'] button:has-text('Not now')",
            "[role='dialog'] button:has-text('Close')",
            "[role='dialog'] button:has-text('知道了')",
            "[role='dialog'] button:has-text('关闭')",
            "[role='dialog'] button:has-text('稍后再说')",
            ".cdk-overlay-container button[aria-label*='Close']",
            ".cdk-overlay-container button:has-text('Got it')",
            ".cdk-overlay-backdrop"
        ]
        for sel in dismiss_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    logs.append(f"检测到页面弹出浮层遮罩 ({sel})，自动点击关闭...")
                    btn.click(timeout=self._timeout())
                    self._pause(page, 0.6)
            except ExecutionStopped:
                raise
            except Exception:
                pass
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    _ASPECT_BUTTON_SELECTOR = (
        'button[aria-label*="16:9"], button[aria-label*="9:16"], '
        'button[aria-label*="Aspect ratio"], button[aria-label*="宽高比"], '
        'button:has-text("Landscape"), button:has-text("Portrait"), '
        'button:has-text("横向"), button:has-text("纵向"), '
        'button:has-text("16:9"), button:has-text("9:16"), '
        'button:has-text("Aspect ratio"), button:has-text("宽高比")'
    )
    _ASPECT_OPTION_SELECTOR = (
        '[role="menuitemradio"], [role="menuitem"], [role="option"], mat-option'
    )

    @staticmethod
    def _native_aspect(element) -> Optional[str]:
        # Current Gemini exposes the numbers in aria-label, not visible text.
        for label in (element.get_attribute("aria-label") or "", element.inner_text()):
            match = re.search(r"(?<!\d)(16\s*:\s*9|9\s*:\s*16)(?!\d)", label)
            if match:
                return re.sub(r"\s+", "", match.group(1))
            clean_label = re.sub(r"\s+", "", label).lower()
            if any(k in clean_label for k in ("landscape", "横向", "横屏")):
                return "16:9"
            if any(k in clean_label for k in ("portrait", "纵向", "竖屏")):
                return "9:16"
        return None

    def _aspect_button(self, page):
        for button in page.query_selector_all(self._ASPECT_BUTTON_SELECTOR):
            if button.is_visible() and self._native_aspect(button):
                return button
        return None

    def _configure_video_aspect(self, page, aspect: str, logs: list) -> None:
        if aspect not in ("16:9", "9:16"):
            raise GeminiVideoSettingsError(
                f"Gemini 网页视频当前仅支持 16:9 / 9:16，不能提交 {aspect}；请更改比例。"
            )
        try:
            page.wait_for_selector(self._ASPECT_BUTTON_SELECTOR, state="visible", timeout=self._timeout(10000))
            button = self._aspect_button(page)
            if not button or not button.is_enabled():
                raise GeminiVideoSettingsError("未找到可用的 Gemini 原生比例控件，已停止提交，避免生成错误画幅。")
            if self._native_aspect(button) == aspect:
                logs.append(f"已核验 Gemini 原生画幅: {aspect}")
                return

            button.click(timeout=5000)
            page.wait_for_selector(self._ASPECT_OPTION_SELECTOR, state="visible", timeout=4000)
            option = next((item for item in page.query_selector_all(self._ASPECT_OPTION_SELECTOR)
                           if item.is_visible() and self._native_aspect(item) == aspect), None)
            if not option or not option.is_enabled() or option.get_attribute("aria-disabled") == "true":
                raise GeminiVideoSettingsError(f"Gemini 比例菜单未提供可用的 {aspect} 选项，已停止提交。")
            option.click(timeout=5000)
            # A successful click is not proof the option took effect. Re-read the
            # live button after the menu closes (the option node may be detached).
            for _ in range(8):
                current = self._aspect_button(page)
                if current and self._native_aspect(current) == aspect:
                    logs.append(f"已切换并核验 Gemini 原生画幅: {aspect}")
                    return
                self._pause(page, 0.25)
            raise GeminiVideoSettingsError(f"Gemini 未确认切换为 {aspect}，已停止提交，未消耗生成次数。")
        except GeminiVideoSettingsError:
            raise
        except Exception as exc:
            raise GeminiVideoSettingsError(
                f"无法核验 Gemini 原生比例 {aspect}，已停止提交；请检查网页控件或视频权限。"
            ) from exc

    @staticmethod
    def _validate_video_output(path: Path, aspect: str, requested_duration: int, logs: list) -> None:
        import cv2

        capture = cv2.VideoCapture(str(path))
        try:
            if not capture.isOpened():
                raise GeminiVideoSettingsError("Gemini 返回的文件无法读取为视频。", "VIDEO_OUTPUT_INVALID")
            width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = capture.get(cv2.CAP_PROP_FPS)
            frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
            # Reject unreadable/non-finite metadata before int conversion or
            # duration arithmetic, so invalid media cannot be marked successful.
            if not all(isinstance(value, (int, float)) and math.isfinite(value) and value > 0
                       for value in (width, height, fps, frames)):
                raise GeminiVideoSettingsError("Gemini 返回的视频缺少有效尺寸或时长。", "VIDEO_OUTPUT_INVALID")
            width, height = int(width), int(height)
            if width <= 0 or height <= 0:
                raise GeminiVideoSettingsError("Gemini 返回的视频尺寸无效。", "VIDEO_OUTPUT_INVALID")
            duration = frames / fps
            logs.append(f"Gemini 实际成片: {width}×{height} · {duration:.1f} 秒")
            numerator, denominator = (int(part) for part in aspect.split(":"))
            if abs((width / height) / (numerator / denominator) - 1) > 0.02:
                raise GeminiVideoSettingsError(
                    f"请求画幅 {aspect}，Gemini 实际返回 {width}×{height}；已拦截错误画幅，未标记成功。",
                    "VIDEO_ASPECT_MISMATCH",
                )
            if requested_duration and abs(duration - requested_duration) > 0.5:
                raise GeminiVideoSettingsError(
                    f"请求 {requested_duration} 秒，Gemini 实际返回 {duration:.1f} 秒；已拦截时长不符的产物，未标记成功。",
                    "VIDEO_DURATION_MISMATCH",
                )
        finally:
            capture.release()

    def _execute_browser_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        
        logs = []
        logs.append(f"[{worker_name}] 启动 Gemini 网页版原生视频生成引擎 (Profile: {profile.name})")
        logs.append(f"Profile 目录: {profile_dir}")
        logs.append(f"Prompt: {task.prompt}")

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)
            logs.append(f"初始化建立 Profile 用户数据目录: {profile_dir}")

        from playwright.sync_api import sync_playwright

        output_video_path = self.output_dir / f"{task.id}.mp4"

        control = self.begin_task(task.id)
        request_submitted = False
        outcome = {}
        try:
            control.check()
            self._validate_request(task)
            with sync_playwright() as p:
                launch_args = ["--disable-infobars"]
                
                logs.append("正在拉起 Chrome 浏览器会话...")
                try:
                    browser = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        channel="chrome",
                        headless=self.headless,
                        args=launch_args, timeout=self._timeout(15000)
                    )
                    with self._sessions_lock:
                        self._active_sessions.setdefault(task.id, {}).update(browser=browser, profile=profile)
                except ExecutionStopped:
                    raise
                except Exception as launch_exc:
                    lexc_str = str(launch_exc).lower()
                    logs.append(f"拉起浏览器异常: {launch_exc}")
                    if any(k in lexc_str for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                        logs.append("【检测到目录锁】Chrome Profile 正在被外部浏览器窗口独占占用。")
                        outcome.update({
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "PROFILE_LOCKED",
                            "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 关闭占用 Chrome】后再试。",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        })
                        return outcome
                    raise launch_exc

                try:
                    page = browser.new_page()
                    page.set_default_timeout(5000)
                    page.set_default_navigation_timeout(15000)
                    
                    # 1. 优先直达原生视频生成工作台
                    logs.append("正在打开 Gemini 视频工作区 https://gemini.google.com/videos ...")
                    try:
                        page.goto("https://gemini.google.com/videos", wait_until="domcontentloaded", timeout=self._timeout(25000))
                    except ExecutionStopped:
                        raise
                    except Exception as ge:
                        logs.append(f"直接打开 /videos 超时或异常，尝试主入口 /app ... ({ge})")
                        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=self._timeout(20000))

                    self._pause(page, 3)
                    self._dismiss_overlays(page, logs)

                    cur_url = page.url
                    page_title = page.title()
                    logs.append(f"页面加载完成: Title='{page_title}', URL='{cur_url}'")

                    # 若被重定向到 /app，主动点击左侧导航栏的 Videos 进入视频模式
                    in_video_workspace = "/videos" in cur_url
                    if not in_video_workspace:
                        logs.append("当前未在 /videos 路径，正在尝试切换至左侧【Videos】专属工作区...")
                        video_nav_selectors = [
                            'a[href="/videos"]',
                            'a[href*="/videos"]',
                            'a[href*="videos"]',
                            'gem-nav-list-item:has-text("Videos")',
                            'gem-nav-list-item:has-text("视频")',
                            'button:has-text("Videos")',
                            'button:has-text("视频")',
                            'a:has-text("视频")',
                            '[data-test-id*="video"]'
                        ]
                        for nav_sel in video_nav_selectors:
                            try:
                                vnav = page.query_selector(nav_sel)
                                if vnav and vnav.is_visible():
                                    vnav.click(timeout=self._timeout())
                                    self._pause(page, 2)
                                    self._dismiss_overlays(page, logs)
                                    logs.append(f"成功切换至视频工作区: URL='{page.url}'")
                                    if "/videos" in page.url:
                                        in_video_workspace = True
                                    break
                            except ExecutionStopped:
                                raise
                            except Exception:
                                pass

                    if not in_video_workspace and "/videos" not in page.url:
                        # 检查当前页面是否具备任何视频模式或画幅控件
                        has_video_feature = any(
                            bool(page.query_selector(sel))
                            for sel in [self._ASPECT_BUTTON_SELECTOR, 'button:has-text("Videos")', 'button:has-text("视频")']
                        )
                        if not has_video_feature:
                            raise GeminiVideoSettingsError(
                                f"当前 Google 账号 ({profile.name}) 未开通 Gemini 原生视频生成 (Videos) 内测权限，页面未提供视频工作区或画幅控件；未提交请求，未扣除额度。请使用具备权限的账号或选用 Google Flow / Vids 引擎。",
                                "ACCOUNT_VIDEO_UNAUTHORIZED"
                            )

                    # 2. 登录状态核验：优先寻找输入框
                    input_selector = 'rich-textarea div[contenteditable="true"], div.ql-editor[contenteditable="true"], [contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=self._timeout(8000))
                        has_input = True
                    except ExecutionStopped:
                        raise
                    except Exception:
                        has_input = False

                    is_unauth = False
                    if not has_input:
                        if "accounts.google.com" in page.url:
                            is_unauth = True
                        else:
                            sign_in_btns = page.query_selector_all('a[href*="accounts.google.com/signin"], a[href*="accounts.google.com/ServiceLogin"], a:has-text("Sign in"), a:has-text("登录"), button:has-text("Sign in"), button:has-text("登录")')
                            if len(sign_in_btns) > 0:
                                is_unauth = True

                    if is_unauth:
                        logs.append("【拦截告警】检测到账号未在 Gemini 网页版登录或 Google 登录态已失效！")
                        outcome.update({
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "AUTH_EXPIRED",
                            "error_message": f"Gemini 网页版未登录或会话已过期 (Profile: {profile.name})。请在控制台【账号管理】点击【🌐 登录 Gemini 网页版】完成登录授权，登录后请关闭弹出的 Chrome 窗口。",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        })
                        return outcome

                    # 3. 定位输入框
                    input_el = page.query_selector(input_selector)
                    if not input_el:
                        logs.append("未能找到输入框，正在分析页面结构...")
                        for err_sel in ["div[role='alert']", ".error-message", "gemini-quota-banner"]:
                            el = page.query_selector(err_sel)
                            if el and el.is_visible():
                                txt = el.inner_text().lower()
                                if any(k in txt for k in ["quota", "limit", "额度", "上限"]):
                                    outcome.update({
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "QUOTA_EXHAUSTED",
                                        "error_message": f"检测到 Gemini 页面明确提示额度或频率限制 (Profile: {profile.name})",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    })
                                    return outcome
                        outcome.update({
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "ELEMENT_NOT_FOUND",
                            "error_message": "未在页面找到 Gemini 输入框，可能界面更新或处于非对话状态",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        })
                        return outcome

                    # Validate support now; apply the native setting after model
                    # selection and reference upload, which can reset the ratio.
                    aspect = getattr(task, "aspect_ratio", "16:9") or "16:9"
                    if aspect not in ("16:9", "9:16"):
                        raise GeminiVideoSettingsError(f"Gemini 网页视频不支持 {aspect}；请选择 16:9 或 9:16。")
                    logs.append(f"时长说明: 请求 {task.duration_sec} 秒；当前 Gemini 网页不提供可核验的秒数控件，时长由网页模式决定，不会静默裁切。")

                    # 5. 原生模型选择 (Flash vs 3.8 Flash vs 3.1 Pro 等)
                    model_info = getattr(task, "model", "auto") or "auto"
                    raw_m = str(model_info).strip().lower()
                    if raw_m not in ("auto", "gemini", "default", ""):
                        try:
                            model_btn = page.query_selector('button:has-text("Flash"), button:has-text("Pro"), button[aria-label*="model"], [data-test-id="model-selector-button"]')
                            if model_btn and model_btn.is_visible():
                                logs.append(f"正在匹配 Gemini 页面模型选择 [{model_info}] ...")
                                model_btn.click(timeout=self._timeout())
                                self._pause(page, 0.8)
                                kw = "3.8" if "3.8" in model_info else ("pro" if "pro" in model_info.lower() else ("flash" if "flash" in model_info.lower() else model_info))
                                opt_el = page.query_selector(f'[role="menuitem"]:has-text("{kw}"), [role="option"]:has-text("{kw}"), mat-option:has-text("{kw}"), button:has-text("{kw}")')
                                if opt_el and opt_el.is_visible():
                                    opt_el.click(timeout=self._timeout())
                                    logs.append(f"已成功切换模型至目标模式 [{kw}]")
                                    self._pause(page, 0.8)
                                else:
                                    raise GeminiVideoSettingsError(f"所选 Gemini 模型 {model_info} 在该账号网页不可用；请求未提交。")
                            else:
                                raise GeminiVideoSettingsError("未找到 Gemini 网页模型选择控件；请求未提交。")
                        except GeminiVideoSettingsError:
                            raise
                        except ExecutionStopped:
                            raise
                        except Exception as me:
                            raise GeminiVideoSettingsError(f"无法确认 Gemini 模型设置：{me}") from me

                    # 6. 严格执行素材上传状态机: NOT_STARTED -> FILE_RESOLVED -> UPLOADING -> UPLOAD_CONFIRMED -> READY_TO_SUBMIT
                    upload_state = "NOT_STARTED"
                    media_files: list[str] = []
                    expected_images: list[Path] = []

                    if getattr(task, "input_video_path", None):
                        vp = Path(task.input_video_path).resolve()
                        if not vp.is_file():
                            raise GeminiVideoSettingsError(f"参考视频文件不存在或不可读取: {task.input_video_path}", "INPUT_FILE_NOT_FOUND")
                        media_files.append(str(vp))
                        logs.append(f"正在准备附加多模态参考视频素材: {vp.name}")

                    if task.start_image_path:
                        for p_str in str(task.start_image_path).split(";"):
                            p_clean = p_str.strip()
                            if p_clean:
                                ip = Path(p_clean).resolve()
                                if not ip.is_file():
                                    raise GeminiVideoSettingsError(f"参考图片素材文件不存在或不可读取: {p_clean}", "INPUT_FILE_NOT_FOUND")
                                expected_images.append(ip)
                                media_files.append(str(ip))
                                logs.append(f"正在准备附加参考图素材: {ip.name}")

                    if task.end_image_path:
                        raise GeminiVideoSettingsError("Gemini 网页视频通道不支持尾帧绑定能力，请改用 Google Flow 或单图动画模式", "UNSUPPORTED_FEATURE")

                    if media_files:
                        upload_state = "FILE_RESOLVED"
                        logs.append(f"[上传状态机] FILE_RESOLVED: 已完成 {len(media_files)} 个素材文件的完整性与可读性校验")

                        file_input = page.query_selector('input[type="file"]')
                        if not file_input:
                            for btn_sel in [
                                'button[aria-label*="Add"]', 'button[aria-label*="Upload"]', 'button[aria-label*="Plus"]',
                                'button[aria-label*="添加"]', 'button[aria-label*="上传"]', 'button[aria-label*="文件"]',
                                'button.mat-mdc-button-base:has-text("Add")', 'button:has-text("添加")'
                            ]:
                                try:
                                    ab = page.query_selector(btn_sel)
                                    if ab and ab.is_visible():
                                        ab.click(timeout=self._timeout())
                                        self._pause(page, 0.5)
                                        file_input = page.query_selector('input[type="file"]')
                                        if file_input:
                                            break
                                except Exception:
                                    pass

                        if not file_input:
                            upload_state = "FAILED"
                            logs.append("[上传状态机] FAILED: 未在当前页面找到可用的文件上传控件或上传按钮")
                            raise GeminiVideoSettingsError("参考素材上传入口不存在或当前模式不可用；请求未提交，不会丢弃素材。", "UPLOAD_ENTRY_NOT_FOUND")

                        upload_state = "UPLOADING"
                        logs.append(f"[上传状态机] UPLOADING: 正在执行向网页文件输入口挂载 {len(media_files)} 个素材...")
                        file_input.set_input_files(media_files)

                        logs.append("[上传状态机] 等待并确认网页端附件接收与预处理就绪...")
                        self._wait_for_attachments(
                            page, len(media_files), image_count=len(expected_images))
                        upload_state = "UPLOAD_CONFIRMED"
                        logs.append(f"[上传状态机] UPLOAD_CONFIRMED: 全部 {len(media_files)} 个素材附件上传与缩略图加载已确认完成")

                        upload_state = "READY_TO_SUBMIT"
                        logs.append("[上传状态机] READY_TO_SUBMIT: 所有参数、画幅与素材校验 100% 达成，允许安全提交生成")
                    else:
                        upload_state = "READY_TO_SUBMIT"

                    # 7. 填充提示词并安全提交
                    final_prompt = task.prompt.strip()
                    self._dismiss_overlays(page, logs)

                    # 聚焦并输入，避免被浮层截获 pointer events
                    input_el.scroll_into_view_if_needed()
                    input_el.click(timeout=self._timeout())
                    self._pause(page, 0.3)
                    input_el.fill(final_prompt)
                    logs.append(f"已填入生成提示词: {final_prompt} (引擎: Gemini网页版, 指定模型: {model_info}, 画幅: {aspect})")
                    self._pause(page, 1)

                    # Configure and verify after all uploads, immediately before
                    # submitting. Failure must never fall through to Send/Enter.
                    self._configure_video_aspect(page, aspect, logs)

                    # 发送提交
                    send_selectors = [
                        'button[aria-label="Send message"]',
                        'button[aria-label*="Send"]',
                        'button[aria-label*="发送"]',
                        '.send-button-container button',
                        '[data-test-id="send-button"]',
                        'button.send-button'
                    ]
                    baseline_response_count = len(page.query_selector_all('model-response'))
                    baseline_media = {VidsWorker.media_identity(v.get_attribute("src") or "")
                                      for v in page.query_selector_all('model-response video')}
                    control.check()
                    s_btn = next((b for selector in send_selectors
                                  if (b := page.query_selector(selector)) and b.is_visible() and b.is_enabled()), None)
                    # A lost click acknowledgement is not permission to resubmit.
                    self._mark_submission(task.id)
                    request_submitted = True
                    if s_btn:
                        s_btn.click(timeout=self._timeout())
                    else:
                        page.keyboard.press("Enter")
                    logs.append("已提交一次生成请求；未知结果不会自动重试。")

                    self._pause(page, 3)

                    # 8. 智能轮询等待视频渲染结果
                    logs.append("任务已提交，开始轮询等待视频生成渲染结果...")
                    start_wait_t = time.time()
                    video_found = False

                    while (time.time() - start_wait_t) < self.timeout_sec:
                        self._pause(page, 0.5)
                        elapsed = int(time.time() - start_wait_t)

                        if len(page.query_selector_all('model-response')) <= baseline_response_count:
                            continue

                        # A. 检查额度与频控提示
                        for err_sel in ["gemini-quota-banner", ".quota-exceeded-message", "div[role='alert']", "model-response:last-child"]:
                            el = page.query_selector(err_sel)
                            if el and el.is_visible():
                                txt = el.inner_text().lower()
                                if any(k in txt for k in ["quota exceeded", "reached your limit", "额度已达上限", "今日额度已用完", "try again tomorrow", "limit for today"]):
                                    logs.append("【额度耗尽】捕获到 Gemini 真实可见额度上限提示")
                                    outcome.update({
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "QUOTA_EXHAUSTED",
                                        "error_message": f"Gemini 今日生成额度已达上限 (Profile: {profile.name})，系统已自动换号。",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    })
                                    return outcome
                                if any(k in txt for k in ["too many requests", "rate limit", "请求过于频繁", "请稍后再试"]):
                                    logs.append("【频控拦截】捕获到 Gemini 真实可见频控提示")
                                    outcome.update({
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "RATE_LIMITED",
                                        "error_message": f"Gemini 请求频控保护 (Profile: {profile.name})，系统将自动切入冷却并换号。",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    })
                                    return outcome

                        # B. 检查是否有明确的文本拒答（提前阻断，杜绝无休止死等）
                        model_responses = page.query_selector_all("model-response")
                        if len(model_responses) > 0:
                            last_resp = model_responses[-1]
                            last_txt = last_resp.inner_text().strip()
                            # 如果回答已结束且包含拒答词
                            refusal_keywords = [
                                "无法直接生成视频", "作为语言模型", "我不能生成视频", "我无法制作视频",
                                "i cannot create videos", "i am unable to generate video", "i can't generate video",
                                "i cannot generate video", "don't have the ability to generate video"
                            ]
                            is_refusal = any(rw in last_txt.lower() for rw in refusal_keywords)
                            if is_refusal:
                                logs.append(f"【智能拒答阻断】Gemini 明确返回了文本拒答: {last_txt[:100]}...")
                                outcome.update({
                                    "success": False,
                                    "pid": os.getpid(),
                                    "error_code": "FEATURE_REFUSED",
                                    "error_message": f"Gemini 网页端当前账号回复了纯文本拒答而非视频内容。建议切换至更成熟的 Google Flow (Veo) 引擎直接生成成片视频。",
                                    "output_video_path": None,
                                    "logs": "\n".join(logs)
                                })
                                return outcome

                        # C. 检查生成的 video 元素
                        videos = page.query_selector_all('model-response:last-child video')
                        for v in videos:
                            src = v.get_attribute("src")
                            if (src and VidsWorker.media_identity(src) not in baseline_media
                                    and (src.startswith("https://") or src.startswith("blob:"))):
                                logs.append("当前回复内出现新的生成视频，准备本地归档。")
                                logs.append("正在提取完整视频成片...")
                                try:
                                    b64_data = page.evaluate("""
                                        async (video) => {
                                            try {
                                                const abort = new AbortController();
                                                const timer = setTimeout(() => abort.abort(), 15000);
                                                let res;
                                                try {res = await fetch(video.src, { credentials: 'include', signal: abort.signal });}
                                                finally {clearTimeout(timer);}
                                                if (!res.ok) return null;
                                                const blob = await res.blob();
                                                if (blob.size > 64*1024*1024) throw Error('video exceeds 64MiB');
                                                return new Promise((resolve) => {
                                                    const reader = new FileReader();
                                                    reader.onloadend = () => resolve(reader.result);
                                                    reader.readAsDataURL(blob);
                                                });
                                            } catch (err) {
                                                return null;
                                            }
                                        }
                                    """, v)
                                    if b64_data and "," in b64_data:
                                        raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                                        if len(raw_bytes) > 20000 and not raw_bytes.startswith(b"<!doctype") and not raw_bytes.startswith(b"<html"):
                                            with open(output_video_path, "wb") as vf:
                                                vf.write(raw_bytes)
                                            logs.append(f"已成功通过浏览器安全上下文转存成片 ({len(raw_bytes)} 字节): {output_video_path}")
                                            video_found = True
                                            break
                                        else:
                                            logs.append(f"上下文返回内容未就绪 (大小: {len(raw_bytes)} 字节)，继续等待渲染...")
                                except ExecutionStopped:
                                    raise
                                except Exception as e_ev:
                                    logs.append(f"页面内视频流提取提示: {e_ev}")

                        # D. 兜底方案：通过页面原生下载按钮
                        if not video_found:
                            dl_btns = page.query_selector_all("model-response:last-child a[download], model-response:last-child button[aria-label*='Download video'], model-response:last-child button[aria-label*='下载视频']")
                            if dl_btns and len(dl_btns) > 0:
                                dl_btn = dl_btns[-1]
                                if dl_btn.is_visible():
                                    try:
                                        logs.append("检测到成片下载按钮，尝试直接触发原生文件下载...")
                                        with page.expect_download(timeout=self._timeout(8000)) as dl_info:
                                            dl_btn.click(timeout=self._timeout())
                                        download = dl_info.value
                                        download.save_as(str(output_video_path))
                                        if output_video_path.exists() and output_video_path.stat().st_size > 20000:
                                            logs.append(f"已成功通过下载通道获取成片 ({output_video_path.stat().st_size} 字节)")
                                            video_found = True
                                            break
                                    except ExecutionStopped:
                                        raise
                                    except Exception as de:
                                        logs.append(f"原生下载尝试提示: {de}")

                        if video_found:
                            break

                        if elapsed % 20 == 0:
                            logs.append(f"等待生成中... 已耗时 {elapsed}s")

                    if video_found and output_video_path.exists() and output_video_path.stat().st_size > 1024:
                        self._validate_video_output(output_video_path, aspect, task.duration_sec, logs)
                        outcome.update({
                            "success": True,
                            "pid": os.getpid(),
                            "error_code": None,
                            "error_message": None,
                            "output_video_path": str(output_video_path.resolve()),
                            "logs": "\n".join(logs)
                        })
                        return outcome
                    else:
                        logs.append("超时或未捕获到生成的视频流")
                        outcome.update({
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "GEMINI_RESULT_UNCONFIRMED",
                            "error_message": f"Gemini 视频生成超时或未能在页面提取到视频元素 (耗时: {self.timeout_sec}s)",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        })
                        return outcome

                finally:
                    browser.close()
                    logs.append("浏览器会话已安全退出。")

        except Exception as exc:
            logs.append(f"执行异常: {exc}")
            err_str = str(exc)
            err_code = getattr(exc, "code", "INVALID_VIDEO_REQUEST" if isinstance(exc, VideoRequestError) else "EXCEPTION")
            if request_submitted and err_code not in ("USER_CANCELLED", "VIDEO_ASPECT_MISMATCH", "VIDEO_DURATION_MISMATCH", "VIDEO_OUTPUT_INVALID"):
                err_code = "GEMINI_RESULT_UNCONFIRMED"
            if not request_submitted and any(k in err_str.lower() for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                err_code = "PROFILE_LOCKED"
                err_str = f"Chrome Profile 目录被独占占用 ({profile.name})。通常是因为此前点击【登录】打开的 Chrome 窗口尚未关闭。请先关闭 Chrome 窗口再重试。"
            outcome.update({
                "success": False,
                "pid": os.getpid(),
                "error_code": err_code,
                "error_message": err_str,
                "output_video_path": None,
                "logs": "\n".join(logs)
            })
            return outcome

        finally:
            outcome["submission_possible"] = request_submitted
            with self._sessions_lock:
                self._active_sessions.pop(task.id, None)
            self._execution.control = None

    def _synthesize_tts_file(self, text: str, voice: str, out_path: Path) -> bool:
        """本地配音功能已下线"""
        return False

    def _extract_narration_script(self, text: str) -> str:
        """从 Gemini 多模态输出中智能提取最纯粹的解说文案，去除思考过程与舞台说明、去除 Markdown 格式"""
        import re
        if not text:
            return ""
        clean = text.strip()
        if clean.startswith("Gemini said"):
            clean = clean[len("Gemini said"):].strip()

        extracted_block = None
        for tag in ["【配音解说词】", "[配音解说词]", "配音解说词：", "配音解说词:"]:
            if tag in clean:
                parts = clean.split(tag, 1)
                extracted_block = parts[1].strip()
                break
        else:
            if "配音解说词" in clean:
                parts = clean.split("配音解说词", 1)
                extracted_block = parts[1].lstrip("：:\n ").strip()

        if extracted_block:
            block_lines = []
            for line in extracted_block.split("\n"):
                s_line = line.strip()
                if s_line.startswith("#") or s_line.startswith("===") or s_line.startswith("---"):
                    break
                if s_line:
                    block_lines.append(s_line)
            if block_lines:
                extracted_clean = " ".join(block_lines)
            else:
                extracted_clean = extracted_block
            quotes = re.findall(r'[“]([^”]+)[”]', extracted_clean)
            if quotes:
                script = " ".join(quotes)
            else:
                script = extracted_clean
        else:
            # 没有专门配音解说词标识时，清理 Markdown 标签与元数据
            script = re.sub(r'[*#_`~>\[\]]', '', clean)
            script = re.sub(r'https?://\S+', '', script)

        # 清除括号内的动作/镜头说明
        script = re.sub(r'[\(（][^\)）]*[\)）]', '', script).strip()
        script = script.strip('“"”\' \n\r')
        return script if len(script) >= 2 else text[:200]

    def execute_audio_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """本地配音功能已下线"""
        return {
            "success": False,
            "pid": os.getpid(),
            "error_code": "AUDIO_DISABLED",
            "error_message": "本地配音功能已下线",
            "output_audio_path": None,
            "logs": "本地配音功能已下线并移除"
        }

    def execute_multimodal_interaction(
        self,
        profile: Profile,
        prompt: str,
        mode: str = "chat",
        video_path: Optional[str] = None,
        image_path: Optional[str] = None,
        voice: str = "zh-CN-YunxiNeural",
        aspect_ratio: str = "16:9",
        timeout_sec: int = 120,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Gemini 网页端综合多模态交互工作台：
        - 支持文字对话、多轮交互
        - 支持上传任意本地视频 (.mp4, .mov 等)，让 Gemini 网页端分析画面并生成配音文案与音频
        - 支持 AI 绘画（文生图/图生图），自动提取生成的图片并转存到资产库
        - 稳定 Playwright 驱动；不强杀占用的浏览器，不自动接受协议
        """
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        out_id = uuid.uuid4().hex[:12]
        output_audio_path = self.output_dir / f"gemini_audio_{out_id}.mp3"
        output_images = []
        logs = []

        logs.append(f"[{worker_name}] 启动 Gemini 多模态工作台交互 (Profile: {profile.name}, Mode: {mode})")
        logs.append(f"Prompt: {prompt[:80] if prompt else '（无提示词）'}")

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

        session_id = execution_id or f"chat_{out_id}"
        control = self.begin_task(session_id, timeout_sec)
        prof_lock = get_profile_lock(profile.name)
        request_submitted = False
        acquired = False
        while control.remaining and not acquired:
            if control.cancel_event.is_set():
                break
            acquired = prof_lock.acquire(timeout=min(0.25, control.remaining))
        if not acquired:
            with self._sessions_lock:
                self._active_sessions.pop(session_id, None)
            self._execution.control = None
            return {
                "success": False,
                "error_code": "USER_CANCELLED" if control.cancel_event.is_set() else "PROFILE_BUSY",
                "error_message": "任务已停止，尚未提交网页请求。" if control.cancel_event.is_set() else f"账号 [{profile.name}] 当前正在执行前序对话，请稍候片刻再试。",
                "text": "",
                "audio_url": None,
                "image_urls": [],
                "logs": f"[{worker_name}] 等待账号锁时已取消" if control.cancel_event.is_set() else f"[{worker_name}] 获取账号锁超时"
            }

        try:
            control.check()

            for supplied in (video_path, image_path):
                if supplied and not Path(supplied).is_file():
                    raise GeminiVideoSettingsError("参考素材不存在，请求未提交。", "INVALID_IMAGE_REQUEST")
            has_video = bool(video_path)
            has_image = bool(image_path)
            if has_video:
                logs.append(f"已附加本地参考视频: {Path(video_path).name}")
            if has_image:
                logs.append(f"已附加本地参考图片: {Path(image_path).name}")

            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                launch_args = ["--no-sandbox", "--disable-dev-shm-usage"]
                logs.append("正在拉起独立 Chrome 容器 (Profile 隔离模式)...")
                try:
                    browser = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        channel="chrome",
                        headless=self.headless,
                        args=launch_args, timeout=self._timeout(15000)
                    )
                    with self._sessions_lock:
                        self._active_sessions[session_id].update(browser=browser, profile=profile)
                except ExecutionStopped:
                    raise
                except Exception as launch_exc:
                    lexc_str = str(launch_exc).lower()
                    logs.append(f"拉起浏览器异常: {launch_exc}")
                    if any(k in lexc_str for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                        return {
                            "success": False,
                            "error_code": "PROFILE_LOCKED",
                            "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 释放占用】后重试。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "logs": "\n".join(logs)
                        }
                    raise launch_exc

                try:
                    page = browser.new_page()
                    page.set_default_timeout(5000)
                    page.set_default_navigation_timeout(15000)
                    logs.append("正在导航至 Gemini 主工作区 https://gemini.google.com/app ...")
                    try:
                        page.goto("https://gemini.google.com/app", timeout=self._timeout(15000))
                    except ExecutionStopped:
                        raise
                    except Exception as ge:
                        logs.append(f"页面初次加载提醒: {ge}")

                    self._pause(page, 2.5)
                    self._dismiss_overlays(page, logs)

                    # 记录初始回复节点数量，避免读到历史旧对话
                    initial_resp_count = len(page.query_selector_all('model-response'))

                    # 检查输入框与登录态
                    input_selector = 'rich-textarea div[contenteditable="true"], div.ql-editor[contenteditable="true"], [contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=self._timeout(8000))
                        has_input = True
                    except ExecutionStopped:
                        raise
                    except Exception:
                        has_input = False

                    if not has_input:
                        logs.append("未检测到有效输入框，可能未登录或被弹窗拦截")
                        return {
                            "success": False,
                            "error_code": "AUTH_EXPIRED",
                            "error_message": f"Gemini 网页版未登录或会话已过期 (Profile: {profile.name})。请在顶部点击【🌐 登录网页版】完成 Google 登录授权。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "logs": "\n".join(logs)
                        }

                    input_el = page.query_selector(input_selector)

                    # Upload all requested files, then verify every attachment before Send.
                    if has_video or has_image:
                        upload_btn = page.query_selector('button[aria-label="Upload & tools"], button[aria-label*="Upload"], button[aria-label*="Add"], button:has-text("+")')
                        if upload_btn:
                            upload_btn.click(timeout=self._timeout())
                            self._pause(page, 1)
                        file_input = page.query_selector('input[type="file"]')
                        if has_image and not has_video:
                            image_inputs = page.query_selector_all('input[type="file"][accept*="image"]')
                            file_input = image_inputs[0] if image_inputs else file_input
                        if not file_input:
                            raise GeminiVideoSettingsError("参考素材上传入口不存在，请求未提交，不会丢弃素材。")
                        files = [str(Path(supplied).resolve()) for supplied in (video_path, image_path) if supplied]
                        try:
                            file_input.set_input_files(files, timeout=self._timeout(15000))
                        except ExecutionStopped:
                            raise
                        except Exception as exc:
                            raise GeminiVideoSettingsError("网页未接受全部参考素材，请求未提交，不会丢弃素材。") from exc
                        self._wait_for_attachments(page, len(files), int(has_image))
                        logs.append(f"全部 {len(files)} 个附件上传与预处理已确认完成")

                    # 整理提示词
                    clean_prompt = prompt.strip() if prompt else ""
                    if mode == "image":
                        if not any(k in clean_prompt for k in ["画", "draw", "image", "插画", "图"]):
                            clean_prompt = f"画一张插画：{clean_prompt}"
                    elif has_video and not clean_prompt:
                        clean_prompt = "请深度分析我提供的视频画面内容、镜头运镜与动作节奏，提炼核心看点并给出专业总结。"

                    # 填写内容（使用 execCommand insertText 富文本原子插入，支持多行上下文且避免 \n 触发换行过早发送）
                    if clean_prompt and input_el:
                        input_el.scroll_into_view_if_needed()
                        input_el.click(timeout=self._timeout())
                        self._pause(page, 0.2)
                        inserted = page.evaluate("""(txt) => {
                            const el = document.querySelector('rich-textarea div[contenteditable="true"]');
                            if (el) {
                                el.focus();
                                return document.execCommand('insertText', false, txt);
                            }
                            return false;
                        }""", clean_prompt)
                        if not inserted:
                            page.keyboard.insert_text(clean_prompt)
                        logs.append(f"已输入提示词 ({len(clean_prompt)} 字): {clean_prompt[:60]}...")
                        self._pause(page, 0.5)

                    previous_count = len(page.query_selector_all("model-response"))
                    # 发送请求
                    send_selectors = [
                        'button[aria-label="Send message"]',
                        'button[aria-label*="Send"]',
                        'button[aria-label*="发送"]',
                        '.send-button-container button',
                        '[data-test-id="send-button"]'
                    ]
                    submitted = False
                    for s_sel in send_selectors:
                        s_btn = page.query_selector(s_sel)
                        if s_btn and s_btn.is_visible() and s_btn.is_enabled():
                            request_submitted = True
                            s_btn.click(timeout=self._timeout())
                            submitted = True
                            logs.append("已点击发送按钮提交多模态请求")
                            break
                    if not submitted:
                        request_submitted = True
                        page.keyboard.press("Enter")
                        logs.append("已通过 Enter 键提交多模态请求")

                    self._pause(page, 1)

                    self._dismiss_overlays(page, logs)

                    # 等待模型回复
                    logs.append("等待 Gemini 响应流...")
                    start_t = time.time()
                    generation_started = False
                    captured_text = ""
                    last_txt = ""
                    stable_count = 0

                    while (time.time() - start_t) < max(timeout_sec, 90):
                        self._pause(page, 0.5)
                        self._dismiss_overlays(page, logs)
                        control.check()
                        model_responses = page.query_selector_all("model-response")
                        if len(model_responses) <= previous_count:
                            continue
                        stop_btn = page.query_selector('button[aria-label*="Stop"], button[aria-label*="停止"]')
                        if stop_btn or len(model_responses) > previous_count:
                            generation_started = True

                        elapsed = int(time.time() - start_t)
                        if elapsed % 15 == 0:
                            logs.append(f"[{elapsed}s] 等待回复生成中... (节点数: {len(model_responses)}, 生成标志: {bool(stop_btn)})")

                        if generation_started and not stop_btn and len(model_responses) > 0:
                            last_resp = model_responses[-1]
                            txt = last_resp.inner_text().strip()
                            if txt.startswith("Gemini said"):
                                txt = txt[len("Gemini said"):].strip()
                            if "You stopped this response" in txt:
                                continue
                            has_images = bool(last_resp.query_selector("img"))
                            if len(txt) > 0 or has_images:
                                if not txt and has_images:
                                    txt = f"已为您生成 AI 绘画作品：{prompt or '参考插画'}"
                                if txt == last_txt:
                                    stable_count += 1
                                    if stable_count >= 3:
                                        captured_text = txt
                                        logs.append(f"Gemini 回答已完全稳定输出: {len(captured_text)} 字符 (生成图片: {has_images})")
                                        break
                                else:
                                    stable_count = 0
                                    last_txt = txt

                    if not captured_text:
                        return {
                            "success": False,
                            "error_code": "RESPONSE_TIMEOUT",
                            "error_message": f"Gemini 响应超时（已等待 {int(time.time() - start_t)} 秒），未获取到有效回答。请检查网络或重新提问。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "profile_id": profile.id,
                            "profile_name": profile.name,
                            "logs": "\n".join(logs)
                        }

                    # 检查图片产物 (如果是绘画模式或包含生图)
                    if mode == "image" or any(k in clean_prompt for k in ["画", "生图", "image", "插画"]) or (model_responses and model_responses[-1].query_selector("img")):
                        self._pause(page, 2.5)
                        target_resp = model_responses[-1] if model_responses else page
                        img_elems = target_resp.query_selector_all("img, .generated-image img, .image-container img")
                        for idx, im in enumerate(img_elems):
                            box = im.bounding_box()
                            img_save_path = self.output_dir / f"gemini_img_{out_id}_{idx}.png"
                            saved = False
                            # 优先尝试从原图 Blob / Fetch 提取全分辨率原图数据
                            try:
                                b64_data = page.evaluate("""
                                    async (img) => {
                                        try {
                                            const res = await fetch(img.currentSrc || img.src, {signal: AbortSignal.timeout(15000)});
                                            if (!res.ok) return null;
                                            const blob = await res.blob();
                                            if (blob.size > 32*1024*1024) return null;
                                            return new Promise((resolve) => {
                                                const reader = new FileReader();
                                                reader.onloadend = () => resolve(reader.result);
                                                reader.readAsDataURL(blob);
                                            });
                                        } catch (e) { return null; }
                                    }
                                """, im)
                                if b64_data and "," in b64_data:
                                    raw = base64.b64decode(b64_data.split(",", 1)[1])
                                    if len(raw) > 1000:
                                        with open(img_save_path, "wb") as f:
                                            f.write(raw)
                                        output_images.append(f"/media/outputs/{img_save_path.name}")
                                        logs.append(f"Blob原生提取高清原图成功: {img_save_path.name} (大小: {len(raw)} 字节)")
                                        saved = True
                            except ExecutionStopped:
                                raise
                            except Exception as ie:
                                logs.append(f"Blob提取原图异常，切换截图备选: {ie}")

                            # 备选方案：若 Blob 提取因跨域/限制失败，使用 Playwright 元素精准截图
                            if not saved:
                                try:
                                    im.screenshot(path=str(img_save_path))
                                    if img_save_path.exists() and img_save_path.stat().st_size > 1000:
                                        output_images.append(f"/media/outputs/{img_save_path.name}")
                                        logs.append(f"元素截图提取图片备选成功: {img_save_path.name} (大小: {img_save_path.stat().st_size} 字节)")
                                        saved = True
                                except ExecutionStopped:
                                    raise
                                except Exception as se:
                                    logs.append(f"元素截图提取失败: {se}")

                    if mode == "image" and not output_images:
                        raise GeminiVideoSettingsError("本次回复没有可验证的新图片，不能把文本算作生图成功。", "IMAGE_RESULT_UNCONFIRMED")

                    # 本地配音功能已下线，纯净返回 AI 文本与视觉产物
                    audio_url = None
                    audio_path_str = None
                    final_text = captured_text
                    return {
                        "success": True,
                        "text": final_text,
                        "audio_url": audio_url,
                        "audio_path": audio_path_str,
                        "image_urls": output_images,
                        "profile_id": profile.id,
                        "profile_name": profile.name,
                        "logs": "\n".join(logs)
                    }

                finally:
                    with self._sessions_lock:
                        self._active_sessions.pop(session_id, None)
                    try:
                        browser.close()
                    except ExecutionStopped:
                        raise
                    except Exception:
                        pass
                    logs.append("本次 Chrome 会话已安全退出；未终止其他浏览器或删除锁文件。")

        except Exception as exc:
            logs.append(f"执行 Gemini 多模态交互异常: {exc}")
            code = getattr(exc, "code", "EXCEPTION")
            if request_submitted and code != "USER_CANCELLED":
                code = "IMAGE_RESULT_UNCONFIRMED" if mode == "image" else "GEMINI_RESULT_UNCONFIRMED"
            return {
                "success": False,
                "error_code": code,
                "error_message": str(exc),
                "text": "",
                "audio_url": None,
                "image_urls": [],
                "logs": "\n".join(logs)
            }
        finally:
            with self._sessions_lock:
                self._active_sessions.pop(session_id, None)
            self._execution.control = None
            if acquired:
                prof_lock.release()
