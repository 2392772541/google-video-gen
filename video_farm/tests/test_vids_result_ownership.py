import threading
from unittest.mock import MagicMock
import pytest
from video_farm.vids_worker import VidsWorker


def test_signed_history_url_cannot_become_new_result():
    worker = VidsWorker
    original = 'https://drive.google.com/videoplayback?id=OLD&expire=1&sig=A'
    refreshed = 'https://drive.google.com/videoplayback?id=OLD&expire=2&sig=B'
    assert worker.media_identity(original) == worker.media_identity(refreshed)
    assert worker.media_identity(original) != worker.media_identity(refreshed.replace('OLD', 'NEW'))


def test_result_must_belong_to_current_sidebar_and_not_baseline(tmp_path):
    worker = VidsWorker(output_dir=tmp_path)
    old = 'https://drive.google.com/videoplayback?id=OLD&sig=A'
    baseline = {worker.media_identity(old)}
    rows = [
        {'src': old.replace('sig=A','sig=B'), 'sidebar': True, 'ready': True},
        {'src': 'https://drive.google.com/videoplayback?id=OTHER', 'sidebar': False, 'ready': True},
        {'src': 'https://gstatic.com/demo.mp4', 'sidebar': True, 'ready': True},
    ]
    assert worker.pick_current_media(rows, baseline) is None
    new = {'src': 'https://drive.google.com/videoplayback?id=NEW', 'sidebar': True, 'ready': True}
    assert worker.pick_current_media(rows+[new], baseline) == new['src']


def test_begin_session_keeps_prepared_cancel_event(tmp_path):
    worker = VidsWorker(output_dir=tmp_path)
    event = threading.Event()
    worker.prepare_task('job', event)
    worker.cancel_task('job')
    control = worker.begin_task('job')
    assert control.cancel_event is event
    with pytest.raises(Exception, match='取消'):
        control.check()


def test_total_deadline_and_interruptible_wait():
    from video_farm.execution_control import ExecutionControl, ExecutionStopped
    event = threading.Event()
    control = ExecutionControl(event, timeout_sec=0)
    with pytest.raises(ExecutionStopped, match='超时'):
        control.check()
    control = ExecutionControl(event, timeout_sec=2)
    event.set()
    with pytest.raises(ExecutionStopped, match='取消'):
        control.pause(None, 20)


def test_submitted_vids_timeout_never_auto_retries(tmp_path):
    from video_farm.scheduler import classify_failure
    category, message, _, retry = classify_failure('VIDS_RESULT_UNCONFIRMED', 'cloud wait timeout', '')
    assert category == 'VIDS_RESULT_UNCONFIRMED'
    assert not retry
    assert '重试' in message
