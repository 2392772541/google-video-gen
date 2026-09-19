import sqlite3
conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
for row in c.execute("SELECT id, status, assigned_profile_id, output_video_path, error_message FROM tasks WHERE id IN ('task_b96c4aee24a1', 'task_743ac8a92022')"):
    print(row)
