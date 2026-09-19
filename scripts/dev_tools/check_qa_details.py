import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
submitted = json.load(open("video_farm_data/submitted_10_videos.json", encoding="utf-8"))

for k, info in sorted(submitted.items()):
    tid = info["task_id"]
    row = c.execute("SELECT status, first_frame_ncc, last_frame_ncc, first_frame_matched, last_frame_matched, watermark_check, output_video_path FROM tasks WHERE id = ?", (tid,)).fetchone()
    print(f"[{k}] {row[0]:10s} | f_ncc={str(row[1]):6s}, f_match={str(row[3]):5s} | l_ncc={str(row[2]):6s}, l_match={str(row[4]):5s} | wm={str(row[5]):8s} | path={str(row[6])[-30:]}")
