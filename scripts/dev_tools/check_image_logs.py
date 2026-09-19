import sqlite3, json, re

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()

with open("video_farm_data/submitted_images.json", "r", encoding="utf-8") as f:
    submitted = json.load(f)

for key, info in submitted.items():
    tid = info["task_id"]
    row = c.execute("SELECT logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    if row and row[0]:
        log = row[0]
        match = re.search(r'{\s*"status":\s*"ok".*?}', log, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                imgs = data.get("images", [])
                if imgs:
                    print(f"[{key}] {tid} -> {imgs[0].get('local_path')} (seed={imgs[0].get('seed')})")
            except Exception as e:
                print(f"[{key}] parse err: {e}")
        else:
            print(f"[{key}] No json found in log")
