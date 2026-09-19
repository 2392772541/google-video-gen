import sqlite3
conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
row = c.execute("SELECT logs FROM tasks WHERE id = 'task_3ab23d0adf5e'").fetchone()
if row:
    print(row[0][:1500])
