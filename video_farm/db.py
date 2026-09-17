from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from .models import Profile, Task

DEFAULT_DB_PATH = Path("video_farm_data/tasks.db")

def get_db_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn

def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                profile_path TEXT,
                account_label TEXT,
                status TEXT NOT NULL DEFAULT 'idle',
                watermark_mode TEXT NOT NULL DEFAULT 'unknown',
                last_heartbeat_at TEXT,
                last_success_at TEXT,
                last_failure_at TEXT,
                cooldown_until TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                prompt TEXT NOT NULL,
                start_image_path TEXT NOT NULL,
                end_image_path TEXT NOT NULL,
                engine TEXT NOT NULL DEFAULT 'flow',
                aspect_ratio TEXT NOT NULL DEFAULT '9:16',
                duration_sec INTEGER NOT NULL DEFAULT 8,
                status TEXT NOT NULL DEFAULT 'queued',
                assigned_profile_id TEXT,
                priority INTEGER NOT NULL DEFAULT 10,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                require_clean_watermark INTEGER NOT NULL DEFAULT 0,
                submit_time TEXT NOT NULL,
                start_time TEXT,
                finish_time TEXT,
                output_video_path TEXT,
                first_frame_ncc REAL,
                last_frame_ncc REAL,
                last_vs_start_ncc REAL,
                first_frame_matched INTEGER,
                last_frame_matched INTEGER,
                watermark_check TEXT DEFAULT 'unknown',
                error_code TEXT,
                error_message TEXT,
                logs TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (assigned_profile_id) REFERENCES profiles (id)
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT,
                payload_json TEXT,
                FOREIGN KEY (task_id) REFERENCES tasks (id)
            );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks (status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_status ON profiles (status, enabled);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events (task_id);")

            # Auto-migrate: check if engine column exists in tasks table
            cursor = conn.execute("PRAGMA table_info(tasks);")
            columns = [row[1] for row in cursor.fetchall()]
            if 'engine' not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN engine TEXT NOT NULL DEFAULT 'flow';")
    finally:
        conn.close()

# --- Profile operations ---

def add_profile(profile: Profile, db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            conn.execute("""
            INSERT INTO profiles (
                id, name, profile_path, account_label, status, watermark_mode,
                last_heartbeat_at, last_success_at, last_failure_at, cooldown_until,
                enabled, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                profile_path = excluded.profile_path,
                account_label = excluded.account_label,
                watermark_mode = excluded.watermark_mode,
                enabled = excluded.enabled,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """, (
                profile.id, profile.name, profile.profile_path, profile.account_label,
                profile.status, profile.watermark_mode, profile.last_heartbeat_at,
                profile.last_success_at, profile.last_failure_at, profile.cooldown_until,
                1 if profile.enabled else 0, profile.notes, profile.created_at or now, now
            ))
    finally:
        conn.close()

def get_profile_by_name(name: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Profile]:
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM profiles WHERE name = ?", (name,)).fetchone()
        if not row:
            return None
        return row_to_profile(row)
    finally:
        conn.close()

def get_profile_by_id(profile_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Profile]:
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
        if not row:
            return None
        return row_to_profile(row)
    finally:
        conn.close()

def list_profiles(db_path: Path = DEFAULT_DB_PATH) -> List[Profile]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM profiles ORDER BY name ASC").fetchall()
        return [row_to_profile(r) for r in rows]
    finally:
        conn.close()

def update_profile_status(
    profile_id: str,
    status: str,
    cooldown_until: Optional[str] = None,
    success: Optional[bool] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    now = datetime.now().astimezone().isoformat()
    conn = get_db_connection(db_path)
    try:
        with conn:
            updates = ["status = ?", "updated_at = ?"]
            params = [status, now]
            if cooldown_until is not None:
                updates.append("cooldown_until = ?")
                params.append(cooldown_until)
            if success is True:
                updates.append("last_success_at = ?")
                params.append(now)
                updates.append("cooldown_until = NULL")
            elif success is False:
                updates.append("last_failure_at = ?")
                params.append(now)

            params.append(profile_id)
            conn.execute(f"UPDATE profiles SET {', '.join(updates)} WHERE id = ?", params)
    finally:
        conn.close()

def acquire_idle_profile(require_clean: bool = False, db_path: Path = DEFAULT_DB_PATH) -> Optional[Profile]:
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
            if require_clean:
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
    try:
        with conn:
            conn.execute("""
            INSERT INTO tasks (
                id, project_id, prompt, start_image_path, end_image_path, engine,
                aspect_ratio, duration_sec, status, assigned_profile_id, priority,
                retry_count, max_retries, require_clean_watermark, submit_time,
                output_video_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.project_id, task.prompt, task.start_image_path, task.end_image_path, getattr(task, 'engine', 'flow'),
                task.aspect_ratio, task.duration_sec, task.status, task.assigned_profile_id, task.priority,
                task.retry_count, task.max_retries, 1 if task.require_clean_watermark else 0,
                task.submit_time or now, task.output_video_path, task.created_at or now, now
            ))
            log_task_event(task.id, "TASK_CREATED", f"Task created: {task.prompt[:40]}...", conn=conn)
    finally:
        conn.close()

def get_task(task_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Task]:
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return row_to_task(row)
    finally:
        conn.close()

def list_tasks(status: Optional[str] = None, limit: int = 50, db_path: Path = DEFAULT_DB_PATH) -> List[Task]:
    conn = get_db_connection(db_path)
    try:
        if status:
            rows = conn.execute("SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, submit_time ASC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks ORDER BY priority DESC, submit_time DESC LIMIT ?", (limit,)).fetchall()
        return [row_to_task(r) for r in rows]
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
            if not row:
                return None
            return row_to_task(row)
    finally:
        conn.close()

def update_task_status(
    task_id: str,
    status: str,
    assigned_profile_id: Optional[str] = None,
    clear_assigned_profile: bool = False,
    output_video_path: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    logs: Optional[str] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    now = datetime.now().astimezone().isoformat()
    conn = get_db_connection(db_path)
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
            elif assigned_profile_id is not None:
                updates.append("assigned_profile_id = ?")
                params.append(assigned_profile_id)
            if output_video_path is not None:
                updates.append("output_video_path = ?")
                params.append(output_video_path)
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
            log_task_event(task_id, f"STATUS_{status.upper()}", f"Status updated to {status}", conn=conn)
    finally:
        conn.close()

def record_task_verification(
    task_id: str,
    first_frame_ncc: float,
    last_frame_ncc: float,
    last_vs_start_ncc: float,
    first_frame_matched: bool,
    last_frame_matched: bool,
    watermark_check: str,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    now = datetime.now().astimezone().isoformat()
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
            UPDATE tasks SET
                first_frame_ncc = ?,
                last_frame_ncc = ?,
                last_vs_start_ncc = ?,
                first_frame_matched = ?,
                last_frame_matched = ?,
                watermark_check = ?,
                updated_at = ?
            WHERE id = ?
            """, (
                first_frame_ncc, last_frame_ncc, last_vs_start_ncc,
                1 if first_frame_matched else 0, 1 if last_frame_matched else 0,
                watermark_check, now, task_id
            ))
            log_task_event(
                task_id, "VERIFICATION_COMPLETED",
                f"First NCC: {first_frame_ncc:.4f}, Last NCC: {last_frame_ncc:.4f}, Watermark: {watermark_check}",
                payload={"first_ncc": first_frame_ncc, "last_ncc": last_frame_ncc, "watermark": watermark_check},
                conn=conn
            )
    finally:
        conn.close()

def log_task_event(
    task_id: str,
    event_type: str,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Path = DEFAULT_DB_PATH
) -> None:
    now = datetime.now().astimezone().isoformat()
    payload_str = json.dumps(payload, ensure_ascii=False) if payload else None
    if conn is not None:
        conn.execute("""
        INSERT INTO task_events (task_id, timestamp, event_type, message, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """, (task_id, now, event_type, message, payload_str))
    else:
        c = get_db_connection(db_path)
        try:
            with c:
                c.execute("""
                INSERT INTO task_events (task_id, timestamp, event_type, message, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """, (task_id, now, event_type, message, payload_str))
        finally:
            c.close()

def list_task_events(task_id: str, db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC", (task_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

# --- Helpers ---

def row_to_profile(r: sqlite3.Row) -> Profile:
    return Profile(
        id=r["id"],
        name=r["name"],
        profile_path=r["profile_path"] or "",
        account_label=r["account_label"] or "",
        status=r["status"],
        watermark_mode=r["watermark_mode"],
        last_heartbeat_at=r["last_heartbeat_at"],
        last_success_at=r["last_success_at"],
        last_failure_at=r["last_failure_at"],
        cooldown_until=r["cooldown_until"],
        enabled=bool(r["enabled"]),
        notes=r["notes"] or "",
        created_at=r["created_at"],
        updated_at=r["updated_at"]
    )

def row_to_task(r: sqlite3.Row) -> Task:
    col_keys = r.keys()
    return Task(
        id=r["id"],
        project_id=r["project_id"] or "",
        prompt=r["prompt"],
        start_image_path=r["start_image_path"] or "",
        end_image_path=r["end_image_path"] or "",
        engine=r["engine"] if "engine" in col_keys else "flow",
        aspect_ratio=r["aspect_ratio"],
        duration_sec=r["duration_sec"],
        status=r["status"],
        assigned_profile_id=r["assigned_profile_id"],
        priority=r["priority"],
        retry_count=r["retry_count"],
        max_retries=r["max_retries"],
        require_clean_watermark=bool(r["require_clean_watermark"]),
        submit_time=r["submit_time"],
        start_time=r["start_time"],
        finish_time=r["finish_time"],
        output_video_path=r["output_video_path"],
        first_frame_ncc=r["first_frame_ncc"],
        last_frame_ncc=r["last_frame_ncc"],
        last_vs_start_ncc=r["last_vs_start_ncc"],
        first_frame_matched=bool(r["first_frame_matched"]) if r["first_frame_matched"] is not None else None,
        last_frame_matched=bool(r["last_frame_matched"]) if r["last_frame_matched"] is not None else None,
        watermark_check=r["watermark_check"] or "unknown",
        error_code=r["error_code"],
        error_message=r["error_message"],
        logs=r["logs"] or "",
        created_at=r["created_at"],
        updated_at=r["updated_at"]
    )
