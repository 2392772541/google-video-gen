"""Gemini video regressions: isolated UI doubles, no accounts/network/live DB."""
import base64
import threading
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from video_farm.gemini_worker import GeminiWebWorker
from video_farm.models import Profile, Task


class Element:
    def __init__(self, page, kind, aspect=None):
        self.page, self.kind = page, kind
        self.target_aspect = aspect

    def is_visible(self):
        return True

    def is_enabled(self):
        return not (self.kind == "option" and self.page.option_disabled)

    def get_attribute(self, name):
        if self.kind == "video":
            return "blob:https://gemini.google.com/test" if name == "src" else None
        if name == "aria-label":
            if self.kind == "aspect":
                if self.page.locale == "zh":
                    return "宽高比，" + ("横向 (16:9)" if self.page.aspect == "16:9" else "纵向 (9:16)")
                return "Aspect ratio, " + ("Landscape (16:9)" if self.page.aspect == "16:9" else "Portrait (9:16)")
            if self.kind == "option":
                return (("横向 (16:9)" if self.target_aspect == "16:9" else "纵向 (9:16)")
                        if self.page.locale == "zh" else
                        ("Landscape (16:9)" if self.target_aspect == "16:9" else "Portrait (9:16)"))
        if self.kind == "option":
            return {"role": "menuitemradio", "aria-checked": str(self.page.aspect == self.target_aspect).lower(),
                    "aria-disabled": str(self.page.option_disabled).lower()}.get(name)
        return None

    def inner_text(self):
        if self.kind == "aspect":
            if self.page.locale == "zh":
                return "横向" if self.page.aspect == "16:9" else "纵向"
            return "Landscape" if self.page.aspect == "16:9" else "Portrait"
        return self.get_attribute("aria-label") or ""

    def click(self, **kwargs):
        if self.kind == "aspect":
            self.page.menu_open = True
        elif self.kind == "option":
            if not self.page.click_stuck:
                self.page.aspect = self.target_aspect
            self.page.menu_open = False
        elif self.kind == "send":
            self.page.submitted = True
            self.page.aspect_at_submit = self.page.aspect

    def scroll_into_view_if_needed(self):
        pass

    def fill(self, text):
        self.page.prompt = text

    def set_input_files(self, paths):
        # Uploading a landscape reference may reset Gemini's native aspect.
        self.page.aspect = "16:9"
        self.page.files = list(paths)

    def query_selector_all(self, selector):
        if self.kind == "preview" and selector == "img":
            return [Element(self.page, "image")]
        return []

    def evaluate(self, script, *args):
        return self.page.image_ready


class VideoPage:
    def __init__(self, locale="en", aspect="16:9", button_found=True,
                 option_found=True, click_stuck=False, option_disabled=False,
                 image_ready=True, uploading=False, show_previews=True):
        self.locale, self.aspect = locale, aspect
        self.button_found, self.option_found = button_found, option_found
        self.click_stuck, self.option_disabled = click_stuck, option_disabled
        self.menu_open = self.submitted = False
        self.aspect_at_submit = None
        self.files = []
        self.image_ready, self.uploading, self.show_previews = image_ready, uploading, show_previews
        self.url = "https://gemini.google.com/videos"
        self.keyboard = MagicMock()
        self.keyboard.press.side_effect = self._press

    def _press(self, key):
        if key == "Escape":
            self.menu_open = False
        elif key == "Enter":
            Element(self, "send").click()

    def goto(self, *args, **kwargs):
        pass

    def title(self):
        return "Google Gemini"

    def set_default_timeout(self, *args):
        pass

    def set_default_navigation_timeout(self, *args):
        pass

    def wait_for_timeout(self, *args):
        pass

    def wait_for_selector(self, selector, **kwargs):
        el = self.query_selector(selector)
        if not el:
            raise TimeoutError("control missing")
        return el

    def query_selector(self, selector):
        matches = self.query_selector_all(selector)
        return matches[0] if matches else None

    def query_selector_all(self, selector):
        if selector == "uploader-file-preview":
            return [Element(self, "preview") for _ in self.files] if self.show_previews else []
        if "mat-spinner" in selector:
            return [Element(self, "spinner")] if self.uploading else []
        if selector == "model-response":
            return [Element(self, "response")] if self.submitted else []
        if "contenteditable" in selector:
            return [Element(self, "input")]
        if selector == 'input[type="file"]':
            return [Element(self, "upload")]
        if 'Send message' in selector:
            return [Element(self, "send")]
        if selector in ("video", "model-response video", "model-response:last-child video"):
            return [Element(self, "video")] if self.submitted else []
        if "menuitemradio" in selector:
            return [Element(self, "option", "16:9"), Element(self, "option", "9:16")] if self.menu_open and self.option_found else []
        if "Landscape" in selector or 'button[aria-label*="16:9"]' in selector:
            if self.button_found and (self.locale == "en" or 'aria-label' in selector):
                return [Element(self, "aspect")]
        return []

    def evaluate(self, script, *args):
        return "data:video/mp4;base64," + base64.b64encode(b"\0" * 30000).decode()


