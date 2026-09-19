import urllib.request, json, time

task_ids = ["task_b96c4aee24a1", "task_743ac8a92022"]

for i in range(50):
    all_done = True
    statuses = {}
    for tid in task_ids:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:8088/api/tasks/{tid}")
            with urllib.request.urlopen(req) as res:
                data = json.loads(res.read().decode("utf-8"))
                st = data.get("status")
                profile = data.get("assigned_profile", "")
                output = data.get("output_video_path")
                statuses[tid] = f"{st} (prof: {profile}, out: {bool(output)})"
                if st not in ["completed", "failed", "cancelled"]:
                    all_done = False
        except Exception as e:
            statuses[tid] = f"error: {e}"
            all_done = False
            
    print(f"[{i*5}s] {statuses}")
    if all_done:
        print("All video generation tasks finished!")
        break
    time.sleep(5)
