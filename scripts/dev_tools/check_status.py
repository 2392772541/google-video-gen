import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
submitted = json.load(open("video_farm_data/submitted_10_videos.json", encoding="utf-8"))

for k, info in sorted(submitted.items()):
    tid = info["task_id"]
    row = c.execute("SELECT status, assigned_profile_id, output_video_path, error_message FROM tasks WHERE id = ?", (tid,)).fetchone()
    st, prof, path, err = row
    info_str = path if path else (err if err else "")
    print(f"[{k}] {st:10s} | {str(prof):15s} | {info_str}")
