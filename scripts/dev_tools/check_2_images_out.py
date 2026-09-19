import sqlite3, json, re, glob, os

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()

task_ids = {"11_促保利素": "task_825e562b128e", "12_优根优苗": "task_4a20cd88b4f0"}

for name, tid in task_ids.items():
    row = c.execute("SELECT output_image_paths, logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    out_paths, logs = row[0], row[1]
    print(f"=== {name} ({tid}) ===")
    print("output_image_paths:", out_paths)
    m = re.search(r'"media_name":\s*"([a-f0-9\-]+)"', logs or "")
    if m:
        mname = m.group(1)
        print("media_name from log:", mname)
        found = glob.glob(f"video_farm_data/outputs/{mname}*")
        print("matching files:", found)
