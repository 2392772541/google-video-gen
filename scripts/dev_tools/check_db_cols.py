import sqlite3
conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
for col in c.execute("PRAGMA table_info(tasks)").fetchall():
    print(col[1])
