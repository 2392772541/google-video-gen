"""Local-only child for the opt-in process regression; never opens a browser."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

if sys.argv[1] == "descendant":
    time.sleep(30)
    raise SystemExit(0)

spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
attempt = Path(spec["output_dir"])
if spec["task"]["prompt"] == "complete fixture":
    output = attempt / (spec["task"]["id"] + ".mp4")
    output.write_bytes(b"explicit fixture media; not a generated video")
    (attempt / "result.json").write_text(json.dumps({
        "success": True, "output_video_path": str(output),
        "submission_possible": False,
    }), encoding="utf8")
    raise SystemExit(0)

from greenlet import greenlet
from playwright._impl._sync_base import SyncBase
child = subprocess.Popen([sys.executable, __file__, "descendant"])
loop = asyncio.new_event_loop()
dispatcher = greenlet(lambda: None)
dispatcher.switch()
assert dispatcher.dead
if spec["task"]["prompt"] == "dead sync submitted":
    (attempt / "submission.json").write_text(json.dumps({
        "submission_possible": True, "task_id": spec["task"]["id"],
    }), encoding="utf8")
(attempt / "ready.json").write_text(json.dumps({
    "root_pid": os.getpid(), "descendant_pid": child.pid,
    "real_sync": True, "dispatcher_dead": dispatcher.dead,
}), encoding="utf8")
async def pending():
    await asyncio.sleep(1)
print("Entering the real SyncBase._sync with a dead dispatcher", flush=True)
SyncBase._sync(SimpleNamespace(_loop=loop, _dispatcher_fiber=dispatcher), pending())
raise RuntimeError("The dead dispatcher unexpectedly returned")
