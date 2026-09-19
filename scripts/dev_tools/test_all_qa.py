import video_farm.verify

for k, v, s in [
    ("01", "video_farm_data/outputs/f175f836-bfa5-4199-b668-aa0c66126bfc.mp4", "video_farm_data/uploads/scenes/prod_01_first_frame.png"),
    ("03", "video_farm_data/outputs/94a271c3-6a2d-462b-adca-119b0ca3d702.mp4", "video_farm_data/uploads/scenes/prod_03_first_frame.png"),
    ("04", "video_farm_data/outputs/13e37d54-4570-42a0-afdb-07d514b54fa2.mp4", "video_farm_data/uploads/scenes/prod_04_first_frame.png"),
]:
    res = video_farm.verify.verify_task_video(v, s)
    print(f"[{k}] success={res['success']}, first_ncc={res['first_ncc']:.4f}, matched={res['first_matched']}, wm={res['watermark_status']}")
