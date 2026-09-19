import os, glob

session_dir = r"C:\Users\win10\.codex\sessions"
files = glob.glob(os.path.join(session_dir, "**", "*.jsonl"), recursive=True)
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:3]:
    print("Checking", f)
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        for line in fp:
            if "matchTemplate" in line or "prod_01_first_frame" in line:
                print("Found match in", f)
                # print first 300 chars of snippet
                idx = line.find("matchTemplate")
                if idx != -1:
                    print(line[max(0, idx-100):min(len(line), idx+200)])
                break
