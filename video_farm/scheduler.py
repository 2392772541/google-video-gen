from __future__ import annotations
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from .models import Task, Profile
from . import db
from .worker import VideoWorker
from .gemini_worker import GeminiWebWorker
from .verify import verify_task_video

def classify_failure(err_code: str, err_msg: str, logs: str) -> tuple[str, str, int, bool]:
    """
    ?????????
    ??: (reason_category, friendly_message, cooldown_seconds, count_as_task_retry)
    - QUOTA_EXHAUSTED: ???? -> ??8???????????????????
    - RATE_LIMITED: ????/429 -> ??20???????????????????
    - AUTH_EXPIRED: ????/??? -> ???????????????????????
    - GENERAL_ERROR: ???? -> ??60??????????
    """
    code_up = (err_code or "").upper()
    content = f"{err_code} {err_msg} {logs}".lower()
    
    # 1. ??????? (401 Unauthorized, Session Expired, etc.)
    if code_up == "AUTH_EXPIRED" or any(k in content for k in [
        "auth_expired", "authexpirederror", "auth-expired", "authentication expired", "unauthorized",
        "sign in", "login required", "auth_failed", "cookie expired", "unauthenticated",
        "session expired", "not to the flow app", "status\": 401", "???", "??????",
        "?????", "?????", "401", "?????????????"
    ]):
        return (
            "AUTH_EXPIRED",
            "Google ??????????????????????????????????",
            86400,
            False
        )
        
    # 2. ?????? (Quota, Daily limit, Out of credits, Resource exhausted)
    if code_up == "QUOTA_EXHAUSTED" or any(k in content for k in [
        "quota_exhausted", "quota", "exhausted", "credit", "daily limit", "resource_exhausted",
        "limit reached", "out of credits", "try again tomorrow", "you've reached your limit",
        "????", "????", "??"
    ]):
        return (
            "QUOTA_EXHAUSTED",
            "?????????????????????????????????",
            28800,
            False
        )
        
    # 3. ????/???? (429, Unusual activity, Rate limit)
    if code_up == "RATE_LIMITED" or any(k in content for k in [
        "rate_limited", "unusual_activity", "rate_limit", "429", "too many requests",
        "public_error_unusual_activity", "??", "??", "????"
    ]):
        return (
            "RATE_LIMITED",
            "?? Google ??/????????? 20 ???????????????",
            1200,
            False
        )
        
    # 4. ?????? (?????????????)
    return ("GENERAL_ERROR", err_msg or "??????", 60, True)


