import sqlite3
conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
for row in c.execute("SELECT id, task_type, status, assigned_profile_id, error_message FROM tasks WHERE id IN ('task_825e562b128e', 'task_4a20cd88b4f0')"):
    print(row)
