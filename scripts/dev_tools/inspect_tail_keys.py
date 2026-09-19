import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
row = c.execute("SELECT logs FROM tasks WHERE id = ?", ("task_82940e33b0a6",)).fetchone()
log = row[0] or ""

for line in reversed(log.splitlines()):
    line_str = line.strip()
    if line_str.startswith("{") and line_str.endswith("}"):
        d = json.loads(line_str)
        print("KEYS:", list(d.keys()))
        if "path" in d:
            print("  Found 'path':", d["path"])
