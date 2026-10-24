from __future__ import annotations
import time
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from .models import Task, Profile
from .flow_errors import (
    FLOW_RESPONSE_UNREADABLE,
    FLOW_RESPONSE_UNREADABLE_MESSAGE,
    is_flow_response_unreadable,
)
from . import db
from .worker import VideoWorker
from .gemini_worker import GeminiWebWorker
from .vids_worker import VidsWorker
from .verify import verify_task_video
from .image_modes import validate_image_result

# Explicit preflight and post-submit outcomes take precedence over log heuristics.
TERMINAL_FAILURES = {
    "FLOW_RESULT_UNCONFIRMED", "VIDS_RESULT_UNCONFIRMED", "GEMINI_RESULT_UNCONFIRMED", "IMAGE_RESULT_UNCONFIRMED",
    "INVALID_VIDEO_REQUEST", "VIDS_SETTINGS_UNCONFIRMED", "USER_ACTION_REQUIRED",
    "PROJECT_INIT_REQUIRED", "UNSUPPORTED_FEATURE", "WIRE_FORMAT_MISMATCH", "CONFIG_ERROR", "AGENTIC_UI_BLOCKED",
    FLOW_RESPONSE_UNREADABLE, "SAFETY_FILTER_BLOCKED", "VIDEO_ASPECT_MISMATCH", "VIDEO_DURATION_MISMATCH",
    "VIDEO_OUTPUT_INVALID", "AUDIO_DISABLED", "INVALID_IMAGE_REQUEST", "IMAGE_OUTPUT_INVALID",
    "PROCESS_CLEANUP_FAILED", "STOP_RESULT_UNCONFIRMED", "PRE_SUBMIT_TIMEOUT",
}

