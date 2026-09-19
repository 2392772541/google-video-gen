f = r"C:\Users\win10\.codex\sessions\2026\09\16\rollout-2026-09-16T16-30-02-01a0a956-5688-74a0-accf-aecec539afc2.jsonl"
with open(f, "r", encoding="utf-8", errors="ignore") as fp:
    for line in fp:
        if "prod_01_first_frame.png" in line and "PIL" in line:
            print(line[:2500])
            break
