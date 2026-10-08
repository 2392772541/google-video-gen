"""Atomic media publication after a verified attempt and owned-tree cleanup."""
import os
import uuid
from pathlib import Path


def publish_video(source, output_dir, task_id, control):
    source, output_dir = Path(source), Path(output_dir)
    destination = output_dir / f"{task_id}.mp4"
    temporary = output_dir / f".{task_id}.{uuid.uuid4().hex}.publishing"
    try:
        control.check()
        try:
            os.link(source, temporary)
        except OSError:
            with source.open("rb") as src, temporary.open("xb") as dst:
                while True:
                    control.check()
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    dst.write(block)
        control.check()
        os.replace(temporary, destination)
        return str(destination)
    finally:
        temporary.unlink(missing_ok=True)