class VideoScheduler:
    def __init__(
        self,
        db_path: Path = db.DEFAULT_DB_PATH,
        max_workers: int = 4,
        gflow_dir: Path = Path("gflow-cli"),
        output_dir: Path = Path("video_farm_data/outputs"),
        qa_dir: Path = Path("video_farm_data/qa"),
        worker_timeout_sec: int = 360,
        mock_sample_video: Optional[str] = None
    ):
        self.db_path = db_path
        self.gflow_dir = gflow_dir
        self.output_dir = output_dir
        self.qa_dir = qa_dir
        self.worker_timeout_sec = worker_timeout_sec
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="FarmWorker")
        
        # Flow 引擎与 Gemini 网页版引擎双轨实例化
        self.flow_worker = VideoWorker(
            gflow_dir=gflow_dir,
            output_dir=output_dir,
            timeout_sec=worker_timeout_sec,
            mock_sample_video=mock_sample_video
        )
        self.gemini_worker = GeminiWebWorker(
            output_dir=output_dir,
            timeout_sec=worker_timeout_sec,
            headless=True
        )
        
        self.active_tasks: Dict[str, threading.Event] = {}
        self.lock = threading.Lock()
        self.running = False

    def recover_cooldowns(self) -> None:
        """自动恢复冷却时间到期的 Profile 为 idle"""
        now = datetime.now().astimezone().isoformat()
        conn = db.get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("""
                UPDATE profiles
                SET status = 'idle', cooldown_until = NULL, updated_at = ?
                WHERE status = 'cooldown'
                  AND cooldown_until IS NOT NULL
                  AND cooldown_until <= ?
                """, (now, now))
        finally:
            conn.close()

    def process_task_execution(self, task: Task, profile: Profile) -> None:
        """工作线程主入口：执行单个任务并处理自适应质检与故障转移"""
        task_id = task.id
        profile_id = profile.id
        thread_name = threading.current_thread().name
        engine_name = getattr(task, "engine", "flow")
        
        try:
            engine_label = "Google Flow (首尾帧模式)" if engine_name == "flow" else "Gemini 网页版"
            db.log_task_event(
                task_id, "WORKER_START",
                f"[{thread_name}] 任务分配至 Profile [{profile.name}]，采用引擎: {engine_label}",
                db_path=self.db_path
            )

            # 根据任务类型派发到对应的 Worker
            if engine_name == "gemini":
                exec_res = self.gemini_worker.execute_task(task, profile)
            else:
                exec_res = self.flow_worker.execute_task(task, profile)

            pid = exec_res.get("pid")
            pid_str = f" (PID={pid})" if pid else ""

            # ---------------- 失败处理与智能熔断切换 (Failover) ----------------
            if not exec_res["success"]:
                raw_code = exec_res.get("error_code") or "EXEC_FAILED"
                raw_msg = exec_res.get("error_message") or "Unknown error"
                logs = exec_res.get("logs") or ""

                category, friendly_msg, cooldown_sec, count_retry = classify_failure(raw_code, raw_msg, logs)
                now_dt = datetime.now().astimezone()
                cooldown_until = (now_dt + timedelta(seconds=cooldown_sec)).isoformat()

                if category in ("AUTH_EXPIRED", "QUOTA_EXHAUSTED", "RATE_LIMITED"):
                    # 关键逻辑：如果是账号凭据失效、额度耗尽或频控，绝不消耗任务的 max_retries 额度！
                    # 而是将当前账号冷却/标记，并将任务直接重新投回 queued，自动寻找下一个可用账号
                    prof_new_status = "auth_expired" if category == "AUTH_EXPIRED" else "cooldown"
                    db.update_profile_status(
                        profile_id=profile_id,
                        status=prof_new_status,
                        cooldown_until=cooldown_until,
                        success=False,
                        db_path=self.db_path
                    )

                    failover_msg = f"⚡ 账号 [{profile.name}] {friendly_msg}。系统已将任务自动重置排队，正在无缝切换至下一个可用账号..."
                    db.update_task_status(
                        task_id=task_id,
                        status="queued",
                        clear_assigned_profile=True,  # 物理级解绑账号，允许其他账号接单
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "ACCOUNT_FAILOVER", failover_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {failover_msg}")
                    return

                # 普通错误处理
                can_retry = task.retry_count < task.max_retries
                new_status = "retry_wait" if can_retry else "failed"

                db.update_task_status(
                    task_id=task_id,
                    status=new_status,
                    error_code=raw_code,
                    error_message=friendly_msg,
                    logs=logs,
                    db_path=self.db_path
                )

                if can_retry:
                    conn = db.get_db_connection(self.db_path)
                    with conn:
                        conn.execute("UPDATE tasks SET retry_count = retry_count + 1 WHERE id = ?", (task_id,))
                    conn.close()
                    db.log_task_event(task_id, "RETRY_SCHEDULED", f"任务计划重试 ({task.retry_count + 1}/{task.max_retries}){pid_str}", db_path=self.db_path)

                db.update_profile_status(
                    profile_id=profile_id,
                    status="cooldown",
                    cooldown_until=cooldown_until,
                    success=False,
                    db_path=self.db_path
                )
                return

            # ---------------- 成功生成 -> 质检验收流程 ----------------
            video_path = exec_res["output_video_path"]
            db.update_task_status(
                task_id=task_id,
                status="verifying",
                output_video_path=video_path,
                logs=exec_res.get("logs") or "",
                db_path=self.db_path
            )
            db.log_task_event(task_id, "STATUS_VERIFYING", f"视频已生成{pid_str}，正在进行质检与帧提取", db_path=self.db_path)

            task_qa_dir = self.qa_dir / task_id

            if engine_name == "flow" and task.end_image_path and Path(task.end_image_path).exists():
                # Google Flow 首尾帧严格比对
                v_res = verify_task_video(
                    video_path=video_path,
                    start_image_path=task.start_image_path,
                    end_image_path=task.end_image_path,
                    qa_dir=task_qa_dir
                )
            else:
                # Gemini 网页版：检验视频合法性并提取首末帧展示
                v_res = verify_task_video(
                    video_path=video_path,
                    start_image_path=task.start_image_path if task.start_image_path and Path(task.start_image_path).exists() else None,
                    end_image_path=None,
                    qa_dir=task_qa_dir
                )

            db.record_task_verification(
                task_id=task_id,
                first_frame_ncc=v_res.get("first_ncc"),
                first_frame_matched=v_res.get("first_matched"),
                last_frame_ncc=v_res.get("last_ncc"),
                last_frame_matched=v_res.get("last_matched"),
                last_vs_start_ncc=v_res.get("last_vs_start_ncc"),
                watermark_check=v_res.get("watermark_status", "unknown"),
                db_path=self.db_path
            )

            if v_res["success"]:
                db.update_task_status(task_id=task_id, status="completed", db_path=self.db_path)
                db.update_profile_status(profile_id=profile_id, status="idle", success=True, db_path=self.db_path)

                if v_res["watermark_status"] == "visible_veo" and profile.watermark_mode == "unknown":
                    conn = db.get_db_connection(self.db_path)
                    with conn:
                        conn.execute("UPDATE profiles SET watermark_mode = 'forced_visible' WHERE id = ?", (profile_id,))
                    conn.close()
                elif v_res["watermark_status"] == "clean" and profile.watermark_mode == "unknown":
                    conn = db.get_db_connection(self.db_path)
                    with conn:
                        conn.execute("UPDATE profiles SET watermark_mode = 'clean' WHERE id = ?", (profile_id,))
                    conn.close()

                db.log_task_event(task_id, "TASK_COMPLETED", f"质检通过，成片完成: {video_path}", db_path=self.db_path)
            else:
                fail_reason = v_res.get("error") or "质检未达标"
                db.update_task_status(
                    task_id=task_id,
                    status="failed",
                    error_code="VERIFY_FAILED",
                    error_message=fail_reason,
                    db_path=self.db_path
                )
                db.update_profile_status(profile_id=profile_id, status="idle", success=False, db_path=self.db_path)
                db.log_task_event(task_id, "TASK_VERIFY_FAILED", fail_reason, db_path=self.db_path)

        except Exception as exc:
            db.update_task_status(
                task_id=task_id,
                status="failed",
                error_code="SCHEDULER_EXCEPTION",
                error_message=str(exc),
                db_path=self.db_path
            )
            db.update_profile_status(profile_id=profile_id, status="idle", success=False, db_path=self.db_path)
            db.log_task_event(task_id, "TASK_EXCEPTION", str(exc), db_path=self.db_path)
        finally:
            with self.lock:
                self.active_tasks.pop(task_id, None)

    def dispatch_cycle(self) -> int:
        """????????????????????????????"""
        self.recover_cooldowns()

        conn = db.get_db_connection(self.db_path)
        queued_tasks = []
        try:
            with conn:
                rows = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority DESC, submit_time ASC
                LIMIT 8
                """).fetchall()
                queued_tasks = [db.row_to_task(r) for r in rows]
        finally:
            conn.close()

        if not queued_tasks:
            # ????? retry_wait ????? queued
            conn = db.get_db_connection(self.db_path)
            try:
                with conn:
                    conn.execute("UPDATE tasks SET status = 'queued' WHERE status = 'retry_wait'")
            finally:
                conn.close()
            return 0

        dispatched = 0
        for task in queued_tasks:
            profile = db.acquire_idle_profile(require_clean=task.require_clean_watermark, db_path=self.db_path)
            if not profile:
                continue

            # ?????? running ??
            db.update_task_status(
                task_id=task.id,
                status="running",
                assigned_profile_id=profile.id,
                db_path=self.db_path
            )

            with self.lock:
                evt = threading.Event()
                self.active_tasks[task.id] = evt

            self.executor.submit(self.process_task_execution, task, profile)
            dispatched += 1
            break

        return dispatched

    def run_loop(self, poll_interval_sec: float = 3.0, stop_when_idle: bool = False) -> None:
        self.running = True
        print(f"[VideoScheduler] 调度器已启动 (轮询周期: {poll_interval_sec}s, 最大并发: {self.executor._max_workers})...")
        try:
            while self.running:
                dispatched = self.dispatch_cycle()
                if stop_when_idle:
                    with self.lock:
                        has_active = len(self.active_tasks) > 0
                    queued = db.get_next_queued_task(self.db_path)
                    if not has_active and not queued and dispatched == 0:
                        break
                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            print("[VideoScheduler] 接收到退出信号，正在停止...")
        finally:
            self.running = False
            self.executor.shutdown(wait=True)
            print("[VideoScheduler] 调度器已安全停止。")