def classify_failure(err_code: str, err_msg: str, logs: str) -> tuple[str, str, int, bool]:
    """
    故障模式分类与冷却策略判定
    返回: (reason_category, friendly_message, cooldown_seconds, count_as_task_retry)
    - PROFILE_LOCKED: 浏览器目录被占用 -> 冷却10秒，不扣重试次数，重回排队
    - QUOTA_EXHAUSTED: 额度耗尽 -> 冷却8小时并换号，不扣重试次数
    - RATE_LIMITED: 触发频控/429 -> 冷却20分钟并换号，不扣重试次数
    - AUTH_EXPIRED: 授权失效/登录态过期 -> 标记auth_expired，提醒重新登录，不扣重试次数
    - GENERAL_ERROR: 普通错误 -> 冷却60秒，消耗任务重试次数
    """
    code_up = (err_code or "").upper()
    content = f"{err_code} {err_msg} {logs}".lower()

    if code_up == "PRE_SUBMIT_TIMEOUT":
        return (code_up, (err_msg or "提交前执行超时，确认未提交云端请求") +
                " 请检查登录和网页后手动重试；不自动重发。", 0, False)
    if code_up == "LOCAL_IMAGE_BUSY":
        return ("LOCAL_IMAGE_BUSY", err_msg or "本机生图通道繁忙，未提交网页请求", 15, False)
    if code_up in ("FLOW_RESULT_UNCONFIRMED", "VIDS_RESULT_UNCONFIRMED", "GEMINI_RESULT_UNCONFIRMED", "IMAGE_RESULT_UNCONFIRMED"):
        return (code_up, (err_msg or "Google 已收到生成请求，但本地尚未确认结果") +
                " 已停止自动重试，请先检查原工程/网页结果，勿直接重新生成以免重复消耗额度。", 0, False)
    if code_up in ("INVALID_VIDEO_REQUEST", "INVALID_IMAGE_REQUEST", "VIDS_SETTINGS_UNCONFIRMED",
                   "USER_ACTION_REQUIRED", "PROJECT_INIT_REQUIRED", "AUDIO_DISABLED", "CONFIG_ERROR", "AGENTIC_UI_BLOCKED"):
        return (code_up, (err_msg or "请核对输入、网页设置、登录或工程") +
                " 请手动处理后再重试；系统不会自动同意协议或切换平台。", 0, False)

    # Gemini has already generated a result. Validation failures must not spend
    # credits again or turn into account failover because logs mention quota.
    if code_up in ("VIDEO_ASPECT_MISMATCH", "VIDEO_DURATION_MISMATCH", "VIDEO_OUTPUT_INVALID", "IMAGE_OUTPUT_INVALID"):
        return (
            code_up,
            (err_msg or "生成产物核验未通过") + " 已停止自动重试，请检查成片后手动处理。",
            0,
            False,
        )

    # A reply-format drift is not evidence of missing frame constraints. This
    # check must precede quota/WAF text heuristics, including for older task logs.
    if is_flow_response_unreadable(err_code, err_msg, logs):
        return FLOW_RESPONSE_UNREADABLE, FLOW_RESPONSE_UNREADABLE_MESSAGE, 0, False

    # Other wire errors may protect outgoing constraints or follow a submit.
    # Keep them terminal, without falsely diagnosing absent frames.
    if code_up == "WIRE_FORMAT_MISMATCH" or (
        code_up == "EXIT_7" and ("wireformaterror" in content or "wire-format" in content)
    ):
        return (
            "WIRE_FORMAT_MISMATCH",
            "Flow 请求或响应格式校验失败；已停止重试，请先核对原项目和任务日志。",
            0,
            False,
        )

    # 0.2 提示词内容安全/条款拦截 (Safety Filter / Terms Violation)
    if code_up in ("SAFETY_FILTER_BLOCKED", "TERMS_VIOLATION") or any(k in content for k in [
        "against our terms", "safety_filter_blocked", "try asking something else",
        "content policy", "违反服务条款", "提示词安全拦截"
    ]):
        return (
            "SAFETY_FILTER_BLOCKED",
            "提示词触碰 Google 内容政策与服务条款 (That request looks like it goes against our terms)。请调整提示词避开敏感词后重新提交",
            0,
            False
        )

    # 0. 浏览器目录锁冲突 (Chrome 窗口仍在运行中)
    if code_up == "PROFILE_LOCKED" or any(k in content for k in [
        "profile_locked", "profilelockederror", "profile is in use", "is already in use",
        "lockfile", "singletonlock", "processsingleton",
        "chrome 窗口正被占用", "被当前打开的 chrome 窗口独占锁定"
    ]):
        return (
            "PROFILE_LOCKED",
            "Chrome Profile 正在被其他窗口占用；不会强杀浏览器，将冷却并有限重试/调度其他可用账号",
            60,
            True
        )

    # 0.3 浏览器会话或进程意外中断 (EXIT_15 / BrowserSessionClosedError)
    if code_up in ("EXIT_15", "BROWSER_CLOSED") or any(k in content for k in [
        "browsersessionclosederror", "browser has been closed", "target page, context or browser has been closed",
        "browser closed", "browser disconnected"
    ]):
        return (
            "BROWSER_SESSION_CLOSED",
            "浏览器会话意外中断，已自动解绑并由空闲账号接单重试",
            15,
            False
        )

    # 0.4 Google Flow 远端服务短暂波动 (Status 4 / Generation Failed)
    if any(k in content for k in [
        "migrated host reported status 4",
        "media_generation_status_failed",
        "generation_status_failed",
        "rpc error: status 4"
    ]):
        return (
            "TRANSIENT_SERVER_ERROR",
            "Google Flow 远端生成队列偶发波动(Status 4)，已自动解绑并由其他空闲账号重新排队重试",
            20,
            False
        )

    # 0.5 界面遮罩/智能体模式阻断
    if code_up in ("AGENTIC_UI_BLOCKED", "EXIT_25") or any(k in content for k in [
        "agentic_ui_blocked", "flowagentuierror", "google flow agentic ui detected", "settings-trigger-button"
    ]):
        return (
            "AGENTIC_UI_BLOCKED",
            "Google Flow 处于遮罩或智能体状态，已触发自愈并重新排队",
            15,
            False
        )

    # 0.8 工程未初始化或新条款阻断（可自愈错误，绝不能判定为账号失效封禁24小时）
    if any(k in content for k in [
        "createproject", "projectnotfound", "failed to create project", "project not found", "no project specified"
    ]):
        return (
            "PROJECT_INIT_REQUIRED",
            "账号缺少可用工程；请手动选择工程或处理协议，系统不会自动同意协议",
            10,
            False
        )

    # 1. 授权失效 / 未登录 (401 Unauthorized, Session Expired, etc.)
    if code_up == "AUTH_EXPIRED" or any(k in content for k in [
        "auth_expired", "authexpirederror", "auth-expired", "authentication expired",
        "unauthorized", "login required", "auth_failed", "cookie expired", "unauthenticated",
        "session expired", "not to the flow app", "status\": 401", "401 unauthorized",
        "登录态已失效", "未在 gemini 网页版登录", "请重新登录"
    ]):
        return (
            "AUTH_EXPIRED",
            "Google 账号登录态已过期或未授权，需在控制台重新登录",
            86400,
            False
        )

    # 1.5 新特性/模型尚未移植支持（例如 flow.google.com 下的 imagen4）
    if code_up in ("UNSUPPORTED_FEATURE", "EXIT_36") or any(k in content for k in [
        "not ported yet", "flowhostmigratederror", "flow-host-migrated"
    ]):
        return (
            "UNSUPPORTED_FEATURE",
            err_msg or "Google Flow 新架构尚未支持当前指定模型或功能，无需重试",
            0,
            False
        )

    # 2. 额度耗尽 (Quota, Daily limit, Out of credits, Resource exhausted)
    if code_up == "QUOTA_EXHAUSTED" or any(k in content for k in [
        "quota_exhausted", "quota", "exhausted", "credit", "daily limit", "resource_exhausted",
        "limit reached", "out of credits", "try again tomorrow", "you've reached your limit",
        "额度耗尽", "配额用尽", "超出限额"
    ]):
        return (
            "QUOTA_EXHAUSTED",
            "账号生成额度已耗尽，已触发自动轮换与冷却保护",
            28800,
            False
        )

    # 3. 触发 Google Flow 真实异常活动限制 (Unusual Activity / WAF)
    is_unusual = code_up == "UNUSUAL_ACTIVITY" or any(k in content for k in [
        "unusual activity",
        "unusual_activity",
        "public_error_unusual_activity",
        "we noticed some unusual activity"
    ])
    if is_unusual:
        return (
            "UNUSUAL_ACTIVITY",
            "Google Flow 拦截频控检测 (Unusual Activity)。系统已启动 5 分钟安全避让，家庭住宅IP无需换节点，静置后自动继续。",
            300,  # 5 分钟安全避让
            False
        )

    # 3.1 触发高频频控 (429, Rate limit)
    is_429 = bool(re.search(r"\b429\b", content)) or 'status": 429' in content or 'http 429' in content
    if code_up == "RATE_LIMITED" or is_429 or any(k in content for k in [
        "rate_limited", "rate_limit", "too many requests", "频控", "限流", "请求过多"
    ]):
        return (
            "RATE_LIMITED",
            "触发 Google 高频频控保护 (429 Too Many Requests)，该账号冷却 20 分钟并自动换号重试",
            1200,
            False
        )

    # 3.5 网络传输/远端生成超时 (TransportTimeoutError, EXIT_9, etc.)
    if code_up in ("EXIT_9", "TRANSPORT_TIMEOUT", "TIMEOUT") or any(k in content for k in [
        "transporttimeouterror", "transport timeout", "timed out waiting for response",
        "timed out", "timeout 180000ms exceeded", "timeout 120000ms exceeded",
        "operation timed out", "connection reset", "exited with code 9", "exit code 9"
    ]):
        return (
            "NETWORK_TIMEOUT",
            "Google Flow 远端响应超时（网络拥堵或生成队列波动）。已自动解绑故障通道，正由空闲账号接力换号重试",
            60,
            False
        )

    # 4. 普通可重试错误
    return ("GENERAL_ERROR", err_msg or "生成过程遇到普通异常", 60, True)


