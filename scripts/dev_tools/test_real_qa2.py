from video_farm.verify import verify_task_video
from pathlib import Path

tests = {
    "01": {
        "start": "video_farm_data/uploads/scenes/prod_01_first_frame.png",
        "video": "video_farm_data/outputs/f175f836-bfa5-4199-b668-aa0c66126bfc.mp4"
    },
    "03": {
        "start": "video_farm_data/uploads/scenes/prod_03_first_frame.png",
        "video": "video_farm_data/outputs/94a271c3-6a2d-462b-adca-119b0ca3d702.mp4"
    },
    "04": {
        "start": "video_farm_data/uploads/scenes/prod_04_first_frame.png",
        "video": "video_farm_data/outputs/13e37d54-4570-42a0-afdb-07d514b54fa2.mp4"
    }
}

for k, item in tests.items():
    res = verify_task_video(
        video_path=Path(item["video"]),
        start_image_path=Path(item["start"]),
        end_image_path=None,
        qa_dir=Path("video_farm_data/qa"),
        task_id=f"test_{k}"
    )
    print(f"[{k}] QA passed={res['passed']}, first_ncc={res['first_frame_ncc']:.4f}, match={res['first_frame_matched']}, wm={res['watermark_check']}")
