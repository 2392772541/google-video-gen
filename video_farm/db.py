from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import uuid
from .models import Task, Profile

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "video_farm_data/tasks.db"

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
                task_type TEXT DEFAULT 'video', -- 'video', 'image', 'audio'
                model TEXT DEFAULT '',
                input_video_path TEXT DEFAULT '',
                output_image_paths TEXT,
                output_audio_path TEXT,
                FOREIGN KEY(assigned_profile_id) REFERENCES profiles(id)
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS vids_workflows (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                doc_url TEXT,
                style_prompt TEXT,
                aspect_ratio TEXT DEFAULT '16:9',
                duration_per_shot INTEGER DEFAULT 10,
                resolution TEXT DEFAULT '1080p',
                model_name TEXT DEFAULT 'Omni',
                engine TEXT DEFAULT 'vids',
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS vids_shots (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                sequence INTEGER DEFAULT 1,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                narration TEXT,
                duration INTEGER DEFAULT 10,
                scene_index INTEGER,
                mode TEXT DEFAULT 'text2video',
                image_url TEXT DEFAULT '',
                end_image_url TEXT DEFAULT '',
                resolution TEXT DEFAULT '1080p',
                model_name TEXT DEFAULT 'Omni',
                engine TEXT DEFAULT 'vids',
                status TEXT DEFAULT 'pending',
                progress INTEGER DEFAULT 0,
                video_url TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(workflow_id) REFERENCES vids_workflows(id) ON DELETE CASCADE
            )
            """)


            conn.execute("""
            CREATE TABLE IF NOT EXISTS gemini_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT 'default',
                profile_id TEXT,
                profile_name TEXT,
                role TEXT NOT NULL, -- 'user', 'assistant'
                mode TEXT DEFAULT 'chat', -- 'chat', 'dubbing', 'image'
                content TEXT,
                attachments_json TEXT,
                audio_url TEXT,
                audio_path TEXT,
                image_urls_json TEXT,
                status TEXT DEFAULT 'completed',
                error_message TEXT,
                created_at TEXT NOT NULL
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gemini_messages_session ON gemini_messages(session_id, created_at)")

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
            if "input_video_path" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN input_video_path TEXT DEFAULT ''")
            if "output_audio_path" not in cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN output_audio_path TEXT")

            # Ensure columns exist in vids_workflows
            vids_wf_cols = [r["name"] for r in conn.execute("PRAGMA table_info(vids_workflows)").fetchall()]
            if "resolution" not in vids_wf_cols:
                conn.execute("ALTER TABLE vids_workflows ADD COLUMN resolution TEXT DEFAULT '1080p'")
            if "model_name" not in vids_wf_cols:
                conn.execute("ALTER TABLE vids_workflows ADD COLUMN model_name TEXT DEFAULT 'Omni'")
            if "engine" not in vids_wf_cols:
                conn.execute("ALTER TABLE vids_workflows ADD COLUMN engine TEXT DEFAULT 'vids'")

            # Ensure columns exist in vids_shots
            vids_shot_cols = [r["name"] for r in conn.execute("PRAGMA table_info(vids_shots)").fetchall()]
            if "mode" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN mode TEXT DEFAULT 'text2video'")
            if "image_url" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN image_url TEXT DEFAULT ''")
            if "end_image_url" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN end_image_url TEXT DEFAULT ''")
            if "resolution" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN resolution TEXT DEFAULT '1080p'")
            if "model_name" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN model_name TEXT DEFAULT 'Omni'")
            if "task_id" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN task_id TEXT DEFAULT ''")
            if "local_video_path" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN local_video_path TEXT DEFAULT ''")
            if "engine" not in vids_shot_cols:
                conn.execute("ALTER TABLE vids_shots ADD COLUMN engine TEXT DEFAULT 'vids'")

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
    input_video_path = row_dict.get("input_video_path", "") or ""
    output_image_paths = row_dict.get("output_image_paths")
    output_audio_path = row_dict.get("output_audio_path")
    t = Task(
        id=row["id"],
        project_id=row["project_id"] or "",
        prompt=row["prompt"],
        start_image_path=row["start_image_path"],
        end_image_path=row["end_image_path"],
        input_video_path=input_video_path,
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
        model=model,
        output_audio_path=output_audio_path
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
                CASE
                    WHEN last_failure_at IS NOT NULL AND (last_success_at IS NULL OR last_failure_at > last_success_at) THEN 1
                    ELSE 0
                END ASC,
                MAX(COALESCE(last_success_at, '1970-01-01'), COALESCE(last_failure_at, '1970-01-01')) ASC,
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

def pick_best_profile(
    require_clean: bool = False,
    db_path: Path = DEFAULT_DB_PATH
) -> Optional[Profile]:
    """只读查询：挑选当前最健康、就绪的主账号（用于整批任务锁定指定，不改变 busy 状态）"""
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
                CASE WHEN watermark_mode = 'clean' THEN 0 ELSE 1 END ASC,
                CASE
                    WHEN last_failure_at IS NOT NULL AND (last_success_at IS NULL OR last_failure_at > last_success_at) THEN 1
                    ELSE 0
                END ASC,
                MAX(COALESCE(last_success_at, '1970-01-01'), COALESCE(last_failure_at, '1970-01-01')) ASC,
                created_at ASC
            LIMIT 1
            """
            row = conn.execute(query, params).fetchone()
            if row:
                return row_to_profile(row)
            
            fallback = conn.execute("SELECT * FROM profiles WHERE enabled = 1 ORDER BY CASE WHEN watermark_mode = 'clean' THEN 0 ELSE 1 END ASC, created_at ASC LIMIT 1").fetchone()
            return row_to_profile(fallback) if fallback else None
    finally:
        conn.close()


# --- Task operations ---

def add_task(task: Task, db_path: Path = DEFAULT_DB_PATH) -> None:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    engine = getattr(task, "engine", "flow") or "flow"
    task_type = getattr(task, "task_type", "video") or "video"
    model = getattr(task, "model", "") or ""
    input_video_path = getattr(task, "input_video_path", "") or ""
    output_image_paths = getattr(task, "output_image_paths", None)
    output_audio_path = getattr(task, "output_audio_path", None)
    try:
        with conn:
            conn.execute("""
            INSERT INTO tasks (
                id, project_id, prompt, start_image_path, end_image_path, aspect_ratio,
                duration_sec, status, assigned_profile_id, priority, retry_count,
                max_retries, require_clean_watermark, submit_time, created_at, updated_at, engine,
                task_type, model, input_video_path, output_image_paths, output_audio_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.project_id, task.prompt, task.start_image_path, task.end_image_path,
                task.aspect_ratio, task.duration_sec, task.status, task.assigned_profile_id,
                task.priority, task.retry_count, task.max_retries, 1 if task.require_clean_watermark else 0,
                task.submit_time, task.created_at, task.updated_at, engine,
                task_type, model, input_video_path, output_image_paths, output_audio_path
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

def list_tasks(status: Optional[str] = None, limit: int = 100, db_path: Path = DEFAULT_DB_PATH, offset: int = 0) -> List[Task]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY submit_time DESC, id DESC LIMIT ? OFFSET ?",
                    (status, limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY submit_time DESC, id DESC LIMIT ? OFFSET ?",
                    (limit, offset)
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
    output_audio_path: Optional[str] = None,
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

            if output_audio_path is not None:
                updates.append("output_audio_path = ?")
                params.append(output_audio_path)

            if error_code is not None:
                updates.append("error_code = ?")
                params.append(error_code)
            elif status == "completed":
                updates.append("error_code = NULL")

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)
            elif status == "completed":
                updates.append("error_message = NULL")

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


# --- Google Vids Workflow DB Operations ---

def create_vids_workflow(
    title: str,
    doc_url: str = "",
    style_prompt: str = "",
    aspect_ratio: str = "16:9",
    duration_per_shot: int = 10,
    resolution: str = "1080p",
    model_name: str = "Omni",
    workflow_id: Optional[str] = None,
    engine: str = "vids",
    db_path: Path = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    import uuid
    init_db(db_path)
    wf_id = workflow_id or f"vw_{uuid.uuid4().hex[:10]}"
    now = datetime.now().astimezone().isoformat()
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO vids_workflows (id, title, doc_url, style_prompt, aspect_ratio, duration_per_shot, resolution, model_name, engine, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
            """, (wf_id, title, doc_url, style_prompt, aspect_ratio, duration_per_shot, resolution, model_name, engine or "vids", now, now))
        return get_vids_workflow(wf_id, db_path=db_path)
    finally:
        conn.close()


def sync_shot_with_task(shot_dict: Dict[str, Any], conn: sqlite3.Connection) -> Dict[str, Any]:
    t_id = shot_dict.get("task_id")
    if not t_id:
        if shot_dict.get("video_url") and shot_dict.get("status") != "completed":
            shot_dict["status"] = "completed"
            shot_dict["progress"] = 100
            conn.execute("UPDATE vids_shots SET status = 'completed', progress = 100 WHERE id = ?", (shot_dict["id"],))
        return shot_dict
    t_row = conn.execute("SELECT status, output_video_path, error_message FROM tasks WHERE id = ?", (t_id,)).fetchone()
    if not t_row:
        return shot_dict
    
    t_status = t_row["status"]
    t_out = t_row["output_video_path"]
    t_err = t_row["error_message"]
    updates = {}
    
    if t_status == "completed":
        if shot_dict.get("status") != "completed":
            updates["status"] = "completed"
            updates["progress"] = 100
        if t_out:
            p_out = Path(t_out)
            v_url = f"/media/outputs/{p_out.name}"
            if shot_dict.get("video_url") != v_url:
                updates["video_url"] = v_url
            try:
                local_path_str = str(p_out.resolve())
            except Exception:
                local_path_str = str(p_out)
            if shot_dict.get("local_video_path") != local_path_str:
                updates["local_video_path"] = local_path_str
            shot_dict["local_video_path"] = local_path_str
        elif shot_dict.get("video_url") and not shot_dict.get("local_video_path"):
            v_val = shot_dict.get("video_url")
            if v_val.startswith("/media/outputs/"):
                fname = v_val.split("/media/outputs/")[-1]
                local_p = Path("video_farm_data/outputs") / fname
                if local_p.exists():
                    shot_dict["local_video_path"] = str(local_p.resolve())
        if shot_dict.get("error_message"):
            updates["error_message"] = ""
    elif t_status in ("running", "dispatching", "verifying"):
        if shot_dict.get("status") != "running":
            updates["status"] = "running"
        prog = 50 if t_status == "running" else (90 if t_status == "verifying" else 15)
        if (shot_dict.get("progress") or 0) < prog:
            updates["progress"] = prog
    elif t_status == "queued":
        if shot_dict.get("status") != "running":
            updates["status"] = "running"
            updates["progress"] = 5
    elif t_status == "failed":
        if shot_dict.get("status") == "pending":
            updates["task_id"] = ""
            updates["error_message"] = ""
        elif shot_dict.get("status") != "failed":
            updates["status"] = "failed"
            updates["error_message"] = t_err or "视频生成失败"
    elif t_status == "retry_wait":
        if shot_dict.get("status") != "running":
            updates["status"] = "running"
        updates["error_message"] = t_err or "调度避让重试中..."
    elif t_status == "cancelled":
        if shot_dict.get("status") != "pending":
            updates["status"] = "pending"
            updates["progress"] = 0
            updates["error_message"] = t_err or "任务已中断，点击即可重新生成"
            updates["task_id"] = ""
        
    if updates:
        now = datetime.now().astimezone().isoformat()
        updates["updated_at"] = now
        flds = [f"{k} = ?" for k in updates.keys()]
        vals = list(updates.values()) + [shot_dict["id"]]
        conn.execute(f"UPDATE vids_shots SET {', '.join(flds)} WHERE id = ?", vals)
        shot_dict.update(updates)
        
    return shot_dict
def get_vids_workflow(workflow_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM vids_workflows WHERE id = ?", (workflow_id,)).fetchone()
            if not row:
                return None
            wf = dict(row)
            shots = conn.execute("SELECT * FROM vids_shots WHERE workflow_id = ? ORDER BY sequence ASC", (workflow_id,)).fetchall()
            wf["shots"] = [sync_shot_with_task(dict(s), conn) for s in shots]
            return wf
    finally:
        conn.close()

def list_vids_workflows(db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    init_db(db_path)
    conn = get_db_connection(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT * FROM vids_workflows ORDER BY updated_at DESC").fetchall()
            res = []
            for r in rows:
                wf = dict(r)
                shots = conn.execute("SELECT * FROM vids_shots WHERE workflow_id = ?", (wf["id"],)).fetchall()
                synced_shots = [sync_shot_with_task(dict(s), conn) for s in shots]
                wf["total_shots"] = len(synced_shots)
                wf["completed_shots"] = sum(1 for s in synced_shots if s["status"] == "completed")
                res.append(wf)
            return res
    finally:
        conn.close()

def update_vids_workflow(workflow_id: str, updates: Dict[str, Any], db_path: Path = DEFAULT_DB_PATH):
    now = datetime.now().astimezone().isoformat()
    updates["updated_at"] = now
    fields = [f"{k} = ?" for k in updates.keys()]
    values = list(updates.values()) + [workflow_id]
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(f"UPDATE vids_workflows SET {', '.join(fields)} WHERE id = ?", values)
    finally:
        conn.close()

def delete_vids_workflow(workflow_id: str, db_path: Path = DEFAULT_DB_PATH):
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM vids_shots WHERE workflow_id = ?", (workflow_id,))
            conn.execute("DELETE FROM vids_workflows WHERE id = ?", (workflow_id,))
    finally:
        conn.close()

def create_vids_shot(
    workflow_id: str,
    name: str,
    prompt: str,
    narration: str = "",
    duration: int = 10,
    sequence: int = 1,
    scene_index: Optional[int] = None,
    mode: str = "text2video",
    image_url: str = "",
    end_image_url: str = "",
    resolution: str = "1080p",
    model_name: str = "Omni",
    task_id: str = "",
    shot_id: Optional[str] = None,
    engine: str = "vids",
    db_path: Path = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    import uuid
    sid = shot_id or f"vs_{uuid.uuid4().hex[:10]}"
    now = datetime.now().astimezone().isoformat()
    s_idx = scene_index or sequence
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("""
                INSERT INTO vids_shots (id, workflow_id, sequence, name, prompt, narration, duration, scene_index, mode, image_url, end_image_url, resolution, model_name, engine, status, progress, task_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?)
            """, (sid, workflow_id, sequence, name, prompt, narration, duration, s_idx, mode, image_url, end_image_url, resolution, model_name, engine or "vids", task_id, now, now))
            row = conn.execute("SELECT * FROM vids_shots WHERE id = ?", (sid,)).fetchone()
            return dict(row)
    finally:
        conn.close()

def list_vids_shots(workflow_id: str, db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT * FROM vids_shots WHERE workflow_id = ? ORDER BY sequence ASC", (workflow_id,)).fetchall()
            return [sync_shot_with_task(dict(r), conn) for r in rows]
    finally:
        conn.close()

def update_vids_shot(shot_id: str, updates: Dict[str, Any], db_path: Path = DEFAULT_DB_PATH):
    now = datetime.now().astimezone().isoformat()
    updates["updated_at"] = now
    fields = [f"{k} = ?" for k in updates.keys()]
    values = list(updates.values()) + [shot_id]
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(f"UPDATE vids_shots SET {', '.join(fields)} WHERE id = ?", values)
    finally:
        conn.close()

def get_vids_shot(shot_id: str, db_path: Path = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        with conn:
            row = conn.execute("SELECT * FROM vids_shots WHERE id = ?", (shot_id,)).fetchone()
            if not row:
                return None
            return sync_shot_with_task(dict(row), conn)
    finally:
        conn.close()

def delete_vids_shot(shot_id: str, db_path: Path = DEFAULT_DB_PATH):
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM vids_shots WHERE id = ?", (shot_id,))
    finally:
        conn.close()


def delete_task(task_id: str, delete_files: bool = True, db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Remove a terminal/queued record; quarantine only unshared managed outputs.

    Original inputs and external files are never deleted. A manifest contains the
    full record and events. File failures roll back both moves and SQL changes.
    """
    import json, shutil, uuid
    if not task_id or Path(task_id).name != task_id or task_id in (".", "..") or any(c in task_id for c in "/\\:"):
        raise TaskOperationConflict("非法任务ID")
    root = Path(db_path).resolve().parent
    conn = get_db_connection(db_path)
    moved, skipped = [], []
    trash = root / "trash" / (task_id + "_" + uuid.uuid4().hex[:12])
    committed = False
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return {"id":task_id, "deleted":False, "removed_files":[]}
            if row["status"] in ("dispatching", "running", "verifying"):
                raise TaskOperationConflict("运行中任务不能删除，请等待生成与质检结束")
            record = dict(row)
            others = [dict(r) for r in conn.execute("SELECT * FROM tasks WHERE id<>?", (task_id,))]
            shots = [dict(r) for r in conn.execute("SELECT * FROM vids_shots")]
            # Conservative matching also protects workflow URLs and image references.
            reference_text = json.dumps(others + shots, ensure_ascii=False).replace("\\\\", "/").lower()
            candidates = []
            for field in ("output_video_path", "output_audio_path"):
                if record.get(field): candidates.append(Path(record[field]).resolve())
            if record.get("output_image_paths"):
                try:
                    images = json.loads(record["output_image_paths"])
                    if isinstance(images, list): candidates.extend(Path(i).resolve() for i in images if isinstance(i,str))
                except (ValueError, TypeError):
                    skipped.append({"path":record["output_image_paths"], "reason":"invalid image list; retained"})
            qa = (root / "qa" / task_id).resolve()
            if qa.is_relative_to(root / "qa") and qa.is_dir():
                candidates.extend(f.resolve() for f in qa.rglob("*") if f.is_file())
            if delete_files:
                for source in dict.fromkeys(candidates):
                    if not source.is_file(): continue
                    managed = any(source.is_relative_to((root / d).resolve()) for d in ("outputs", "qa"))
                    if not managed:
                        skipped.append({"path":str(source), "reason":"external/original file retained"}); continue
                    if source.as_posix().lower() in reference_text or source.name.lower() in reference_text:
                        skipped.append({"path":str(source), "reason":"referenced by another task/workflow; retained"}); continue
                    target = trash / "files" / source.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(target))
                    moved.append({"source":str(source), "target":str(target)})
            events = [dict(r) for r in conn.execute("SELECT * FROM task_events WHERE task_id=?",(task_id,))]
            trash.mkdir(parents=True, exist_ok=True)
            manifest = {"task":record,"events":events,"linked_shots":[r for r in shots if r.get("task_id")==task_id], "moved_files":moved,"skipped_files":skipped,"original_uploads_retained":True}
            (trash / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            conn.execute("DELETE FROM task_events WHERE task_id=?", (task_id,))
            conn.execute("UPDATE vids_shots SET task_id=NULL, status='planned' WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        committed = True
        return {"id":task_id,"deleted":True,"removed_files":[m["source"] for m in moved],"skipped_files":skipped,"trash_path":str(trash),"recoverable":True}
    finally:
        conn.close()
        if not committed:
            for item in reversed(moved):
                if Path(item["target"]).exists():
                    Path(item["source"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(item["target"],item["source"])
            if trash.is_dir():
                # This unique directory was created by this operation only.
                if trash.resolve().is_relative_to((root / "trash").resolve()): shutil.rmtree(trash)


def batch_delete_tasks(task_ids: List[str], delete_files: bool = True, db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    results = []
    deleted_count = 0
    all_removed = []
    for tid in dict.fromkeys(task_ids):
        try:
            r = delete_task(tid, delete_files=delete_files, db_path=db_path)
        except (TaskOperationConflict, OSError) as e:
            r = {"id":tid, "deleted":False, "error":str(e)}
        if r.get("deleted"):
            deleted_count += 1
            all_removed.extend(r.get("removed_files", []))
        results.append(r)
    return {
        "success": all(r.get("deleted") for r in results),
        "requested_count": len(set(task_ids)),
        "deleted_count": deleted_count,
        "removed_files_count": len(all_removed),
        "results": results
    }

class TaskOperationConflict(ValueError):
    """The worker or a terminal task must not be overwritten by a UI action."""

def task_statistics(db_path: Path = DEFAULT_DB_PATH, status=None) -> Dict[str, int]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute('SELECT status, COUNT(*) AS n FROM tasks' + (' WHERE status=?' if status else '') + ' GROUP BY status', (status,) if status else ()).fetchall()
        counts = {r['status']: r['n'] for r in rows}
        return {'total':sum(counts.values()), 'queued':counts.get('queued',0)+counts.get('retry_wait',0), 'running':sum(counts.get(s,0) for s in ('running','dispatching','verifying')), **{s:counts.get(s,0) for s in ('completed','failed','cancelled')}}
    finally:
        conn.close()

def claim_task(task_id: str, profile_id: str, db_path: Path = DEFAULT_DB_PATH) -> bool:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            return conn.execute("UPDATE tasks SET status='running', assigned_profile_id=?, start_time=?, finish_time=NULL, updated_at=? WHERE id=? AND status='queued'", (profile_id,now,now,task_id)).rowcount == 1
    finally:
        conn.close()

def transition_task(task_id: str, action: str, db_path: Path = DEFAULT_DB_PATH):
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            if row is None:
                raise KeyError(task_id)
            if action == 'retry':
                if row['status'] not in ('failed','cancelled','retry_wait'):
                    raise TaskOperationConflict('仅失败、已取消或等待重试的任务可重新排队；运行中任务不能重置')
                if row['error_code'] in ('WIRE_FORMAT_MISMATCH','UNSUPPORTED_FEATURE'):
                    raise TaskOperationConflict('模型或请求参数不兼容，请修正参数后创建新任务；换号不能解决此问题')
                # Preserve explicit profile binding; never silently switch a pinned account.
                conn.execute("UPDATE tasks SET status='queued', retry_count=0, error_code=NULL, error_message=NULL, start_time=NULL, finish_time=NULL, updated_at=? WHERE id=?",(now,task_id))
                status='queued'
            elif action == 'cancel':
                if row['status'] == 'cancelled':
                    return {'id':task_id,'status':'cancelled'}
                if row['status'] not in ('queued','retry_wait'):
                    raise TaskOperationConflict('只能取消尚未执行的任务；运行中不能安全强制中断，请等待完成')
                conn.execute("UPDATE tasks SET status='cancelled', finish_time=?, updated_at=? WHERE id=?",(now,now,task_id))
                status='cancelled'
            else:
                raise ValueError('Unknown task action')
            conn.execute('INSERT INTO task_events(task_id,event_type,detail,created_at,message,timestamp) VALUES(?,?,?,?,?,?)',(task_id,'MANUAL_'+action.upper(),'Web状态转换',now,'Web状态转换',now))
        return {'id':task_id,'status':status}
    finally:
        conn.close()


def add_gemini_message(msg: dict, db_path: Path = DEFAULT_DB_PATH) -> dict:
    conn = get_db_connection(db_path)
    now = datetime.now().astimezone().isoformat()
    msg_id = msg.get("id") or f"gmsg_{uuid.uuid4().hex[:12]}"
    created_at = msg.get("created_at") or now
    try:
        with conn:
            conn.execute("""
                INSERT INTO gemini_messages (
                    id, session_id, profile_id, profile_name, role, mode,
                    content, attachments_json, audio_url, audio_path,
                    image_urls_json, status, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg_id,
                msg.get("session_id", "default"),
                msg.get("profile_id"),
                msg.get("profile_name"),
                msg.get("role", "user"),
                msg.get("mode", "chat"),
                msg.get("content", ""),
                msg.get("attachments_json", "[]"),
                msg.get("audio_url"),
                msg.get("audio_path"),
                msg.get("image_urls_json", "[]"),
                msg.get("status", "completed"),
                msg.get("error_message"),
                created_at
            ))
        res = dict(msg)
        res["id"] = msg_id
        res["created_at"] = created_at
        return res
    finally:
        conn.close()

def list_gemini_messages(session_id: str = "default", limit: int = 100, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT * FROM gemini_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (session_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def clear_gemini_messages(session_id: str = "default", db_path: Path = DEFAULT_DB_PATH) -> int:
    conn = get_db_connection(db_path)
    try:
        with conn:
            return conn.execute("DELETE FROM gemini_messages WHERE session_id = ?", (session_id,)).rowcount
    finally:
        conn.close()

def list_gemini_images(db_path: Path = DEFAULT_DB_PATH, limit: int = 60) -> list[dict]:
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute("""
            SELECT id, session_id, profile_id, profile_name, content, image_urls_json, created_at
            FROM gemini_messages
            WHERE image_urls_json IS NOT NULL AND image_urls_json != '[]' AND image_urls_json != ''
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        images = []
        for r in rows:
            try:
                urls = json.loads(r["image_urls_json"]) if r["image_urls_json"] else []
                for url in urls:
                    images.append({
                        "message_id": r["id"],
                        "url": url,
                        "prompt": r["content"],
                        "profile_name": r["profile_name"] or "Gemini",
                        "created_at": r["created_at"]
                    })
            except Exception:
                pass
        return images
    finally:
        conn.close()
