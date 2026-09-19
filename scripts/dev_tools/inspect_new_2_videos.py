import sqlite3, json, subprocess
from pathlib import Path
from video_farm.verify import verify_task_video

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()

task_info = {
    "11_促保利素": {
        "id": "task_b96c4aee24a1",
        "first_frame": "video_farm_data/uploads/scenes/prod_11_first_frame.png"
    },
    "12_优根优苗": {
        "id": "task_743ac8a92022",
        "first_frame": "video_farm_data/uploads/scenes/prod_12_first_frame.png"
    }
}

for name, item in task_info.items():
    row = c.execute("SELECT output_video_path, status, first_frame_ncc, first_frame_matched, watermark_check FROM tasks WHERE id = ?", (item["id"],)).fetchone()
    vpath = row[0]
    print(f"=== {name} ===")
    print(f"Task status: {row[1]}, Video path: {vpath}")
    print(f"Initial DB QA: ncc={row[2]}, matched={row[3]}, watermark={row[4]}")
    
    # Run ffprobe
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=width,height,r_frame_rate,duration:format=size,duration",
        "-of", "json", vpath
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    probe = json.loads(p.stdout)
    streams = probe.get("streams", [{}])[0]
    w = streams.get("width")
    h = streams.get("height")
    fps = streams.get("r_frame_rate")
    dur = streams.get("duration") or probe.get("format", {}).get("duration")
    size_mb = int(probe.get("format", {}).get("size", 0)) / (1024 * 1024)
    print(f"ffprobe: {w}x{h}, {fps} fps, {float(dur):.1f}s, {size_mb:.2f} MB")
    
    # Run quality verification
    res = verify_task_video(
        video_path=Path(vpath),
        start_image_path=Path(item["first_frame"]),
        end_image_path=None,
        qa_dir=Path("video_farm_data/qa")
    )
    print(f"QA verify: success={res['success']}, first_ncc={res['first_ncc']:.4f}, watermark={res['watermark_status']}\n")
