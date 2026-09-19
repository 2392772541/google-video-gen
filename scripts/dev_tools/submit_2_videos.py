import urllib.request, urllib.parse, json, os

tasks = {
    "11_促保利素": {
        "title": "添添向上 促保利素 (1000g)",
        "img": "video_farm_data/uploads/scenes/prod_11_first_frame.png",
        "prompt": "Commercial advertising shot, slow cinematic macro dolly push-in toward the package on the glowing warm amber stone pedestal, golden wheat field swaying gently in the background breeze under radiant morning sunrise, golden lens flares and shimmering light particles drifting across the frame, 4k ultra realistic, high-end product commercial film."
    },
    "12_优根优苗": {
        "title": "添添向上 优根优苗 (1000g)",
        "img": "video_farm_data/uploads/scenes/prod_12_first_frame.png",
        "prompt": "Cinematic agricultural science commercial, smooth slow forward tracking camera movement toward the product pouch on the dark stone pedestal, gentle misty vapors rising around the transparent glass vessels with root seedlings, soft emerald green ambient lighting and subtle reflections, pristine high-tech corporate showcase, 4k 60fps luxury aesthetic."
    }
}

api_url = "http://127.0.0.1:8088/api/tasks/create"
submitted_tasks = {}

for k, item in tasks.items():
    data = urllib.parse.urlencode({
        "prompt": item["prompt"],
        "engine": "flow",
        "model": "veo-lite",
        "start_image_path": os.path.abspath(item["img"]),
        "aspect_ratio": "16:9",
        "duration_sec": 8,
        "priority": 10
    }).encode("utf-8")
    req = urllib.request.Request(api_url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        tid = res["id"]
        item["task_id"] = tid
        item["status"] = res["status"]
        submitted_tasks[k] = item
        print(f"[{k}] Submitted -> Task ID: {tid}")

with open("video_farm_data/submitted_2_videos.json", "w", encoding="utf-8") as f:
    json.dump(submitted_tasks, f, ensure_ascii=False, indent=2)

print("Both video generation tasks submitted successfully!")
