"""Native, single-submit Flow/Gemini image automation in a task-owned process.

No private API reconstruction, browser-wide cleanup, protocol acceptance or
silent model fallback. Only newly generated media is downloaded.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from .execution_control import ExecutionControl, ExecutionStopped
from .image_modes import IMAGE_MODELS, validate_image_settings, validate_image_file


class ImageWebError(RuntimeError):
    def __init__(self, message, code="UNSUPPORTED_FEATURE"):
        super().__init__(message)
        self.code = code


def profile_in_use(profile_dir):
    """Check exact browser profile ownership. Never terminate another browser."""
    import psutil
    target = os.path.normcase(str(Path(profile_dir).resolve()))
    for process in psutil.process_iter(["name", "cmdline"]):
        try:
            if not any(browser in (process.info["name"] or "").lower()
                       for browser in ("chrome", "chromium", "msedge")):
                continue
            args = process.info["cmdline"] or []
            for index, arg in enumerate(args):
                value = arg.split("=", 1)[1] if arg.startswith("--user-data-dir=") else (
                    args[index + 1] if arg == "--user-data-dir" and index + 1 < len(args) else None)
                if value and os.path.normcase(str(Path(value.strip('"')).resolve())) == target:
                    return True
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
            continue
    return False


def flow_project(spec):
    project = spec.get("project_id") or ""
    if not project:
        database = Path(os.environ.get("LOCALAPPDATA", "")) / "ffroliva/gflow-cli/gflow.db"
        if database.is_file():
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as conn:
                row = conn.execute("SELECT flow_project_id FROM projects WHERE profile_name=? "
                                   "AND flow_project_id IS NOT NULL ORDER BY rowid DESC LIMIT 1",
                                   (spec.get("profile_name", ""),)).fetchone()
                project = row[0] if row else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project):
        raise ImageWebError("所选账号尚无 Flow 工程；请先在账号页面登录并初始化工程。", "PROJECT_INIT_REQUIRED")
    return project


class NativeImageRun:
    def __init__(self, spec):
        self.spec = spec
        self.engine, self.model, self.aspect = validate_image_settings(
            spec["engine"], spec["model"], spec["aspect_ratio"])
        self.directory = Path(spec["output_dir"]).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.control = ExecutionControl(timeout_sec=spec.get("timeout_sec", 355))
        self.submitted = False
        self.page = None
        self.logs = []
        self.started = time.monotonic()

    def log(self, message):
        entry = f"[{time.monotonic() - self.started:.1f}s] {message}"
        self.logs.append(entry)
        print(entry, flush=True)

    def click(self, locator):
        locator.click(timeout=self.control.timeout_ms(12000))

    def wait(self, predicate, message, seconds=45):
        until = time.monotonic() + min(seconds, self.control.remaining)
        while time.monotonic() < until:
            self.guard()
            if predicate():
                return
            self.control.pause(self.page, .4)
        self.control.check()
        raise ImageWebError(message)

    def guard(self):
        self.control.check()
        if "accounts.google.com" in self.page.url:
            raise ImageWebError("所选账号未登录，请在原网页完成登录。", "AUTH_EXPIRED")
        blockers = self.page.locator('iframe[src*="recaptcha"], iframe[src*="challenge"]')
        if any(el.is_visible() for el in blockers.all()):
            raise ImageWebError("网页要求人机验证，请手动处理；不会自动绕过。", "USER_ACTION_REQUIRED")
        for name in (r"^(同意|我同意|I agree|Agree|Accept terms)$",):
            buttons = self.page.get_by_role("button", name=re.compile(name, re.I))
            if any(button.is_visible() for button in buttons.all()):
                raise ImageWebError("网页要求同意协议，请先手动处理。", "USER_ACTION_REQUIRED")

    def screenshot(self, name):
        if self.page:
            try:
                self.page.screenshot(path=str(self.directory / name), timeout=self.control.timeout_ms(4000))
            except Exception:
                pass

    def choose_flow(self):
        page = self.page
        page.goto("https://flow.google.com/project/" + flow_project(self.spec),
                  wait_until="domcontentloaded", timeout=self.control.timeout_ms(45000))
        editor = page.locator('div.ProseMirror[contenteditable="true"]')
        self.wait(lambda: editor.count() == 1 and editor.is_visible(), "Flow 提示框未就绪", 45)
        agent = page.get_by_role("button", name=re.compile(r"^(智能体|Agent)$", re.I))
        if agent.count() and agent.get_attribute("aria-pressed") == "true":
            self.click(agent)
        self.click(page.get_by_role("button", name=re.compile(r"^(设置触发器|Settings trigger)$", re.I)))
        image_mode = page.get_by_role("radio", name=re.compile(r"^(图片|Image|Images)$", re.I))
        self.click(image_mode)
        self.wait(lambda: image_mode.get_attribute("aria-checked") == "true", "Flow 未确认图片模式", 10)
        aspect = page.get_by_role("radio", name=self.aspect, exact=True)
        self.click(aspect)
        self.wait(lambda: aspect.get_attribute("aria-checked") == "true", "Flow 画幅未确认", 10)
        # The same menu trigger is renamed to the chosen model on some cohorts.
        model_labels = "|".join(re.escape(value) for value in IMAGE_MODELS["flow"].values())
        trigger_names = re.compile(r"^(选择模型系列|Select model family|(?:🍌\s*)?(?:" + model_labels + r"))$", re.I)
        trigger = page.get_by_role("button", name=trigger_names)
        self.wait(lambda: trigger.count() == 1 and trigger.is_visible(), "Flow 模型选择入口未就绪", 10)
        self.click(trigger)
        label = IMAGE_MODELS["flow"][self.model]
        item = page.get_by_role("menuitem", name=re.compile(r"^(?:🍌\s*)?" + re.escape(label) + r"$"))
        if item.count() != 1 or not item.is_enabled():
            raise ImageWebError(f"当前 Flow 账号不提供 {label}，不会替换成其他型号。")
        self.click(item)
        selected = page.get_by_role("button", name=trigger_names)
        chosen = re.compile(r"^(?:🍌\s*)?" + re.escape(label) + r"$", re.I)
        self.wait(lambda: selected.count() == 1 and selected.is_visible()
                  and chosen.fullmatch(selected.inner_text().strip()), "Flow 模型选择未确认", 10)
        count = page.get_by_role("radio", name="x1", exact=True)
        self.click(count)
        self.wait(lambda: count.get_attribute("aria-checked") == "true", "Flow 图片数量未确认", 10)
        editor.press("Escape", timeout=self.control.timeout_ms())
        editor.fill(self.spec["prompt"], timeout=self.control.timeout_ms())
        self.guard()
        if self.spec.get("reference"):
            self.attach_flow(editor)
        self.log(f"Flow 设置已确认：{label} / {self.aspect} / x1")
        return editor

    @staticmethod
    def reference_ready(composer):
        images = composer.locator("img")
        pending = composer.locator('mat-spinner, [role="progressbar"], .loading')
        return (images.count() > 0 and pending.count() == 0
                and images.evaluate_all("els => els.every(e => e.complete && e.naturalWidth > 0)"))

    def attach_flow(self, editor):
        page = self.page
        before = set(page.locator('img[data-media-id]').evaluate_all("els => els.map(e => e.dataset.mediaId)"))
        self.click(page.get_by_role("button", name=re.compile(r"^(在提示框中添加素材|Add assets to prompt)$", re.I)))
        upload = page.get_by_role("button", name=re.compile(r"^(上传媒体内容|Upload media)$", re.I))
        with page.expect_file_chooser(timeout=self.control.timeout_ms(10000)) as chooser:
            self.click(upload)
        chooser.value.set_files(self.spec["reference"], timeout=self.control.timeout_ms(15000))
        # Some cohorts attach immediately; others add an uploaded asset to the drawer.
        composer = page.locator("flow-base-prompt-box")
        def attached():
            return self.reference_ready(composer)
        until = time.monotonic() + min(45, self.control.remaining)
        while time.monotonic() < until and not attached():
            self.guard()
            options = page.get_by_role("option")
            for option in options.all():
                ids = option.locator('img[data-media-id]').evaluate_all("els => els.map(e => e.dataset.mediaId)")
                if ids and any(media_id not in before for media_id in ids):
                    self.click(option)
                    add = page.get_by_role("button", name=re.compile(r"^(添加到提示|Add to prompt)$", re.I))
                    if add.count() and add.is_visible():
                        self.click(add)
                    break
            self.control.pause(page, .4)
        self.wait(attached, "Flow 参考图未附着到本次提示；已阻止纯文生图提交", 5)
        self.log("Flow 原生参考图上传及附着已确认")

    def flow(self):
        page = self.page
        self.choose_flow()
        before = set(page.locator('img[data-media-id]').evaluate_all("els => els.map(e => e.dataset.mediaId)"))
        button = page.get_by_role("button", name=re.compile(r"^(开始生成|Start generation|Generate)$", re.I))
        self.wait(button.is_enabled, "Flow 生成按钮不可用", 25)
        self.screenshot("settings.png")
        self.submitted = True  # A click error is uncertain; never automatically click twice.
        self.click(button)
        self.log("Flow 原生生成已提交一次，等待本次新媒体")
        new_ids = []
        while self.control.remaining:
            self.guard()
            new_ids = page.locator('img[data-media-id]').evaluate_all("els => els.map(e => e.dataset.mediaId)")
            new_ids = list(dict.fromkeys(media_id for media_id in new_ids if media_id not in before))
            # Reference upload was captured in 'before', so it cannot become the result.
            ready = [media_id for media_id in new_ids if page.locator(f'img[data-media-id="{media_id}"]').first.evaluate("e => e.complete && e.naturalWidth > 32")]
            if ready:
                new_ids = ready
                break
            self.control.pause(page, 1)
        self.control.check()
        if len(new_ids) != 1:
            raise ImageWebError("无法唯一确认本次 Flow 新图片；请检查工程，不自动重发。", "IMAGE_RESULT_UNCONFIRMED")
        image = page.locator(f'img[data-media-id="{new_ids[0]}"]').first
        image.dblclick(timeout=self.control.timeout_ms(12000))
        download = page.get_by_role("button", name=re.compile(r"^(下载媒体内容|Download media)$", re.I))
        self.wait(lambda: download.count() == 1 and download.is_visible(), "Flow 下载控件未就绪", 15)
        self.click(download)
        original = page.get_by_role("menuitem", name=re.compile(r"(?:1K.*(?:原始|Original)|(?:原始|Original).*1K)", re.I))
        if not original.count():
            original = page.get_by_role("button", name=re.compile(r"(?:1K.*(?:原始|Original)|(?:原始|Original).*1K)", re.I))
        if original.count() != 1:
            raise ImageWebError("未找到 Flow 原始尺寸下载选项；不调用高清重塑。", "IMAGE_RESULT_UNCONFIRMED")
        with page.expect_download(timeout=self.control.timeout_ms(45000)) as event:
            self.click(original)
        return [self.save(event.value, 1)]

    def choose_gemini(self):
        page = self.page
        # Always create a clean chat; prior responses cannot satisfy this request.
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=self.control.timeout_ms(45000))
        editor = page.locator('div.ql-editor[contenteditable="true"]')
        self.wait(lambda: editor.count() == 1 and editor.is_visible(), "Gemini 提示框未就绪", 45)
        image_chip = page.get_by_role("button", name=re.compile(r"取消选择.*图片|Deselect.*image", re.I))
        if not image_chip.count():
            self.click(page.get_by_role("button", name=re.compile(r"^(上传和工具|Upload.*tools)$", re.I)))
            image_menu = page.get_by_role("menuitemcheckbox", name=re.compile(r"^(制作图片|Create images)$", re.I))
            if image_menu.count() != 1:
                raise ImageWebError("当前 Gemini 账号不提供网页制作图片模式。")
            self.click(image_menu)
        self.wait(lambda: image_chip.count() == 1 and image_chip.is_visible(), "Gemini 图片模式未确认", 10)
        selector = page.get_by_role("button", name=re.compile(r"打开模式选择器|Open mode picker", re.I))
        self.click(selector)
        label = IMAGE_MODELS["gemini"][self.model]
        patterns = {"gemini-flash": r"3\.8 Flash(?!-Lite)", "gemini-flash-lite": r"3\.5 Flash-Lite",
                    "gemini-pro": r"3\.1 Pro", "gemini-thinking": r"扩展思考|Extended thinking"}
        item = page.get_by_role("menuitem", name=re.compile(patterns[self.model], re.I))
        if item.count() != 1 or not item.is_enabled():
            raise ImageWebError(f"当前 Gemini 账号不提供 {label}；不切换其他模式。")
        self.click(item)
        # The picker often displays short labels; Flash must not match Flash-Lite.
        selected_patterns = {
            "gemini-flash": r"\bFlash(?![-\s]*Lite)\b",
            "gemini-flash-lite": r"\bFlash[-\s]*Lite\b",
            "gemini-pro": r"\bPro\b",
            "gemini-thinking": r"(?:扩展)?思考|\b(?:Extended\s+)?thinking\b",
        }
        self.wait(lambda: re.search(selected_patterns[self.model],
                  selector.get_attribute("aria-label") or selector.inner_text(), re.I) is not None,
                  "Gemini 网页模式未确认", 10)
        ratio = page.get_by_role("button", name=re.compile(r"^宽高比|^Aspect ratio", re.I))
        if ratio.count() != 1:
            raise ImageWebError("Gemini 当前图片模式未提供画幅选择，已阻止不确定提交。")
        self.click(ratio)
        option = page.get_by_role("menuitemradio", name=self.aspect, exact=True)
        if option.count() != 1:
            raise ImageWebError("Gemini 当前账号不提供所选画幅。")
        self.click(option)
        self.wait(lambda: self.aspect in (ratio.get_attribute("aria-label") or ratio.inner_text()), "Gemini 画幅未确认", 10)
        editor.fill(self.spec["prompt"], timeout=self.control.timeout_ms())
        if self.spec.get("reference"):
            self.click(page.get_by_role("button", name=re.compile(r"^(上传和工具|Upload.*tools)$", re.I)))
            with page.expect_file_chooser(timeout=self.control.timeout_ms(10000)) as chooser:
                self.click(page.get_by_role("menuitem", name=re.compile(r"^上传文件|^Upload files", re.I)))
            chooser.value.set_files(self.spec["reference"], timeout=self.control.timeout_ms(15000))
            composer = page.locator("input-area-v2")
            self.wait(lambda: self.reference_ready(composer), "Gemini 参考图未加载；已阻止纯文生图提交", 45)
            self.log("Gemini 原生参考图预览已确认")
        self.guard()
        self.log(f"Gemini 制作图片模式已确认：{label} / {self.aspect}")
        return editor

    def gemini(self):
        page = self.page
        editor = self.choose_gemini()
        count = page.locator("model-response").count()
        self.screenshot("settings.png")
        self.submitted = True
        editor.press("Enter", timeout=self.control.timeout_ms(10000))
        self.log("Gemini 原生图片提示已提交一次，等待本轮新增回复")
        response = None
        while self.control.remaining:
            self.guard()
            responses = page.locator("model-response")
            if responses.count() > count:
                candidate = responses.nth(count)
                images = candidate.locator('img[alt*="AI 生成"], img[alt*="AI generated"], img[alt*="AI-generated"]')
                if images.count() and images.first.evaluate("e => e.complete && e.naturalWidth > 32"):
                    response = candidate
                    break
                # Explicit refusal is a terminal result, not an excuse to resubmit.
                text = candidate.inner_text(timeout=self.control.timeout_ms())
                if re.search(r"无法生成|不能生成|can't generate|unable to generate|reached.*limit|已达到.*上限", text, re.I):
                    raise ImageWebError("Gemini 本轮回复未生成图片（限制或拒绝）；请检查网页。", "IMAGE_RESULT_UNCONFIRMED")
            self.control.pause(page, 1)
        self.control.check()
        if response is None:
            raise ImageWebError("Gemini 未确认本次图片，不自动重发。", "IMAGE_RESULT_UNCONFIRMED")
        buttons = response.get_by_role("button", name=re.compile(r"下载完整尺寸的图片|Download full.*image", re.I))
        self.wait(lambda: buttons.count() > 0, "Gemini 本轮回复没有原始尺寸下载控件", 15)
        # Download each picture from this response only, not the page's historical buttons.
        outputs = []
        for index in range(buttons.count()):
            with page.expect_download(timeout=self.control.timeout_ms(45000)) as event:
                self.click(buttons.nth(index))
            outputs.append(self.save(event.value, index + 1))
        return outputs

    def save(self, download, index):
        suffix = Path(download.suggested_filename).suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
            raise ImageWebError("原生下载未返回图像文件。", "IMAGE_OUTPUT_INVALID")
        target = self.directory / f"image_{index}{suffix}"
        download.save_as(str(target))
        try:
            width, height = validate_image_file(target, self.aspect, generated=True)
        except ValueError as exc:
            raise ImageWebError(str(exc), "IMAGE_OUTPUT_INVALID") from exc
        self.log(f"本轮图片已下载核验：{width}×{height}")
        return str(target)

    def run(self):
        from playwright.sync_api import sync_playwright
        from gflow_cli.profile_lease import ProfileLease
        profile = Path(self.spec["profile_dir"]).resolve()
        if not profile.is_dir():
            raise ImageWebError("所选账号浏览器目录不存在，请先完成网页登录。", "AUTH_EXPIRED")
        if profile_in_use(profile):
            raise ImageWebError("所选账号浏览器正在使用中；不关闭用户窗口。", "PROFILE_LOCKED")
        with ProfileLease(profile), sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile), channel="chrome", headless=self.spec.get("headless", True),
                accept_downloads=True, viewport={"width": 1280, "height": 860},
                timeout=self.control.timeout_ms(30000),
                args=["--disable-dev-shm-usage", "--disable-background-networking"])
            try:
                self.page = next((page for page in context.pages
                                  if page.url in ("about:blank", "chrome://newtab/")), None)
                if self.page is None:
                    self.page = context.new_page()
                self.page.set_default_timeout(12000)
                outputs = self.flow() if self.engine == "flow" else self.gemini()
                self.screenshot("result.png")
                return {"success": True, "engine": self.engine, "model": self.model,
                        "output_image_paths": outputs, "attempt_dir": str(self.directory),
                        "result_url": self.page.url, "logs": "\n".join(self.logs)}
            except Exception:
                self.screenshot("failure.png")
                raise
            finally:
                context.close()


def main():
    run = None
    try:
        spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        run = NativeImageRun(spec)
        result = run.run()
    except Exception as exc:
        # Do not print Playwright call logs containing signed URLs or account data.
        code = getattr(exc, "code", None)
        if run and run.submitted and code not in ("USER_ACTION_REQUIRED", "IMAGE_OUTPUT_INVALID"):
            code = "IMAGE_RESULT_UNCONFIRMED"
        elif not code:
            code = "PROFILE_LOCKED" if type(exc).__name__ == "ProfileLockedError" else "INVALID_IMAGE_REQUEST" if isinstance(exc, ValueError) else "UNSUPPORTED_FEATURE"
        message = str(exc).split("Call log:")[0].split("\n")[0][:400] if isinstance(exc, (ImageWebError, ExecutionStopped, ValueError)) else f"原生网页执行未完成：{type(exc).__name__}。请查看本次 failure.png；不会自动重复生成。"
        result = {"success": False, "error_code": code, "error_message": message,
                  "output_image_paths": [], "submitted": bool(run and run.submitted),
                  "logs": "\n".join(run.logs) if run else ""}
    print("IMAGE_RESULT=" + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
