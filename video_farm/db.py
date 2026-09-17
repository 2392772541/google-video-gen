from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from .models import Task, Profile

DEFAULT_DB_PATH = Path("video_farm_data/tasks.db")

def get_db_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                profile_path TEXT,
                account_label TEXT,
                status TEXT DEFAULT 'idle', -- 'idle', 'busy', 'cooldown', 'auth_expired', 'restricted', 'disabled'
                watermark_mode TEXT DEFAULT 'unknown', -- 'unknown', 'clean', 'forced_visible'
                last_heartbeat_at TEXT,
                last_success_at TEXT,
                last_failure_at TEXT,
                cooldown_until TEXT,
                enabled INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                prompt TEXT NOT NULL,
                start_image_path TEXT NOT NULL,
                end_image_path TEXT NOT NULL,
                aspect_ratio TEXT DEFAULT '9:16',
                duration_sec INTEGER DEFAULT 5,
                status TEXT DEFAULT 'queued', -- 'queued', 'dispatching', 'running', 'verifying', 'completed', 'failed', 'retry_wait', 'cancelled'
                assigned_profile_id TEXT,
                priority INTEGER DEFAULT 10,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                require_clean_watermark INTEGER DEFAULT 0,
                submit_time TEXT NOT NULL,
                start_time TEXT,
                finish_time TEXT,
                output_video_path TEXT,
                first_frame_ncc REAL,
                last_frame_ncc REAL,
                last_vs_start_ncc REAL,
                first_frame_matched INTEGER,
                last_frame_matched INTEGER,
                watermark_check TEXT,
                error_code TEXT,
                error_message TEXT,
                logs TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                engine TEXT DEFAULT 'flow', -- 'flow', 'gemini'
                task_type TEXT DEFAULT 'video', -- 'video', 'image'
                model TEXT DEFAULT '',
                output_image_paths TEXT,
                FOREIGN KEY(assigned_profile_id) REFERENCES profiles(id)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES tasks(id)
            )
            """)

            # Ensure columns exist in tasks for backwards compatibility
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            if "engine" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN engine TEXT DEFAULT 'flow'")
            if "task_type" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN task_type TEXT DEFAULT 'video'")
            if "model" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN model TEXT DEFAULT ''")
            if "output_image_paths" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN output_image_paths TEXT")

            event_cols = [r["name"] for r in conn.execute("PRAGMA table_info(task_events)").fetchall()]
            if "detail" not in event_cols:
                conn.execute("ALTER TABLE task_events ADD COLUMN detail TEXT")
            if "created_at" not in event_cols:
                conn.execute("ALTER TABLE task_events ADD COLUMN created_at TEXT")
            if "message" not in event_cols:
                conn.execute("ALTER TABLE task_events ADD COLUMN message TEXT")
            if "timestamp" not in event_cols:
                conn.execute("ALTER TABLE task_events ADD COLUMN timestamp TEXT")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC, submit_time ASC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles(status, enabled)")
    finally:
        conn.close()

def row_to_profile(row: sqlite3.Row) -> Profile:
    return Profile(
        id=row["id"],
        name=row["name"],
        profile_path=row["profile_path"] or "",
        account_label=row["account_label"] or "",
        status=row["status"] or "idle",
        watermark_mode=row["watermark_mode"] or "unknown",
        last_heartbeat_at=row["last_heartbeat_at"],
        last_success_at=row["last_success_at"],
        last_failure_at=row["last_failure_at"],
        cooldown_until=row["cooldown_until"],
        enabled=bool(row["enabled"]),
        notes=row["notes"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"]
    )

def row_to_task(row: sqlite3.Row) -> Task:
    row_dict = dict(row)
    engine = row_dict.get("engine", "flow") or "flow"
    task_type = row_dict.get("task_type", "video") or "video"
    model = row_dict.get("model", "") or ""
    output_image_paths = row_dict.get("output_image_paths")
    t = Task(
        id=row["id"],
        project_id=row["project_id"] or "",
        prompt=row["prompt"],
        start_image_path=row["start_image_path"],
        end_image_path=row["end_image_path"],
        aspect_ratio=row["aspect_ratio"],
        duration_sec=row["duration_sec"],
        status=row["status"],
        assigned_profile_id=row["assigned_profile_id"],
        priority=row["priority"],
        retry_count=row["retry_count"],
        max_retries=row["max_retries"],
        require_clean_watermark=bool(row["require_clean_watermark"]),
        submit_time=row["submit_time"],
        start_time=row["start_time"],
        finish_time=row["finish_time"],
        output_video_path=row["output_video_path"],
        output_image_paths=output_image_paths,
        first_frame_ncc=row["first_frame_ncc"],
        last_frame_ncc=row["last_frame_ncc"],
        last_vs_start_ncc=row["last_vs_start_ncc"],
        first_frame_matched=bool(row["first_frame_matched"]) if row["first_frame_matched"] is not None else None,
        last_frame_matched=bool(row["last_frame_matched"]) if row["last_frame_matched"] is not None else None,
        watermark_check=row["watermark_check"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        logs=row["logs"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        engine=engine,
        task_type=task_type,
        model=model
    )
    return t

# --- Profile operations ---

def add_profile(profile: Profile, db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            INSERT INTO profiles (
                id, name, profile_path, account_label, status, watermark_mode,
                last_heartbeat_at, last_success_at, last_failure_at, cooldown_until,
                enabled, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile.id, profile.name, profile.profile_path, profile.account_label,
                profile.status, profile.watermark_mode, profile.last_heartbeat_at,
                profile.last_success_at, profile.last_failure_at, profile.cooldown_until,
                1 if profile.enabled else 0, profile.notes, profile.created_at, profile.updated_at
            ))
    finally:
        conn.close()

def list_profiles(db_path: Path = DEFAULT_DB_PATH) -> List[Profile]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT * FROM profiles ORDER BY name ASC").fetchall()
            return [row_to_profile(r) for r in rows]
    finally:
        conn.close()

def get_profile_by_id(profile_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Profile]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
            return row_to_profile(row) if row else None
    finally:
        conn.close()

def get_profile_by_name(name: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Profile]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM profiles WHERE name = ?", (name,)).fetchone()
            return row_to_profile(row) if row else None
    finally:
        conn.close()

def update_profile_status(
    profile_id: str,
    status: str,
    cooldown_until: Optional[str] = None,
    success: Optional[bool] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            updates = ["status = ?", "updated_at = ?"]
            params = [status, now]

            if cooldown_until is not None:
                updates.append("cooldown_until = ?")
                params.append(cooldown_until)
            elif status == "idle":
                updates.append("cooldown_until = NULL")

            if success is True:
                updates.append("last_success_at = ?")
                params.append(now)
            elif success is False:
                updates.append("last_failure_at = ?")
                params.append(now)

            params.append(profile_id)
            conn.execute(f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?", params)
    finally:
        conn.close()

def acquire_idle_profile(
    require_clean: bool = False,
    profile_id: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> Optional[Profile]:
    now = datetime.now().astimezone().isoformat()
    conn = get_db_connection(db_path)
    try:
        with conn:
            query = """
            SELECT * FROM profiles
            WHERE enabled = 1
              AND status = 'idle'
              AND (cooldown_until IS NULL OR cooldown_until <= ?)
            """
            params = [now]
            if profile_id:
                query += " AND id = ?"
                params.append(profile_id)
            elif require_clean:
                query += " AND watermark_mode = 'clean'"

            query += """
            ORDER BY
                CASE WHEN last_success_at IS NULL THEN 0 ELSE 1 END,
                last_success_at ASC,
                created_at ASC
            LIMIT 1
            """
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            
            prof = row_to_profile(row)
            conn.execute(
                "UPDATE profiles SET status = 'busy', updated_at = ? WHERE id = ? AND status = 'idle'",
                (now, prof.id)
            )
            return prof
    finally:
        conn.close()

# --- Task operations ---

def add_task(task: Task, db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    engine = getattr(task, "engine", "flow") or "flow"
    task_type = getattr(task, "task_type", "video") or "video"
    model = getattr(task, "model", "") or ""
    output_image_paths = getattr(task, "output_image_paths", None)
    try:
        with conn:
            conn.execute("""
            INSERT INTO tasks (
                id, project_id, prompt, start_image_path, end_image_path, aspect_ratio,
                duration_sec, status, assigned_profile_id, priority, retry_count,
                max_retries, require_clean_watermark, submit_time, created_at, updated_at, engine,
                task_type, model, output_image_paths
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.project_id, task.prompt, task.start_image_path, task.end_image_path,
                task.aspect_ratio, task.duration_sec, task.status, task.assigned_profile_id,
                task.priority, task.retry_count, task.max_retries, 1 if task.require_clean_watermark else 0,
                task.submit_time, task.created_at, task.updated_at, engine,
                task_type, model, output_image_paths
            ))
    finally:
        conn.close()

