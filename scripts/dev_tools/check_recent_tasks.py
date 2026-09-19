import sqlite3
conn = sqlite3.connect('video_farm_data/tasks.db')
c = conn.cursor()
c.execute('SELECT id, status, assigned_profile_id, output_video_path, error_message, updated_at FROM tasks ORDER BY rowid DESC LIMIT 4')
for row in c.fetchall():
    print(row)