def run_task(tmp_path, page, aspect="9:16", actual=(720, 1280), reference=False, actual_duration=8):
    worker = GeminiWebWorker(output_dir=tmp_path / "outputs", timeout_sec=1)
    worker._attachment_upload_timeout_sec = 0  # immediate deterministic UI readiness check
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(exist_ok=True)
    profile = Profile(id="isolated-profile", name="isolated", profile_path=str(profile_dir))
    task = Task(id="isolated-gemini-test", prompt="Video test", engine="gemini",
                aspect_ratio=aspect, duration_sec=8, model="auto")
    if reference:
        image = tmp_path / "reference.png"
        Image.new("RGB", (64, 36), "blue").save(image)
        task.start_image_path = str(image)
    browser = MagicMock()
    browser.new_page.return_value = page
    driver = MagicMock()
    driver.chromium.launch_persistent_context.return_value = browser
    context = MagicMock()
    context.__enter__.return_value = driver
    capture = MagicMock()
    capture.isOpened.return_value = True
    # OpenCV property IDs: frame width=3, height=4, fps=5, frame count=7.
    capture.get.side_effect = lambda prop: {3: actual[0], 4: actual[1], 5: 30, 7: 30 * actual_duration}.get(prop, 0)
    with patch("playwright.sync_api.sync_playwright", return_value=context), \
         patch.object(worker, "_pause", side_effect=lambda *args: worker._execution.control.check()), \
         patch("cv2.VideoCapture", return_value=capture):
        result = worker._execute_browser_task(task, profile)
    if driver.chromium.launch_persistent_context.called:
        browser.close.assert_called_once()
    else:
        browser.close.assert_not_called()
    return result


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_native_radio_menu_selects_requested_portrait(tmp_path, locale):
    page = VideoPage(locale=locale)
    result = run_task(tmp_path, page)
    assert page.aspect_at_submit == "9:16"
    assert result["success"] is True


@pytest.mark.parametrize("settings", [
    {"button_found": False}, {"option_found": False},
    {"click_stuck": True}, {"option_disabled": True},
])
def test_unverified_aspect_never_submits(tmp_path, settings):
    page = VideoPage(**settings)
    result = run_task(tmp_path, page)
    assert page.submitted is False
    assert result["success"] is False
    assert result["error_code"] == "UNSUPPORTED_FEATURE"


def test_square_request_is_not_silently_treated_as_portrait(tmp_path):
    page = VideoPage()
    result = run_task(tmp_path, page, aspect="1:1")
    assert page.submitted is False
    assert result["error_code"] == "INVALID_VIDEO_REQUEST"


def test_reference_upload_cannot_override_requested_portrait(tmp_path):
    page = VideoPage(aspect="9:16")
    result = run_task(tmp_path, page, reference=True)
    assert page.aspect_at_submit == "9:16"
    assert result["success"] is True


def test_landscape_output_is_not_reported_as_portrait_success(tmp_path):
    page = VideoPage(aspect="9:16")
    result = run_task(tmp_path, page, actual=(1280, 720))
    assert result["success"] is False
    assert result["error_code"] == "VIDEO_ASPECT_MISMATCH"
    assert "1280" in result["error_message"]


def test_correct_landscape_passes_with_requested_duration(tmp_path):
    page = VideoPage(aspect="16:9")
    result = run_task(tmp_path, page, aspect="16:9", actual=(1280, 720))
    assert result["success"] is True
    assert "8.0" in result["logs"]


def test_wrong_duration_is_not_reported_as_requested_success(tmp_path):
    page = VideoPage(aspect="16:9")
    result = run_task(tmp_path, page, aspect="16:9", actual=(1280, 720), actual_duration=10)
    assert page.submitted is True
    assert result["success"] is False
    assert result["error_code"] == "VIDEO_DURATION_MISMATCH"
    assert "8" in result["error_message"] and "10.0" in result["error_message"]


def test_unreadable_output_is_not_success(tmp_path):
    page = VideoPage(aspect="9:16")
    result = run_task(tmp_path, page, actual=(0, 0))
    assert result["success"] is False
    assert result["error_code"] == "VIDEO_OUTPUT_INVALID"


@pytest.mark.parametrize("code", ["VIDEO_ASPECT_MISMATCH", "VIDEO_OUTPUT_INVALID", "VIDEO_DURATION_MISMATCH"])
def test_output_failure_is_terminal_even_with_quota_words(code):
    from video_farm.scheduler import classify_failure

    category, message, cooldown, count_retry = classify_failure(
        code, "Gemini output failed validation", "Generation spent credits; quota and timeout diagnostics"
    )
    assert category == code
    assert "Gemini output failed validation" in message
    assert cooldown == 0
    assert count_retry is False


