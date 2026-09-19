import sqlite3, json

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
submitted = json.load(open("video_farm_data/submitted_10_videos.json", encoding="utf-8"))

for k in ["01", "03", "04"]:
    tid = submitted[k]["task_id"]
    row = c.execute("SELECT status, assigned_profile_id, error_code, error_message, logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    print(f"=== [{k}] ({tid}) ===")
    print(f"Status: {row[0]}, Profile: {row[1]}")
    print(f"Error Code: {row[2]}, Message: {row[3]}")
    print("Logs tail:")
    print((row[4] or "")[-500:])