def get_task_by_id(task_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Task]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return row_to_task(row) if row else None
    finally:
        conn.close()

def list_tasks(status: Optional[str] = None, limit: int = 100, db_path: Path = DEFAULT_DB_PATH) -> List[Task]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY submit_time DESC LIMIT ?",
                    (status, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY submit_time DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [row_to_task(r) for r in rows]
    finally:
        conn.close()

def update_task_status(
    task_id: str,
    status: str,
    assigned_profile_id: Optional[str] = None,
    clear_assigned_profile: bool = False,
    output_video_path: Optional[str] = None,
    output_image_paths: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    logs: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            updates = ["status = ?", "updated_at = ?"]
            params = [status, now]

            if status == "running":
                updates.append("start_time = ?")
                params.append(now)
            elif status in ("completed", "failed", "cancelled"):
                updates.append("finish_time = ?")
                params.append(now)

            if clear_assigned_profile:
                updates.append("assigned_profile_id = NULL")
            elif assigned_profile_id:
                updates.append("assigned_profile_id = ?")
                params.append(assigned_profile_id)

            if output_video_path:
                updates.append("output_video_path = ?")
                params.append(output_video_path)

            if output_image_paths is not None:
                updates.append("output_image_paths = ?")
                params.append(output_image_paths)

            if error_code is not None:
                updates.append("error_code = ?")
                params.append(error_code)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if logs is not None:
                updates.append("logs = ?")
                params.append(logs)

            params.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
    finally:
        conn.close()

def record_task_verification(
    task_id: str,
    first_frame_ncc: Optional[float],
    first_frame_matched: Optional[bool],
    last_frame_ncc: Optional[float],
    last_frame_matched: Optional[bool],
    last_vs_start_ncc: Optional[float],
    watermark_check: Optional[str],
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            conn.execute("""
            UPDATE tasks SET
                first_frame_ncc = ?,
                first_frame_matched = ?,
                last_frame_ncc = ?,
                last_frame_matched = ?,
                last_vs_start_ncc = ?,
                watermark_check = ?,
                updated_at = ?
            WHERE id = ?
            """, (
                first_frame_ncc,
                1 if first_frame_matched else 0 if first_frame_matched is not None else None,
                last_frame_ncc,
                1 if last_frame_matched else 0 if last_frame_matched is not None else None,
                last_vs_start_ncc,
                watermark_check,
                now,
                task_id
            ))
    finally:
        conn.close()

def log_task_event(task_id: str, event_type: str, detail: str = "", db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(task_events)").fetchall()]
            data = {"task_id": task_id, "event_type": event_type}
            if "detail" in cols:
                data["detail"] = detail
            if "message" in cols:
                data["message"] = detail
            if "created_at" in cols:
                data["created_at"] = now
            if "timestamp" in cols:
                data["timestamp"] = now
            
            keys = list(data.keys())
            placeholders = ", ".join(["?"] * len(keys))
            col_names = ", ".join(keys)
            conn.execute(f"INSERT INTO task_events ({col_names}) VALUES ({placeholders})", [data[k] for k in keys])
    finally:
        conn.close()

def list_task_events(task_id: str, db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC", (task_id,)).fetchall()
            res = []
            for r in rows:
                keys = r.keys()
                created = r["created_at"] if "created_at" in keys and r["created_at"] else (r["timestamp"] if "timestamp" in keys else "")
                msg = r["detail"] if "detail" in keys and r["detail"] else (r["message"] if "message" in keys else "")
                res.append({
                    "id": r["id"],
                    "task_id": r["task_id"],
                    "event_type": r["event_type"],
                    "message": msg,
                    "detail": msg,
                    "timestamp": created,
                    "created_at": created
                })
            return res
    finally:
        conn.close()

def get_next_queued_task(db_path: Path = DEFAULT_DB_PATH) -> Optional[Task]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("""
            SELECT * FROM tasks
            WHERE status = 'queued'
            ORDER BY priority DESC, submit_time ASC
            LIMIT 1
            """).fetchone()
            return row_to_task(row) if row else None
    finally:
        conn.close()

# Backward compatibility aliases
get_task = get_task_by_id
get_profile = get_profile_by_id
