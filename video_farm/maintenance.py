"""Low-resource maintenance. Default is read-only; restores require --apply.
python -m video_farm.maintenance --output audit.json
python -m video_farm.maintenance --restore <manifest.json> [--apply]
"""
from __future__ import annotations
import argparse
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from .db import DEFAULT_DB_PATH

ACTIVE = {"queued", "retry_wait", "dispatching", "running", "verifying"}

def connect_readonly(database):
    conn = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def inspect(database=DEFAULT_DB_PATH):
    database = Path(database).resolve()
    conn = connect_readonly(database)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        tasks = [dict(r) for r in conn.execute("SELECT * FROM tasks")]
        shots = [dict(r) for r in conn.execute("SELECT * FROM vids_shots")]
        workflows = [dict(r) for r in conn.execute("SELECT * FROM vids_workflows")]
        profiles = [dict(r) for r in conn.execute("SELECT id,status,enabled FROM profiles")]
    finally:
        conn.close()
    counts = {}
    missing = []
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
        if task["status"] != "completed": continue
        paths = [task.get("output_video_path"), task.get("output_audio_path")]
        try:
            images = json.loads(task.get("output_image_paths") or "[]")
            if not isinstance(images, list):
                raise ValueError("Image output must be a list")
            paths += images
        except (TypeError, ValueError):
            missing.append({"id": task["id"], "reason": "invalid image list"})
        paths = [p for p in paths if isinstance(p, str) and p]
        # Never access network shares during unattended inspection.
        absent = [p for p in paths if p.startswith(("\\\\", "//")) or not Path(p).is_file()]
        if absent or not paths:
            missing.append({"id":task["id"],"missing_paths":absent,"no_output_recorded":not paths})
    by_id = {t["id"]: t for t in tasks}
    orphans = []
    for wf in workflows:
        linked = [s for s in shots if s["workflow_id"] == wf["id"]]
        active = any(by_id.get(s.get("task_id"),{}).get("status") in ACTIVE for s in linked)
        if wf["status"] in ("generating","running","queued") and not active:
            orphans.append({"id":wf["id"],"status":wf["status"],"reason":"no active linked task; review only"})
    disk = shutil.disk_usage(database.parent)
    import psutil
    return {"checked_at":datetime.now().astimezone().isoformat(),"read_only":True,
        "database":str(database),"integrity":integrity,"tasks":{"total":len(tasks),"by_status":counts},
        "profiles":{"total":len(profiles),"by_status":{s:sum(p["status"]==s for p in profiles) for s in {p["status"] for p in profiles}}},
        "missing_completed_outputs":missing,"suspected_orphan_workflows":orphans,
        "disk_free_gib":round(disk.free/1024**3,2),"memory_available_gib":round(psutil.virtual_memory().available/1024**3,2),
        "quarantine_manifests":[str(p) for p in (database.parent/"trash").glob("*/manifest.json")],
        "database_candidates":[{"path":str(p),"bytes":p.stat().st_size} for p in database.parent.parent.glob("*.db")]}

def restore(manifest_path, database=DEFAULT_DB_PATH, apply=False):
    database = Path(database).resolve()
    root = database.parent
    manifest_path = Path(manifest_path).resolve()
    if manifest_path.name != "manifest.json" or not manifest_path.is_relative_to((root/"trash").resolve()):
        raise ValueError("Manifest must be within this database quarantine")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = data["task"]
    task_id = record["id"]
    if not task_id or any(c in task_id for c in "/\\:") or task_id in (".",".."):
        raise ValueError("Invalid task ID")
    if record["status"] in ACTIVE: # cancelled queued deletes must not restart generators on restore
        record["status"] = "cancelled"
        record["error_message"] = "Restored by maintenance; explicitly retry to resume"
    conn = sqlite3.connect(str(database), timeout=30)
    conn.row_factory = sqlite3.Row
    moved = []
    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        if conn.execute("SELECT 1 FROM tasks WHERE id=?",(task_id,)).fetchone():
            raise ValueError("Task already exists; refusing overwrite")
        columns = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        if set(record)-columns: raise ValueError("Database schema differs; review manually")
        pairs=[]
        for item in data.get("moved_files",[]):
            src=Path(item["target"]).resolve(); dst=Path(item["source"]).resolve()
            if not src.is_relative_to((manifest_path.parent/"files").resolve()) or not any(dst.is_relative_to((root/d).resolve()) for d in ("outputs","qa")):
                raise ValueError("Unsafe file path in manifest")
            if not src.is_file() or dst.exists(): raise ValueError("Quarantine file missing or destination exists")
            pairs.append((src,dst))
        linked = []
        for shot in data.get("linked_shots",[]):
            row=conn.execute("SELECT * FROM vids_shots WHERE id=?",(shot["id"],)).fetchone()
            if row and row["task_id"] is None and row["status"]=="planned": linked.append(shot)
        plan={"task_id":task_id,"status":record["status"],"files":len(pairs),"linked_shots":len(linked),"applied":False}
        if not apply: return plan
        for src,dst in pairs:
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(src),str(dst));moved.append((src,dst))
        keys=list(record)
        conn.execute("INSERT INTO tasks ("+",".join(keys)+") VALUES ("+",".join("?" for _ in keys)+")",[record[k] for k in keys])
        event_cols={r[1] for r in conn.execute("PRAGMA table_info(task_events)")}
        for event in data.get("events",[]):
            values={k:v for k,v in event.items() if k in event_cols and k!="id"}
            if values.get("task_id")!=task_id: raise ValueError("Wrong task event")
            keys=list(values)
            conn.execute("INSERT INTO task_events ("+",".join(keys)+") VALUES ("+",".join("?" for _ in keys)+")",[values[k] for k in keys])
        for shot in linked:
            conn.execute("UPDATE vids_shots SET task_id=?,status=? WHERE id=? AND task_id IS NULL AND status='planned'",(task_id,shot["status"],shot["id"]))
        conn.commit();committed=True;plan["applied"]=True
        return plan
    finally:
        if not committed:
            conn.rollback()
            for src,dst in reversed(moved):
                src.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dst),str(src))
        conn.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,default=DEFAULT_DB_PATH)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--restore",type=Path)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    if args.apply and not args.restore: parser.error("--apply requires --restore")
    result=restore(args.restore,args.database,args.apply) if args.restore else inspect(args.database)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding="utf-8")
    print(text)

if __name__ == "__main__": main()
