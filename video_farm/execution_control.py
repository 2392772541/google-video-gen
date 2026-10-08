"""Bounded execution owned by the worker thread, with shared cancellation."""
import threading
import time


class ExecutionStopped(RuntimeError):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ExecutionControl:
    def __init__(self, cancel_event=None, timeout_sec=360):
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.timeout_sec = max(0.0, float(timeout_sec))
        self.deadline = time.monotonic() + self.timeout_sec

    @property
    def remaining(self):
        return min(self.timeout_sec, max(0.0, self.deadline - time.monotonic()))

    def check(self):
        if self.cancel_event.is_set():
            raise ExecutionStopped("用户已取消任务；本地执行停止（云端已提交的生成可能仍继续）。", "USER_CANCELLED")
        if not self.remaining:
            raise ExecutionStopped("任务总执行时间超时。", "EXECUTION_TIMEOUT")

    def timeout_ms(self, maximum=5000):
        self.check()
        return max(1, min(int(maximum), int(self.remaining * 1000)))

    def pause(self, page, seconds):
        end = time.monotonic() + max(0, seconds)
        self.check()
        while time.monotonic() < end:
            self.check()
            interval = min(0.2, end - time.monotonic(), self.remaining)
            if page is None:
                self.cancel_event.wait(interval)
            else:
                # Pump Playwright events on its owner thread; never close from
                # the API / scheduler thread to try to interrupt it.
                page.wait_for_timeout(interval * 1000)
        self.check()


def terminate_owned_process(proc):
    """Bounded cleanup of this exact child tree, never all browser processes."""
    import subprocess
    import sys
    if proc.poll() is not None:
        return True
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=5)
        else:
            proc.kill()
        proc.wait(timeout=5)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
            proc.wait(timeout=3)
        except (OSError, subprocess.SubprocessError):
            return False
    return proc.poll() is not None
