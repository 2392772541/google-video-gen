with open("video_farm/worker.py", "r", encoding="utf-8") as f:
    text = f.read()

old_block = """            # Try parsing JSON output from stdout
            output_video_path = None
            try:
                lines = stdout.strip().splitlines()
                for line in reversed(lines):
                    line_str = line.strip()
                    if line_str.startswith("{") and line_str.endswith("}"):
                        data = json.loads(line_str)
                        if "local_path" in data and data["local_path"]:
                            output_video_path = data["local_path"]
                            break
                        elif "path" in data:
                            output_video_path = data["path"]
                            break
                        elif "saved_path" in data:
                            output_video_path = data["saved_path"]
                            break
                        elif "output" in data:
                            output_video_path = data["output"]
                            break
            except Exception:
                pass"""

new_block = """            # Try parsing JSON output from stdout (support multi-line and single-line JSON)
            output_video_path = None
            try:
                s_clean = stdout.strip()
                if s_clean.startswith("{") and s_clean.endswith("}"):
                    data = json.loads(s_clean)
                    for k in ["local_path", "path", "saved_path", "output"]:
                        if data.get(k):
                            output_video_path = data[k]
                            break
                if not output_video_path:
                    lines = stdout.strip().splitlines()
                    for line in reversed(lines):
                        line_str = line.strip()
                        if line_str.startswith("{") and line_str.endswith("}"):
                            data = json.loads(line_str)
                            for k in ["local_path", "path", "saved_path", "output"]:
                                if data.get(k):
                                    output_video_path = data[k]
                                    break
                            if output_video_path:
                                break
                if not output_video_path:
                    import re
                    m = re.search(r'"(?:local_path|path)":\s*"([^"]+\.mp4)"', stdout + "\\n" + stderr)
                    if m:
                        cand = m.group(1).replace("\\\\\\\\", "\\\\")
                        if Path(cand).exists():
                            output_video_path = cand
            except Exception:
                pass"""

if old_block in text:
    text = text.replace(old_block, new_block, 1)
    with open("video_farm/worker.py", "w", encoding="utf-8") as f:
        f.write(text)
    print("Successfully patched video_farm/worker.py")
else:
    print("old_block not found in video_farm/worker.py")