@pytest.mark.parametrize("code", ["VIDEO_ASPECT_MISMATCH", "VIDEO_OUTPUT_INVALID", "VIDEO_DURATION_MISMATCH"])
def test_scheduler_never_requeues_failed_gemini_output(tmp_path, code):
    from video_farm.scheduler import VideoScheduler

    # No constructor: no live DB, thread pool, browser or recovery hooks.
    scheduler = VideoScheduler.__new__(VideoScheduler)
    scheduler.db_path = tmp_path / "never-opened.db"
    scheduler.lock = threading.Lock()
    scheduler.cancelled_task_ids = set()
    scheduler.active_tasks = {"isolated-gemini-test": {}}
    scheduler.gemini_worker = MagicMock()
    scheduler.gemini_worker.execute_task.return_value = {
        "success": False, "error_code": code,
        "error_message": "Gemini output failed validation", "logs": "already generated",
    }
    task = Task(id="isolated-gemini-test", prompt="test", engine="gemini", status="running")
    profile = Profile(id="isolated-profile", name="isolated")
    with patch("video_farm.scheduler.db") as database:
        connection = database.get_db_connection.return_value
        connection.execute.return_value.fetchone.return_value = {"status": "running"}
        scheduler.process_task_execution(task, profile)
        database.update_task_status.assert_called_once()
        assert database.update_task_status.call_args.kwargs["status"] == "failed"
        assert database.update_task_status.call_args.kwargs["error_code"] == code
        assert database.update_profile_status.call_args.kwargs["status"] == "idle"
        assert all("UPDATE" not in str(call.args[0]).upper()
                   for call in connection.execute.call_args_list)
        assert "RETRY_SCHEDULED" not in str(database.log_task_event.call_args_list)
    scheduler.gemini_worker.execute_task.assert_called_once()
    assert not scheduler.active_tasks
    assert not scheduler.db_path.exists()


@pytest.mark.parametrize("actual", [
    (float("nan"), 1280, 30, 300), (720, 1280, float("nan"), 300),
    (720, 1280, 30, float("inf")), (None, 1280, 30, 300),
])
def test_invalid_media_metadata_is_terminal_and_releases_capture(tmp_path, actual):
    from video_farm.gemini_worker import GeminiVideoSettingsError

    capture = MagicMock()
    capture.isOpened.return_value = True
    capture.get.side_effect = lambda prop: dict(zip((3, 4, 5, 7), actual)).get(prop, 0)
    with patch("cv2.VideoCapture", return_value=capture):
        with pytest.raises(GeminiVideoSettingsError) as error:
            GeminiWebWorker._validate_video_output(tmp_path / "test.mp4", "9:16", 8, [])
    assert error.value.code == "VIDEO_OUTPUT_INVALID"
    capture.release.assert_called_once()


def test_unopened_media_is_terminal_and_releases_capture(tmp_path):
    from video_farm.gemini_worker import GeminiVideoSettingsError

    capture = MagicMock()
    capture.isOpened.return_value = False
    with patch("cv2.VideoCapture", return_value=capture):
        with pytest.raises(GeminiVideoSettingsError) as error:
            GeminiWebWorker._validate_video_output(tmp_path / "test.mp4", "9:16", 8, [])
    assert error.value.code == "VIDEO_OUTPUT_INVALID"
    capture.release.assert_called_once()


@pytest.mark.parametrize("aspect,actual", [("9:16", (720, 1280)), ("16:9", (1280, 720))])
def test_matching_aspect_does_not_open_menu(tmp_path, aspect, actual):
    page = VideoPage(aspect=aspect)
    with patch.object(Element, "click", autospec=True, side_effect=Element.click) as click:
        result = run_task(tmp_path, page, aspect=aspect, actual=actual)
    assert result["success"] is True
    assert all(call.args[0].kind not in ("aspect", "option") for call in click.call_args_list)


@pytest.mark.parametrize("locale", ["en", "zh"])
def test_native_radio_menu_switches_portrait_back_to_landscape(tmp_path, locale):
    page = VideoPage(locale=locale, aspect="9:16")
    result = run_task(tmp_path, page, aspect="16:9", actual=(1280, 720))
    assert result["success"] is True
    assert page.aspect_at_submit == "16:9"


@pytest.mark.parametrize("settings", [
    {"image_ready": False}, {"uploading": True}, {"show_previews": False},
])
def test_incomplete_or_broken_reference_never_submits(tmp_path, settings):
    page = VideoPage(**settings)
    result = run_task(tmp_path, page, reference=True)
    assert page.files
    assert not page.submitted
    assert result["success"] is False
    assert result["error_code"] == "ATTACHMENT_NOT_READY"
    assert result["submission_possible"] is False
