import sqlite3

conn = sqlite3.connect("video_farm_data/tasks.db")
c = conn.cursor()

updates = [
    ("task_82940e33b0a6", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\f175f836-bfa5-4199-b668-aa0c66126bfc.mp4", 0.9920),
    ("task_b005751c6636", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\94a271c3-6a2d-462b-adca-119b0ca3d702.mp4", 0.9881),
    ("task_26df73179f8e", r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\13e37d54-4570-42a0-afdb-07d514b54fa2.mp4", 0.9841),
]

for tid, path, ncc in updates:
    c.execute("""
        UPDATE tasks 
        SET status = 'completed', 
            output_video_path = ?, 
            first_frame_ncc = ?, 
            first_frame_matched = 1, 
            error_code = NULL, 
            error_message = NULL 
        WHERE id = ?
    """, (path, ncc, tid))

conn.commit()
print("Updated tasks in DB.")
