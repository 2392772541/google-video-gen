from pathlib import Path

videos = {
    "01": "video_farm_data/outputs/f175f836-bfa5-4199-b668-aa0c66126bfc.mp4",
    "02": "video_farm_data/outputs/5561f737-1478-41a1-8bf2-a4cacc26d812.mp4",
    "03": "video_farm_data/outputs/94a271c3-6a2d-462b-adca-119b0ca3d702.mp4",
    "04": "video_farm_data/outputs/13e37d54-4570-42a0-afdb-07d514b54fa2.mp4",
    "05": "video_farm_data/outputs/15ecbd05-29ab-4bf9-a5bb-dce8650b90c1.mp4",
    "06": "video_farm_data/outputs/145a7e80-5981-425c-a8cf-c13c505adaec.mp4",
    "07": "video_farm_data/outputs/4958b014-659e-4c41-86db-11140f873c70.mp4",
    "08": "video_farm_data/outputs/afd30207-d774-448d-8d81-c3cb1db174d4.mp4",
    "09": "video_farm_data/outputs/3b6e535c-01c8-42c0-966a-7cfd0c69e4a2.mp4",
    "kui": "video_farm_data/outputs/9bab7bbd-9a71-42d3-a8db-da1abfc801bc.mp4"
}

for k, p in videos.items():
    path = Path(p)
    print(f"[{k}] exists={path.exists()}, size={path.stat().st_size if path.exists() else 0} -> {p}")
