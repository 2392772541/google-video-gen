import urllib.request, json, time

task_ids = ["task_825e562b128e", "task_4a20cd88b4f0"]

for i in range(30):
    all_done = True
    statuses = {}
    for tid in task_ids:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:8088/api/tasks/{tid}")
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode('utf-8'))
                st = data.get("status")
                profile = data.get("assigned_profile", "")
                statuses[tid] = f"{st} (prof: {profile})"
                if st not in ["completed", "failed", "cancelled"]:
                    all_done = False
        except Exception as e:
            statuses[tid] = f"error: {e}"
            all_done = False
            
    print(f"[{i*5}s] {statuses}")
    if all_done:
        print("All image generation tasks finished!")
        break
    time.sleep(5)
