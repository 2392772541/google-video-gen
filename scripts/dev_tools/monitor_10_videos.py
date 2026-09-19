import sqlite3, json, time

with open("video_farm_data/submitted_10_videos.json", encoding="utf-8") as f:
    submitted = json.load(f)

task_ids = {info["task_id"]: (k, info["title"]) for k, info in submitted.items()}

while True:
    conn = sqlite3.connect("video_farm_data/tasks.db")
    c = conn.cursor()
    
    statuses = {}
    completed_count = 0
    running_count = 0
    queued_count = 0
    failed_count = 0
    
    for tid, (k, title) in task_ids.items():
        row = c.execute("SELECT status, assigned_profile_id, output_video_path, error_message FROM tasks WHERE id = ?", (tid,)).fetchone()
        if row:
            st, prof, path, err = row
            statuses[k] = (st, prof, path, err)
            if st == "completed":
                completed_count += 1
            elif st == "running":
                running_count += 1
            elif st == "queued":
                queued_count += 1
            elif st == "failed":
                failed_count += 1
    
    conn.close()
    print(f"[{time.strftime('%H:%M:%S')}] Progress: {completed_count}/10 Completed | {running_count} Running | {queued_count} Queued | {failed_count} Failed")
    for k, (st, prof, path, err) in sorted(statuses.items()):
        print(f"  [{k}] {st:10s} (Profile: {str(prof):15s}) -> {str(path or err or '')}")
        
    if completed_count + failed_count == len(task_ids):
        print("All tasks reached terminal state!")
        break
        
    time.sleep(15)
