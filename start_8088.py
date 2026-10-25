import subprocess
import time
import urllib.request
import json
import sys
import os
import signal
from pathlib import Path

root_dir = Path(__file__).resolve().parent

# Terminate existing 8088 process if any
try:
    out = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True)
    for line in out.splitlines():
        if "127.0.0.1:8088" in line and "LISTENING" in line:
            parts = line.strip().split()
            pid = int(parts[-1])
            if pid != os.getpid():
                print(f"Terminating old 8088 process {pid}")
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
except Exception as e:
    print(f"Process cleanup note: {e}")

try:
    from video_farm.canvas_autostart import ensure_canvas_services
    ensure_canvas_services()
except Exception as e:
    print(f"Canvas autostart note: {e}")

cmd = [sys.executable, "-m", "video_farm.web", "--port", "8088", "--host", "127.0.0.1"]

proc = subprocess.Popen(
    cmd,
    cwd=str(root_dir),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
)

time.sleep(2)

try:
    with urllib.request.urlopen("http://127.0.0.1:8088/api/overview", timeout=5) as resp:
        data = json.loads(resp.read().decode())
        print(f"Video Farm 8088 started successfully! (PID: {proc.pid})")
        print(f"Tasks: {data.get('tasks', {})}")
except Exception as e:
    print(f"Failed to connect to 8088: {e}", file=sys.stderr)
    proc.kill()
    sys.exit(1)

