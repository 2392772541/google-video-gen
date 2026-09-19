import sqlite3
conn = sqlite3.connect('video_farm_data/tasks.db')
c = conn.cursor()
c.execute('PRAGMA table_info(tasks)')
for col in c.fetchall():
    print(col[1], col[2])
