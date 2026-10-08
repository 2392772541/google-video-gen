"""Image output and single-submit regressions, isolated from live providers."""
from pathlib import Path
import pytest
from PIL import Image
from video_farm.image_modes import validate_image_result
from video_farm.models import Task


def test_reference_cannot_be_reported_as_generated_output(tmp_path):
    reference = tmp_path / 'reference.png'
    Image.new('RGB', (1024, 1024), 'navy').save(reference)
    task = Task(id='echo-test', prompt='make a new scene', engine='gemini', task_type='image',
                model='gemini-flash', aspect_ratio='1:1', start_image_path=str(reference))
    attempt = tmp_path / task.id / 'attempt_current'
    attempt.mkdir(parents=True)
    output = attempt / 'generated.png'
    output.write_bytes(reference.read_bytes())
    with pytest.raises(ValueError, match='参考图|输入'):
        validate_image_result({'attempt_dir': str(attempt), 'output_image_paths': [str(output)]}, task, tmp_path)


def test_thumbnail_is_not_a_full_size_generated_output(tmp_path):
    task = Task(id='thumbnail-test', prompt='test', engine='flow', task_type='image',
                model='nano-pro', aspect_ratio='1:1')
    attempt = tmp_path / task.id / 'attempt_current'
    attempt.mkdir(parents=True)
    output = attempt / 'thumbnail.png'
    Image.new('RGB', (64, 64), 'red').save(output)
    with pytest.raises(ValueError, match='尺寸|分辨率|缩略图'):
        validate_image_result({'attempt_dir': str(attempt), 'output_image_paths': [str(output)]}, task, tmp_path)


def test_image_cleanup_keeps_global_slot_until_child_exits(tmp_path, monkeypatch):
    import subprocess
    import threading
    from types import SimpleNamespace
    from video_farm import image_worker as module
    from video_farm.models import Profile
    worker = module.BrowserImageWorker(tmp_path)
    event = threading.Event()
    worker.prepare_task("image_orphan", event)
    slot = SimpleNamespace(acquire=lambda **kw: True, releases=0)
    def release():
        slot.releases += 1
    slot.release = release
    proc = SimpleNamespace(returncode=None, pid=991, poll=lambda: proc.returncode)
    def communicate(timeout=None):
        event.set()
        raise subprocess.TimeoutExpired("image", timeout)
    proc.communicate = communicate
    monkeypatch.setattr(module, "_IMAGE_BROWSER_SLOT", slot)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(worker, "_terminate", lambda p: False)
    task = Task(id="image_orphan", prompt="test", engine="flow", task_type="image", model="nano-pro", aspect_ratio="1:1")
    result = worker.execute_image_task(task, Profile(id="p", name="p"))
    assert result.get("cleanup_confirmed") is False
    assert slot.releases == 0
    assert worker.has_live_execution(task.id)
    proc.returncode = -9
    assert not worker.has_live_execution(task.id)
    assert slot.releases == 1
    assert not worker.has_live_execution(task.id)
    assert slot.releases == 1


def test_image_local_slot_timeout_is_not_an_unknown_remote_result(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from video_farm import image_worker as module
    from video_farm.models import Profile
    worker = module.BrowserImageWorker(tmp_path, timeout_sec=-1)
    monkeypatch.setattr(module, "_IMAGE_BROWSER_SLOT", SimpleNamespace(acquire=lambda **kw: False))
    task = Task(id="slot_busy", prompt="test", engine="flow", task_type="image", model="nano-pro", aspect_ratio="1:1")
    result = worker.execute_image_task(task, Profile(id="p", name="p"))
    assert result["error_code"] == "LOCAL_IMAGE_BUSY"
    assert result["submission_possible"] is False


def test_image_cancel_only_signals_owner(tmp_path, monkeypatch):
    import threading
    from video_farm.image_worker import BrowserImageWorker
    worker = BrowserImageWorker(tmp_path)
    event = threading.Event()
    worker.prepare_task("job", event)
    worker._sessions["job"]["proc"] = object()
    monkeypatch.setattr(worker, "_terminate", lambda *a: pytest.fail("cross-thread termination"))
    assert worker.cancel_task("job")
    assert event.is_set()


def test_image_web_runner_timeout_reports_browser_timeout(tmp_path, monkeypatch):
    import json
    import io
    from contextlib import redirect_stdout
    from video_farm import image_web_runner
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    spec = {"engine": "flow", "model": "nano-pro", "aspect_ratio": "9:16", "prompt": "test",
            "profile_dir": str(tmp_path), "project_id": "p", "profile_name": "prof",
            "output_dir": str(tmp_path), "timeout_sec": 10, "headless": True}
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json.dumps(spec))

    monkeypatch.setattr("sys.argv", ["image_web_runner.py", str(spec_file)])
    monkeypatch.setattr(image_web_runner.NativeImageRun, "run",
                        lambda self: (_ for _ in ()).throw(PlaywrightTimeoutError("waiting for editor")))

    f = io.StringIO()
    with redirect_stdout(f):
        image_web_runner.main()
    output = f.getvalue()
    data = json.loads(output.split("IMAGE_RESULT=")[1])
    assert data["error_code"] == "BROWSER_TIMEOUT"
    assert "网页操作超时" in data["error_message"]
    assert data["submitted"] is False
