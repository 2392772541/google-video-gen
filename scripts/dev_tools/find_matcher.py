f = r"C:\Users\win10\.codex\sessions\2026\09\16\rollout-2026-09-16T16-30-02-01a0a956-5688-74a0-accf-aecec539afc2.jsonl"
with open(f, "r", encoding="utf-8", errors="ignore") as fp:
    for line in fp:
        if "cv2.TM_CCOEFF_NORMED" in line or "template matching" in line.lower() or "best_scale" in line:
            print(line[:3000])
            break