class VideoScheduler:
    def __init__(
        self,
        db_path: Path = db.DEFAULT_DB_PATH,
        max_workers: int = 1,
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
        self.vids_worker = VidsWorker(
            output_dir=output_dir,
            timeout_sec=worker_timeout_sec,
            headless=True,
            mock_sample_video=mock_sample_video
        )
        
        self.max_workers = max_workers
        self.active_tasks: Dict[str, threading.Event] = {}
        self.cancelled_task_ids: set[str] = set()
        self.lock = threading.Lock()
        self.running = False
        self.fleet_cooldown_until: Optional[datetime] = None
        self.recent_waf_hits: list[tuple[datetime, str]] = []

    def record_waf_hit(self, profile_id_or_name: str) -> bool:
        """记录 WAF / 异常活动命中：单次触发即开启全池避让，杜绝同 IP 连环撞墙"""
        now_dt = datetime.now().astimezone()
        with self.lock:
            self.recent_waf_hits.append((now_dt, str(profile_id_or_name)))
            cutoff = now_dt - timedelta(minutes=10)
            self.recent_waf_hits = [(t, p) for (t, p) in self.recent_waf_hits if t >= cutoff]
            return True

    def trigger_fleet_cooldown(self, seconds: int = 300, reason: str = "WAF_UNUSUAL_ACTIVITY"):
        now_dt = datetime.now().astimezone()
        target = now_dt + timedelta(seconds=seconds)
        if self.fleet_cooldown_until is None or target > self.fleet_cooldown_until:
            self.fleet_cooldown_until = target
        print(f"[Scheduler] 🛡️ 触发全池安全避让 (Fleet Cooldown): 暂停新任务派发 {seconds} 秒直至 {target.strftime('%H:%M:%S')} (原因: {reason})")

    def clear_fleet_cooldown(self) -> int:
        """手动解除全池避让，并将因为 WAF 等待的任务与冷却中的账号立即唤醒重排"""
        with self.lock:
            self.fleet_cooldown_until = None
            self.recent_waf_hits.clear()
        conn = db.get_db_connection(self.db_path)
        recovered = 0
        now_iso = datetime.now().astimezone().isoformat()
        try:
            with conn:
                cur = conn.execute("""
                UPDATE tasks
                SET status = 'queued', updated_at = ?
                WHERE status = 'retry_wait' AND error_code = 'UNUSUAL_ACTIVITY'
                """, (now_iso,))
                recovered = cur.rowcount
                # 同时将处于 cooldown 的账号一并复位为 idle
                conn.execute("""
                UPDATE profiles
                SET status = 'idle', cooldown_until = NULL, updated_at = ?
                WHERE status = 'cooldown' OR cooldown_until IS NOT NULL
                """, (now_iso,))
        finally:
            conn.close()
        print(f"[Scheduler] ⚡ 手动解除全池冷却，恢复了 {recovered} 个等待重试的任务，并复位所有账号为空闲")
        return recovered

    def recover_orphans(self) -> None:
        """自愈保护：将因服务重启或意外终止遗留在 running/busy 的任务与账号平稳重置"""
        conn = db.get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("""
                UPDATE tasks
                SET status = 'failed', error_code = 'RESULT_UNCONFIRMED', error_message = '服务中断，无法确认是否已提交；请核对原工程结果，不会自动重发扣费'
                WHERE status IN ('running', 'dispatching', 'verifying')
                """)
                conn.execute("""
                UPDATE profiles
                SET status = 'idle'
                WHERE status = 'busy'
                """)
        finally:
            conn.close()

    def recover_cooldowns(self) -> None:
        """自动恢复冷却时间到期的 Profile 为 idle"""
        now = datetime.now().astimezone().isoformat()
        conn = db.get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("""
                UPDATE profiles
                SET status = 'idle', cooldown_until = NULL, updated_at = ?
                WHERE (status = 'cooldown' OR (status = 'idle' AND cooldown_until IS NOT NULL))
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
        cleanup_failed = False
        
        try:
            with self.lock:
                active = self.active_tasks.get(task_id) or {}
                cancel_event = active.get("event", threading.Event())
                if task_id in self.cancelled_task_ids or cancel_event.is_set():
                    return
            worker = self.vids_worker if engine_name == "vids" else self.gemini_worker if engine_name == "gemini" else self.flow_worker
            task_type = getattr(task, "task_type", "video") or "video"
            prepare = getattr(worker, "prepare_image_task" if task_type == "image" else "prepare_task", None)
            if prepare:
                prepare(task_id, cancel_event)
            if engine_name == "vids":
                engine_label = "Google Vids (官方多模态原生工作流)"
            elif engine_name == "flow":
                engine_label = "Google Flow (首尾帧模式)"
            else:
                engine_label = "Gemini 网页版" 
            db.log_task_event(
                task_id, "WORKER_START",
                f"[{thread_name}] 任务分配至 Profile [{profile.name}]，采用引擎: {engine_label}",
                db_path=self.db_path
            )

            # 根据任务类型与业务形态派发到对应的 Worker
            task_type = getattr(task, "task_type", "video") or "video"
            if task_type == "image":
                if engine_name not in ("flow", "gemini"):
                    exec_res = {"success": False, "error_code": "INVALID_IMAGE_REQUEST", "error_message": "生图只支持 Flow 或 Gemini 网页通道"}
                else:
                    exec_res = worker.execute_image_task(task, profile)
            elif task_type == "audio":
                exec_res = {"success": False, "error_code": "AUDIO_DISABLED", "error_message": "本地配音功能已下线", "pid": None}
            elif engine_name == "gemini":
                exec_res = self.gemini_worker.execute_task(task, profile)
            elif engine_name == "vids":
                exec_res = self.vids_worker.execute_task(task, profile)
            else:
                exec_res = self.flow_worker.execute_task(task, profile)

            cleanup_failed = exec_res.get("cleanup_confirmed") is False
            if cleanup_failed:
                with self.lock:
                    self.active_tasks.setdefault(task_id, {
                        "event": cancel_event, "task": task, "profile": profile})["cleanup_failed"] = True
                db.update_profile_status(profile_id, "busy", db_path=self.db_path)
                current = db.get_task(task_id, self.db_path)
                if current and current.status != "cancelled":
                    db.update_task_status(task_id, "failed", error_code="PROCESS_CLEANUP_FAILED",
                        error_message="执行进程未确认退出；账号已隔离，请核对原工程，不重复提交。", db_path=self.db_path)
                db.log_task_event(task_id, "PROCESS_CLEANUP_FAILED",
                    "保留该账号的执行归属；其他空闲账号可继续派发", db_path=self.db_path)
                return

            pid = exec_res.get("pid")
            pid_str = f" (PID={pid})" if pid else ""

            # 优先检查任务是否在执行期间已被外部手动取消
            with self.lock:
                was_cancelled = (task_id in self.cancelled_task_ids)

            conn = db.get_db_connection(self.db_path)
            try:
                with conn:
                    r_check = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
                    if was_cancelled or (r_check and r_check["status"] == "cancelled"):
                        # The API stops immediately and conservatively locks retry.
                        # Only the execution owner, after confirmed tree cleanup
                        # and explicit no-submit evidence, may lift that lock.
                        if (exec_res.get("submission_possible") is False
                                and (exec_res.get("cleanup_confirmed") is True or engine_name == "flow" or task_type == "image")):
                            conn.execute("""UPDATE tasks SET error_code='USER_CANCELLED',
                                error_message=?, updated_at=? WHERE id=? AND status='cancelled'
                                AND error_code='STOP_RESULT_UNCONFIRMED'""",
                                ("本地执行已停止，确认未提交云端生成；可手动重试。",
                                 datetime.now().astimezone().isoformat(), task_id))
                        print(f"[{thread_name}] 任务 [{task_id}] 已在外部被用户手动中止，跳过后置处理。")
                        return
            finally:
                conn.close()

            # Verify task-owned images before success or any retry/failover decision.
            if task_type == "image" and exec_res.get("success"):
                try:
                    validate_image_result(exec_res, task, self.output_dir)
                except (ValueError, OSError, TypeError) as exc:
                    exec_res.update(success=False, error_code="IMAGE_OUTPUT_INVALID", error_message=str(exc))

            # ---------------- 失败处理与智能熔断切换 (Failover) ----------------
            if not exec_res["success"]:
                raw_code = exec_res.get("error_code") or "EXEC_FAILED"
                raw_msg = exec_res.get("error_message") or "Unknown error"
                logs = exec_res.get("logs") or ""

                category, friendly_msg, cooldown_sec, count_retry = classify_failure(raw_code, raw_msg, logs)
                now_dt = datetime.now().astimezone()
                cooldown_until = (now_dt + timedelta(seconds=cooldown_sec)).isoformat()

                if category in TERMINAL_FAILURES:
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="idle",
                        cooldown_until=None,
                        success=True,
                        db_path=self.db_path
                    )
                    db.update_task_status(
                        task_id=task_id,
                        status="failed",
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "TASK_FAILED", f"❌ {friendly_msg}", db_path=self.db_path)
                    print(f"[{thread_name}] ❌ 任务 [{task_id}] 不可自动重试: {friendly_msg}")
                    return

                if category == "PROFILE_LOCKED":
                    # Never destroy a user's Chrome or create an unbounded hot loop.
                    db.update_profile_status(profile_id, "cooldown", cooldown_until=cooldown_until,
                                             success=False, db_path=self.db_path)
                    retries = task.retry_count + 1
                    with db.get_db_connection(self.db_path) as conn:
                        conn.execute("UPDATE tasks SET retry_count = ? WHERE id = ?", (retries, task_id))
                    status = "retry_wait" if retries < task.max_retries else "failed"
                    failover_msg = f"{friendly_msg}（{retries}/{task.max_retries}）；可停止任务或关闭占用窗口后手动重试。"
                    db.update_task_status(task_id, status, clear_assigned_profile=True,
                                          error_code=category, error_message=failover_msg, logs=logs,
                                          db_path=self.db_path)
                    db.log_task_event(task_id, "PROFILE_LOCKED", failover_msg, db_path=self.db_path)
                    return

                if category == "UNUSUAL_ACTIVITY":
                    # 账号长冷却 30 分钟
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="cooldown",
                        cooldown_until=cooldown_until,
                        success=False,
                        db_path=self.db_path
                    )
                    # 立即触发全池避让 300 秒，保护所有账号免受同 IP 连带风控
                    self.record_waf_hit(profile.name)
                    self.trigger_fleet_cooldown(300, f"账号 [{profile.name}] 触发 Google 异常活动检测，启动全池避让 300 秒")

                    # 任务置为 retry_wait（绝不在短时间内无脑切号撞墙，等待冷却结束或用户换 IP 恢复）
                    db.update_task_status(
                        task_id=task_id,
                        status="retry_wait",
                        clear_assigned_profile=False,
                        error_code="UNUSUAL_ACTIVITY",
                        error_message="Google Flow 拦截短时频控检测 (Unusual Activity)。系统已自动进入安全避让（5分钟）；家庭住宅IP无需更换节点，静置后点击【恢复】即可继续。",
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "TASK_WAF_COOLDOWN", "🛡️ Google Flow 拦截异常活动检测 (Unusual Activity)。系统已启动 5 分钟全池避让保护，避免账号连带受控。", db_path=self.db_path)
                    print(f"[{thread_name}] 🛡️ 账号 [{profile.name}] 触发异常活动限制，已启动全池避让至 {self.fleet_cooldown_until.strftime('%H:%M:%S')}，任务 [{task_id}] 已转入安全等待")
                    return

                if category in ("AUTH_EXPIRED", "QUOTA_EXHAUSTED"):
                    prof_new_status = "auth_expired" if category == "AUTH_EXPIRED" else "cooldown"
                    db.update_profile_status(
                        profile_id=profile_id,
                        status=prof_new_status,
                        cooldown_until=cooldown_until,
                        success=False,
                        db_path=self.db_path
                    )

                    can_retry = task.retry_count < task.max_retries
                    if can_retry:
                        new_retry_count = task.retry_count + 1
                        conn = db.get_db_connection(self.db_path)
                        with conn:
                            conn.execute("UPDATE tasks SET retry_count = ? WHERE id = ?", (new_retry_count, task_id))
                        conn.close()
                        failover_msg = f"⚡ 账号 [{profile.name}] {friendly_msg}。正在切换备用可用账号重试 ({new_retry_count}/{task.max_retries})..."
                        db.update_task_status(
                            task_id=task_id,
                            status="queued",
                            clear_assigned_profile=True,
                            error_code=category,
                            error_message=friendly_msg,
                            logs=logs,
                            db_path=self.db_path
                        )
                        db.log_task_event(task_id, "ACCOUNT_FAILOVER", failover_msg, db_path=self.db_path)
                    else:
                        fail_msg = f"❌ 任务重试次数已达上限 ({task.max_retries}/{task.max_retries})，已停止切号重试: {friendly_msg}"
                        db.update_task_status(
                            task_id=task_id,
                            status="failed",
                            clear_assigned_profile=True,
                            error_code=category,
                            error_message=friendly_msg,
                            logs=logs,
                            db_path=self.db_path
                        )
                        db.log_task_event(task_id, "TASK_FAILED", fail_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {friendly_msg}")
                    return

                if category in ("RATE_LIMITED", "NETWORK_TIMEOUT", "TRANSIENT_SERVER_ERROR", "BROWSER_SESSION_CLOSED"):
                    # 临时波动/短时超时/浏览器意外关闭：原地冷却等待，严格锁定原账号，并递增重试计数，坚决防死循环！
                    cooldown_sec = 45 if category == "NETWORK_TIMEOUT" else 30
                    cooldown_until = (datetime.now().astimezone() + timedelta(seconds=cooldown_sec)).isoformat()
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="cooldown",
                        cooldown_until=cooldown_until,
                        success=False,
                        db_path=self.db_path
                    )

                    can_retry = task.retry_count < task.max_retries
                    if can_retry:
                        new_retry_count = task.retry_count + 1
                        conn = db.get_db_connection(self.db_path)
                        with conn:
                            conn.execute("UPDATE tasks SET retry_count = ? WHERE id = ?", (new_retry_count, task_id))
                        conn.close()

                        sticky_msg = f"⏳ 账号 [{profile.name}] 出现波动（{friendly_msg}），系统锁定当前账号冷却 {cooldown_sec} 秒后重试 ({new_retry_count}/{task.max_retries})。"
                        db.update_task_status(
                            task_id=task_id,
                            status="retry_wait",
                            clear_assigned_profile=False,
                            error_code=category,
                            error_message=friendly_msg,
                            logs=logs,
                            db_path=self.db_path
                        )
                        db.log_task_event(task_id, "STICKY_RETRY", sticky_msg, db_path=self.db_path)
                        print(f"[{thread_name}] {sticky_msg}")
                    else:
                        fail_msg = f"❌ 任务重试次数已达上限 ({task.max_retries}/{task.max_retries})，已停止自动重试: {friendly_msg}"
                        db.update_task_status(
                            task_id=task_id,
                            status="failed",
                            clear_assigned_profile=False,
                            error_code=category,
                            error_message=friendly_msg,
                            logs=logs,
                            db_path=self.db_path
                        )
                        db.log_task_event(task_id, "TASK_FAILED", fail_msg, db_path=self.db_path)
                        print(f"[{thread_name}] {fail_msg}")
                    return

                # 普通错误处理
                can_retry = task.retry_count < task.max_retries
                new_status = "retry_wait" if can_retry else "failed"

                db.update_task_status(
                    task_id=task_id,
                    status=new_status,
                    clear_assigned_profile=False,
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

            # ---------------- 成功生成 -> 图像/音频任务直接结单 / 视频进入质检验收 ----------------
            task_type = getattr(task, "task_type", "video") or "video"
            if task_type == "image":
                img_paths = exec_res.get("output_image_paths") or []
                img_json = json.dumps(img_paths, ensure_ascii=False)
                db.update_task_status(
                    task_id=task_id,
                    status="completed",
                    output_image_paths=img_json,
                    logs=exec_res.get("logs") or "",
                    db_path=self.db_path
                )
                db.update_profile_status(profile_id=profile_id, status="idle", success=True, db_path=self.db_path)
                count = len(img_paths)
                db.log_task_event(task_id, "TASK_COMPLETED", f"图像生成完成，共获得 {count} 张高质图片", db_path=self.db_path)
                return

            if task_type == "audio":
                audio_path = exec_res.get("output_audio_path")
                db.update_task_status(
                    task_id=task_id,
                    status="completed",
                    output_audio_path=audio_path,
                    logs=exec_res.get("logs") or "",
                    db_path=self.db_path
                )
                db.update_profile_status(profile_id=profile_id, status="idle", success=True, db_path=self.db_path)
                audio_name = Path(audio_path).name if audio_path else "音频文件"
                db.log_task_event(task_id, "TASK_COMPLETED", f"音频生成完成: {audio_name}", db_path=self.db_path)
                return

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
                s_path = (task.start_image_path or "").split(";")[0].strip()
                v_res = verify_task_video(
                    video_path=video_path,
                    start_image_path=s_path if s_path and Path(s_path).exists() else None,
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

            is_valid_video = bool(video_path and Path(video_path).exists() and v_res.get("error") is None)
            is_passed = v_res["success"] or (engine_name in ("vids", "gemini") and is_valid_video)

            if is_passed:
                db.update_task_status(task_id=task_id, status="completed", db_path=self.db_path)
                pacing_cooldown = (datetime.now().astimezone() + timedelta(seconds=60)).isoformat()
                db.update_profile_status(profile_id=profile_id, status="idle", cooldown_until=pacing_cooldown, success=True, db_path=self.db_path)

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

                db.log_task_event(task_id, "TASK_COMPLETED", f"成片完成并已就绪: {video_path}", db_path=self.db_path)
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
            current = db.get_task(task_id, self.db_path)
            if current and current.status == "cancelled":
                db.log_task_event(task_id, "STOP_CLEANUP", "执行线程已退出并释放资源", db_path=self.db_path)
                return
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
            if not cleanup_failed:
                current = db.get_task(task_id, self.db_path)
                if current and current.status == "cancelled":
                    db.update_profile_status(profile_id, "idle", cooldown_until=None, db_path=self.db_path)
                with self.lock:
                    self.cancelled_task_ids.discard(task_id)
                    self.active_tasks.pop(task_id, None)

    def cancel_task(self, task_id: str) -> bool:
        """Signal the owning worker; release its slot/profile only after it exits."""
        with self.lock:
            active = self.active_tasks.get(task_id)
            if not active:
                return False
            self.cancelled_task_ids.add(task_id)
            active["event"].set()
            engine = active["task"].engine
            task_type = active["task"].task_type
        worker = (self.flow_worker if engine == "flow" else
                  self.vids_worker if engine == "vids" else self.gemini_worker)
        try:
            worker.cancel_task(task_id)
        except Exception as exc:
            db.log_task_event(task_id, "STOP_SIGNAL_ERROR", str(exc), db_path=self.db_path)
        return True

    def _reap_cleanup_owners(self) -> None:
        """Poll only quarantined children; never restart or resubmit their work."""
        with self.lock:
            owners = [(key, value) for key, value in self.active_tasks.items()
                      if value.get("cleanup_failed")]
        for task_id, active in owners:
            task = active["task"]
            worker = (self.flow_worker if task.engine == "flow" else
                      self.vids_worker if task.engine == "vids" else self.gemini_worker)
            poll = getattr(worker, "has_live_execution", None)
            try:
                if poll is None or poll(task_id):
                    continue
            except Exception:
                continue  # An unavailable process status is not proof of exit.
            with self.lock:
                if self.active_tasks.get(task_id) is not active:
                    continue
                db.update_profile_status(active["profile"].id, "idle", db_path=self.db_path)
                self.active_tasks.pop(task_id, None)
                self.cancelled_task_ids.discard(task_id)
            db.log_task_event(task_id, "STOP_CLEANUP", "残留进程已确认退出，解除账号隔离", db_path=self.db_path)

    def dispatch_cycle(self) -> int:
        """检查等待排队任务并派发到空闲可用 Profile"""
        self._reap_cleanup_owners()
        now_dt = datetime.now().astimezone()
        if self.fleet_cooldown_until and now_dt < self.fleet_cooldown_until:
            # 账号池处于削峰熔断保护期，暂停派发新任务
            return 0

        self.recover_cooldowns()

        # 冷却防抖：先将等待超过 15 秒且未达到最大重试次数的 retry_wait 任务推回 queued 并解绑账号
        now_iso = datetime.now().astimezone().isoformat()
        threshold_iso = (datetime.now().astimezone() - timedelta(seconds=15)).isoformat()
        conn = db.get_db_connection(self.db_path)
        try:
            with conn:
                conn.execute("""
                UPDATE tasks 
                SET status = 'queued', updated_at = ?
                WHERE status = 'retry_wait' 
                  AND retry_count < max_retries
                  AND updated_at <= ?
                  AND error_code != 'UNUSUAL_ACTIVITY' 
                """, (now_iso, threshold_iso))

                # 超过最大重试次数的任务自动归为 failed，脱离 retry_wait 死锁状态
                conn.execute("""
                UPDATE tasks 
                SET status = 'failed', updated_at = ?
                WHERE status = 'retry_wait' 
                  AND retry_count >= max_retries
                """, (now_iso,))
        finally:
            conn.close()

        # 计算当前可用槽位
        with self.lock:
            active_count = sum(not owner.get("cleanup_failed") for owner in self.active_tasks.values())
        available_slots = max(0, self.max_workers - active_count)
        if available_slots <= 0:
            return 0

        conn = db.get_db_connection(self.db_path)
        queued_tasks = []
        try:
            with conn:
                rows = conn.execute("""
                SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority DESC, submit_time ASC
                LIMIT ?
                """, (max(50, available_slots * 10),)).fetchall()
                queued_tasks = [db.row_to_task(r) for r in rows]
        finally:
            conn.close()

        if not queued_tasks:
            return 0

        dispatched = 0
        for task in queued_tasks:
            if dispatched >= available_slots:
                break
            # One ownership boundary, shared with profile reset/close and chat.
            with self.lock:
                if task.id in self.active_tasks or sum(not owner.get("cleanup_failed") for owner in self.active_tasks.values()) >= self.max_workers:
                    continue
                target_profile_id = task.assigned_profile_id or db.get_affinity_profile_id(task.project_id, self.db_path)
                profile = db.acquire_idle_profile(
                    require_clean=task.require_clean_watermark,
                    profile_id=target_profile_id, db_path=self.db_path)
                if not profile and target_profile_id:
                    profile = db.acquire_idle_profile(
                        require_clean=task.require_clean_watermark,
                        profile_id=None, db_path=self.db_path)
                    if profile and target_profile_id != task.assigned_profile_id:
                        db.log_task_event(task.id, "AFFINITY_FAILOVER",
                            f"首选粘性账号 [{target_profile_id}] 正忙，由空闲账号 [{profile.name}] 安全接力",
                            db_path=self.db_path)
                    elif profile:
                        db.log_task_event(task.id, "FAILOVER_PROFILE",
                            f"原绑定账号 [{task.assigned_profile_id}] 暂不可用，由空闲账号 [{profile.name}] 接力",
                            db_path=self.db_path)
                if not profile:
                    continue
                if not db.claim_task(task.id, profile.id, self.db_path):
                    db.update_profile_status(profile.id, "idle", db_path=self.db_path)
                    continue
                self.active_tasks[task.id] = {
                    "event": threading.Event(), "task": task, "profile": profile,
                    "start_time": time.time()}
            try:
                self.executor.submit(self.process_task_execution, task, profile)
            except Exception as exc:
                # No worker was started; unlike a stopped running task it is safe
                # to release this reservation immediately.
                with self.lock:
                    self.active_tasks.pop(task.id, None)
                    self.cancelled_task_ids.discard(task.id)
                    db.update_task_status(task.id, "failed", error_code="EXECUTOR_UNAVAILABLE",
                        error_message=f"执行器未启动任务: {exc}", db_path=self.db_path)
                    db.update_profile_status(profile.id, "idle", db_path=self.db_path)
                db.log_task_event(task.id, "EXECUTOR_UNAVAILABLE", str(exc), db_path=self.db_path)
                continue
            dispatched += 1

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
