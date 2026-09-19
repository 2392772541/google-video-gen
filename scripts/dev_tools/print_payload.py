import json

f = r"C:\Users\win10\.codex\sessions\2026\09\16\rollout-2026-09-16T16-30-02-01a0a956-5688-74a0-accf-aecec539afc2.jsonl"
with open(f, "r", encoding="utf-8", errors="ignore") as fp:
    for line in fp:
        if "coords = {" in line:
            data = json.loads(line)
            # dump payload
            payload = data.get("payload", {})
            item = payload.get("item", {})
            for k, v in item.items():
                print(f"--- {k} ---")
                print(str(v)[:2000])
            break
