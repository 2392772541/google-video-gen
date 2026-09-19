with open("video_farm/worker.py", encoding="utf-8") as f:
    text = f.read()
idx = text.find("existing_files = set")
print(text[idx:idx+1500])
