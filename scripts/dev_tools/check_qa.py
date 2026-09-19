import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
submitted = json.load(open("video_farm_data/submitted_10_videos.json", encoding="utf-8"))

for k in ["01", "03", "04"]:
    tid = submitted[k]["task_id"]
    row = c.execute("SELECT output_video_path, qa_result, logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    print(f"=== [{k}] ({tid}) ===")
    print(f"Output Video Path: {row[0]}")
    print(f"QA Result: {row[1]}")
