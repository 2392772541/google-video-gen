import sqlite3

conn = sqlite3.connect('video_farm_data/tasks.db')
with conn:
    cur = conn.execute("UPDATE tasks SET status = 'cancelled', error_message = '用户主动中断' WHERE status IN ('queued', 'running', 'retry_wait')")
    print(f"Cancelled tasks count: {cur.rowcount}")
    cur2 = conn.execute("UPDATE profiles SET status = 'idle', cooldown_until = NULL WHERE status IN ('busy', 'cooldown')")
    print(f"Reset profiles count: {cur2.rowcount}")
conn.close()
