"""Flow logs go to files, never PIPE/communicate buffers in the service."""
import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from video_farm.models import Profile, Task
from video_farm.worker import VideoWorker


class LogProcess:
    pid = 123
    returncode = 0

    def __init__(self, streams, event=None):
        self.streams = streams
        self.event = event

    def wait(self, timeout=None):
        if self.event:
            self.streams[1].write(b"progress before stop\n")
            self.streams[1].flush()
            self.event.set()
            raise subprocess.TimeoutExpired("fixture", timeout)
        return self.returncode

    def cleanup(self):
        self.streams[1].write(b"cleanup-marker\n")
        self.streams[1].flush()
        return True

    def is_alive(self):
        return False


def make_worker(tmp_path):
    worker = VideoWorker(gflow_dir=tmp_path, output_dir=tmp_path / "outputs")
    worker._ensure_profile_marker = Mock()
    return worker


def test_flow_spools_large_stdout_and_keeps_final_receipt(tmp_path):
    worker = make_worker(tmp_path)
    handles = []

    def launch(command, **kwargs):
        out, err = kwargs["stdout"], kwargs["stderr"]
        handles.extend((out, err))
        assert out != subprocess.PIPE and err != subprocess.PIPE
        assert Path(out.name).parent == Path(command[command.index("--out-dir") + 1])
        for _ in range(32):
            out.write(b"x" * (64 * 1024))
        video = Path(out.name).parent / "result.mp4"
        video.write_bytes(b"v" * 60000)
        out.write(b"\n" + json.dumps({"status": "ok", "succeeded": True,
                                       "local_path": str(video)}).encode() + b"\n")
        out.flush()
        return LogProcess((out, err))

    with patch.object(worker, "_launch_cli", side_effect=launch), patch.object(worker, "_validate_output"):
        result = worker.execute_task(Task(id="bounded-flow", project_id="p", prompt="test"), Profile(id="p", name="p"))
    assert result["success"], result
    assert "cleanup-marker" in result["logs"]
    assert "truncated" in result["logs"].lower()
    assert len(result["logs"]) < 25000
    assert all(handle.closed for handle in handles)
    assert Path(result["output_video_path"]).is_file()


def test_flow_stop_retains_progress_log_and_closes_spool_handles(tmp_path):
    worker = make_worker(tmp_path)
    event = threading.Event()
    worker.prepare_task("stopped-flow-log", event)
    handles = []

    def launch(command, **kwargs):
        handles.extend((kwargs["stdout"], kwargs["stderr"]))
        process = LogProcess(tuple(handles), event)
        process.returncode = None
        return process

    with patch.object(worker, "_launch_cli", side_effect=launch):
        result = worker.execute_task(Task(id="stopped-flow-log", project_id="p", prompt="test"), Profile(id="p", name="p"))
    assert result["error_code"] == "USER_CANCELLED", result
    assert "progress before stop" in result["logs"]
    assert "cleanup-marker" in result["logs"]
    assert all(handle.closed for handle in handles)


def test_launch_passes_file_handles_to_owned_process_without_text_pipe(tmp_path):
    worker = make_worker(tmp_path)
    with (tmp_path / "out.log").open("wb") as out, (tmp_path / "err.log").open("wb") as err:
        with patch("video_farm.worker.OwnedProcess") as launch:
            worker._launch_cli(["fixture"], stdout=out, stderr=err)
        assert launch.call_args.kwargs["stdout"] is out
        assert launch.call_args.kwargs["stderr"] is err
        assert "text" not in launch.call_args.kwargs


def test_log_tail_reads_only_bounded_bytes_with_utf8_split(tmp_path):
    path = tmp_path / "large.log"
    with path.open("wb") as stream:
        for _ in range(16):
            stream.write(b"a" * (64 * 1024))
        stream.write("终止诊断".encode())
    tail = VideoWorker._read_log_tail(path, byte_limit=9)
    assert tail.endswith("止诊断")
    assert "truncated" in tail.lower()
    assert len(tail) < 100
