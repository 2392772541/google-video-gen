import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
submitted = json.load(open("video_farm_data/submitted_10_videos.json", encoding="utf-8"))

for k in ["01", "02", "03", "04"]:
    tid = submitted[k]["task_id"]
    row = c.execute("SELECT logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    log = row[0] or ""
    # find lines with { }
    print(f"=== [{k}] ({tid}) ===")
    for line in log.splitlines():
        if line.strip().startswith("{") and line.strip().endswith("}"):
            try:
                d = json.loads(line.strip())
                # filter out simple log events if any, or print keys
                if "local_path" in d or "path" in d or "video" in str(d) or "event" in d:
                    print("  JSON:", d.get("event"), d.get("local_path"), d.get("path"), d.get("media_name"))
            except:
                pass
