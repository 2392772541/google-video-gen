with open("video_farm/worker.py", encoding="utf-8") as f:
    text = f.read()
idx = text.find("output_video_path =")
if idx == -1:
    idx = text.find("output_video")
print(text[idx-200:idx+1500])
