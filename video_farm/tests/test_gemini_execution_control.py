import threading
from unittest.mock import MagicMock
import pytest
from video_farm.gemini_worker import GeminiWebWorker, GeminiVideoSettingsError
from video_farm.execution_control import ExecutionStopped


def test_gemini_keeps_the_prepared_stop_event(tmp_path):
    worker=GeminiWebWorker(output_dir=tmp_path)
    event=threading.Event()
    worker.prepare_task('job', event)
    worker.cancel_task('job')
    control=worker.begin_task('job')
    assert control.cancel_event is event
    with pytest.raises(ExecutionStopped):
        control.check()


def test_agreement_requires_user_action_and_is_not_clicked(tmp_path):
    worker=GeminiWebWorker(output_dir=tmp_path)
    button=MagicMock()
    button.is_visible.return_value=True
    page=MagicMock()
    page.query_selector.side_effect=lambda sel: button if 'agree' in sel.lower() else None
    with pytest.raises(GeminiVideoSettingsError) as exc:
        worker._dismiss_overlays(page, [])
    assert exc.value.code=='USER_ACTION_REQUIRED'
    button.click.assert_not_called()
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from video_farm.models import Profile
from video_farm.gemini_worker import GeminiWebWorker
from video_farm.execution_control import ExecutionStopped

@pytest.mark.parametrize('error,code', [(RuntimeError('driver failed'), 'EXCEPTION'), (ExecutionStopped('stop', 'USER_CANCELLED'), 'USER_CANCELLED')])
def test_multimodal_failure_is_returned_and_owned_session_is_released(tmp_path, error, code):
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    profile = Profile(id='profile-test',name='chat-error-test',profile_path=str(tmp_path/'profile'))
    context = MagicMock()
    context.__enter__.side_effect = error
    with patch('playwright.sync_api.sync_playwright', return_value=context):
        result = worker.execute_multimodal_interaction(profile, 'hello', timeout_sec=1)
    assert result['success'] is False
    assert result['error_code'] == code
    assert not worker._active_sessions
    assert getattr(worker._execution, 'control', None) is None


def test_multimodal_busy_profile_leaves_no_session(tmp_path):
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    profile = Profile(id='profile-test',name='busy-test',profile_path=str(tmp_path/'profile'))
    lock = MagicMock()
    lock.acquire.return_value = False
    with patch('video_farm.gemini_worker.get_profile_lock', return_value=lock):
        result = worker.execute_multimodal_interaction(profile,'hello',timeout_sec=0)
    assert result['success'] is False
    assert not worker._active_sessions
    assert getattr(worker._execution, 'control', None) is None
    lock.release.assert_not_called()


def test_cancel_while_waiting_for_chat_profile_is_cancelled_not_busy(tmp_path):
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    event = threading.Event()
    worker.prepare_task('cancel-before-lock', event)
    event.set()
    lock = MagicMock()
    with patch('video_farm.gemini_worker.get_profile_lock', return_value=lock):
        result = worker.execute_multimodal_interaction(
            Profile(id='p', name='cancel-lock', profile_path=str(tmp_path/'p')),
            'hello', timeout_sec=1, execution_id='cancel-before-lock')
    assert result['error_code'] == 'USER_CANCELLED'
    lock.acquire.assert_not_called()
    lock.release.assert_not_called()
    assert not worker._active_sessions


def test_discard_prepared_session_does_not_remove_running_owner(tmp_path):
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    worker.prepare_task('prepared', threading.Event())
    assert worker.discard_prepared_task('prepared') is True
    assert 'prepared' not in worker._active_sessions
    worker.prepare_task('running', threading.Event())
    worker.begin_task('running')
    assert worker.discard_prepared_task('running') is False
    assert 'running' in worker._active_sessions


@pytest.mark.parametrize('kind,preview_count,pending,loaded', [
    ('both', 1, False, True), ('both', 2, True, True),
    ('video', 1, True, True), ('image', 1, False, False),
])
def test_multimodal_never_sends_incomplete_attachments(tmp_path, monkeypatch, kind, preview_count, pending, loaded):
    worker = GeminiWebWorker(output_dir=tmp_path/'out')
    worker._attachment_upload_timeout_sec = 0
    video = tmp_path/'ref.mp4'; video.write_bytes(b'video')
    image = tmp_path/'ref.png'; image.write_bytes(b'image')
    input_box, upload, send = MagicMock(), MagicMock(), MagicMock()
    picture = MagicMock(); picture.evaluate.return_value = loaded
    previews = []
    for _ in range(preview_count):
        chip = MagicMock(); chip.evaluate.return_value = True
        chip.query_selector_all.return_value = [picture]
        previews.append(chip)
    page = MagicMock()
    def query(selector):
        if 'input[type="file"]' in selector: return upload
        if 'Send' in selector or '发送' in selector or 'send-button' in selector: return send
        if 'contenteditable' in selector: return input_box
        return None
    page.query_selector.side_effect = query
    def query_all(selector):
        if selector == 'model-response': return []
        if selector.startswith('input[type="file"]'): return [upload]
        if 'spinner' in selector or 'progressbar' in selector or '.loading' in selector:
            return [MagicMock()] if pending else []
        return previews
    page.query_selector_all.side_effect = query_all
    browser = MagicMock(); browser.new_page.return_value = page
    manager = MagicMock()
    manager.__enter__.return_value.chromium.launch_persistent_context.return_value = browser
    def pause(*args):
        if send.click.called or page.keyboard.press.called:
            raise ExecutionStopped('test stops after unsafe send', 'USER_CANCELLED')
    monkeypatch.setattr(worker, '_pause', pause)
    monkeypatch.setattr(worker, '_dismiss_overlays', lambda *args: None)
    with patch('playwright.sync_api.sync_playwright', return_value=manager):
        result = worker.execute_multimodal_interaction(
            Profile(id='p', name='attachments', profile_path=str(tmp_path/'p')), 'test',
            video_path=str(video) if kind in ('both','video') else None,
            image_path=str(image) if kind in ('both','image') else None, timeout_sec=60)
    assert result['success'] is False
    assert result['error_code'] == 'ATTACHMENT_NOT_READY', result
    send.click.assert_not_called()
    page.keyboard.press.assert_not_called()
    browser.close.assert_called_once()
    assert not worker._active_sessions
