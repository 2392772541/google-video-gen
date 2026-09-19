import sqlite3, json, re

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()

with open("video_farm_data/submitted_images.json", "r", encoding="utf-8") as f:
    submitted = json.load(f)

real_paths = {}
for key, info in submitted.items():
    tid = info["task_id"]
    row = c.execute("SELECT logs FROM tasks WHERE id = ?", (tid,)).fetchone()
    if row and row[0]:
        log = row[0]
        match = re.search(r'"media_name":\s*"([a-f0-9\-]+)"', log)
        if match:
            media_name = match.group(1)
            # Find the actual file matching media_name
            import glob
            files = glob.glob(f"video_farm_data/outputs/{media_name}*")
            if files:
                real_paths[key] = {
                    "task_id": tid,
                    "media_name": media_name,
                    "scene_path": str(files[0]).replace("\\", "/"),
                    "ref": info["ref"]
                }
                print(f"[{key}] -> {files[0]}")
            else:
                print(f"[{key}] media_name {media_name} file not found!")
        else:
            print(f"[{key}] No media_name in log")

# Add 05 and 06
real_paths["05"] = {
    "task_id": "manual_05",
    "media_name": "fd68493f",
    "scene_path": "video_farm_data/uploads/scenes/fd68493f-07eb-4fe7-ac2b-73e46377099f_1.jpg",
    "ref": "E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/05_10%氨基寡糖素液剂.png"
}
real_paths["06"] = {
    "task_id": "task_3e3eaa9cf4c8",
    "media_name": "1178a729",
    "scene_path": "video_farm_data/outputs/1178a729-88d6-4800-97c8-e6a5ce90a85b_1.jpg",
    "ref": "E:/公司素材/产品实景图/最新定稿图/福联产品包装效果图_9款/06_90%褐藻寡糖粉剂.png"
}

with open("video_farm_data/real_10_scenes.json", "w", encoding="utf-8") as f:
    json.dump(real_paths, f, ensure_ascii=False, indent=2)

print("\nTotal verified unique scenes:", len(real_paths))
