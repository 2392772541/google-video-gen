import sqlite3

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()
row = c.execute("SELECT logs FROM tasks WHERE id = ?", ("task_82940e33b0a6",)).fetchone()
log = row[0] or ""

if "=== STDOUT ===" in log:
    part = log.split("=== STDOUT ===")[1].split("=== STDERR ===")[0]
    print("STDOUT:")
    print(part)
