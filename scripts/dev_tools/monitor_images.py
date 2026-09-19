import urllib.request, json, time

with open("video_farm_data/submitted_images.json", "r", encoding="utf-8") as f:
    submitted = json.load(f)

print(f"Tracking {len(submitted)} image generation tasks...")

done = False
while not done:
    all_done = True
    statuses = {}
    for key, info in submitted.items():
        tid = info["task_id"]
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8088/api/tasks/{tid}") as res:
                t = json.loads(res.read().decode("utf-8"))
                st = t.get("status")
                prof = t.get("assigned_profile_id")
                imgs = t.get("image_paths") or []
                statuses[key] = (st, prof, len(imgs))
                if st not in ("completed", "failed"):
                    all_done = False
        except Exception as e:
            statuses[key] = ("error", str(e), 0)
            all_done = False
            
    summary = " | ".join([f"{k}:{s[0]}" for k, s in statuses.items()])
    print(f"[{time.strftime('%H:%M:%S')}] {summary}")
    if all_done:
        print("All image tasks reached final status!")
        break
    time.sleep(5)

