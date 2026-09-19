with open("video_farm/worker.py", "r", encoding="utf-8") as f:
    content = f.read()

target = """            # 尝试从 stdout 解析输出图片路径列表
            found_paths = []
            try:
                lines = stdout.strip().splitlines()
                for line in reversed(lines):
                    line_str = line.strip()
                    if line_str.startswith("{") and line_str.endswith("}"):
                        data = json.loads(line_str)
                        if "images" in data and isinstance(data["images"], list):
                            for img in data["images"]:
                                if isinstance(img, dict) and "local_path" in img and img["local_path"]:
                                    lp = Path(img["local_path"]).resolve()
                                    if lp.exists():
                                        found_paths.append(str(lp))
                            if found_paths:
                                break
                        elif "saved_paths" in data and isinstance(data["saved_paths"], list):
                            found_paths = [str(Path(p).resolve()) for p in data["saved_paths"] if Path(p).exists()]
                            if found_paths:
                                break
                        elif "paths" in data and isinstance(data["paths"], list):
                            found_paths = [str(Path(p).resolve()) for p in data["paths"] if Path(p).exists()]
                            if found_paths:
                                break
                        elif "local_path" in data and data["local_path"] and Path(data["local_path"]).exists():
                            found_paths = [str(Path(data["local_path"]).resolve())]
                            break
            except Exception:
                pass"""

replacement = """            # 尝试从 stdout 解析输出图片路径列表 (支持多行/单行 JSON)
            found_paths = []
            try:
                s_clean = stdout.strip()
                parsed_data = None
                if s_clean.startswith("{") and s_clean.endswith("}"):
                    try:
                        parsed_data = json.loads(s_clean)
                    except Exception:
                        pass
                if not parsed_data:
                    for line in reversed(s_clean.splitlines()):
                        line_str = line.strip()
                        if line_str.startswith("{") and line_str.endswith("}"):
                            try:
                                parsed_data = json.loads(line_str)
                                break
                            except Exception:
                                pass
                if parsed_data:
                    data = parsed_data
                    if "images" in data and isinstance(data["images"], list):
                        for img in data["images"]:
                            if isinstance(img, dict) and "local_path" in img and img["local_path"]:
                                lp = Path(img["local_path"]).resolve()
                                if lp.exists():
                                    found_paths.append(str(lp))
                    elif "saved_paths" in data and isinstance(data["saved_paths"], list):
                        found_paths = [str(Path(p).resolve()) for p in data["saved_paths"] if Path(p).exists()]
                    elif "paths" in data and isinstance(data["paths"], list):
                        found_paths = [str(Path(p).resolve()) for p in data["paths"] if Path(p).exists()]
                    elif "local_path" in data and data["local_path"] and Path(data["local_path"]).exists():
                        found_paths = [str(Path(data["local_path"]).resolve())]
            except Exception:
                pass"""

if target in content:
    content = content.replace(target, replacement)
    with open("video_farm/worker.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("worker.py successfully updated for execute_image_task multi-line JSON!")
else:
    print("Target block not found in worker.py")
