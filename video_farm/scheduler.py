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
from . import db
from .worker import VideoWorker
from .gemini_worker import GeminiWebWorker
from .verify import verify_task_video

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

    # Flow already received a submit of the wrong shape. Do not retry on this or
    # another account: the first attempt may have spent credits without a usable MP4.
    if code_up == "WIRE_FORMAT_MISMATCH" or (
        code_up == "EXIT_7" and ("wireformaterror" in content or "wire-format" in content)
    ):
        return (
            "WIRE_FORMAT_MISMATCH",
            "Flow 实际提交未满足首尾帧约束；已停止重试，请人工核对模型和帧绑定。",
            0,
            False,
        )

    # 0. 浏览器目录锁冲突 (Chrome 窗口仍在运行中)
    if code_up == "PROFILE_LOCKED" or any(k in content for k in [
        "profile_locked", "profilelockederror", "profile is in use", "is already in use",
        "lockfile", "singletonlock", "processsingleton",
        "chrome 窗口正被占用", "被当前打开的 chrome 窗口独占锁定"
    ]):
        return (
            "PROFILE_LOCKED",
            "Chrome Profile 正在被外部浏览器窗口独占占用，请关闭桌面 Chrome 窗口后系统将自动继续执行",
            10,
            False
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
            "账号尚未初始化专属 Flow 工程或协议未同意，已触发自愈就绪",
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
        
        self.max_workers = max_workers
        self.active_tasks: Dict[str, threading.Event] = {}
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
                SET status = 'queued', error_code = 'RECOVERED_ON_RESTART', error_message = '系统启动自动恢复中断任务'
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
        
        try:
            engine_label = "Google Flow (首尾帧模式)" if engine_name == "flow" else "Gemini 网页版"
            db.log_task_event(
                task_id, "WORKER_START",
                f"[{thread_name}] 任务分配至 Profile [{profile.name}]，采用引擎: {engine_label}",
                db_path=self.db_path
            )

            # 根据任务类型与业务形态派发到对应的 Worker
            task_type = getattr(task, "task_type", "video") or "video"
            if task_type == "image":
                exec_res = self.flow_worker.execute_image_task(task, profile)
            elif task_type == "audio":
                exec_res = self.gemini_worker.execute_audio_task(task, profile)
            elif engine_name == "gemini":
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

                if category in ("UNSUPPORTED_FEATURE", "WIRE_FORMAT_MISMATCH"):
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

                if category == "PROJECT_INIT_REQUIRED":
                    # 工程未初始化或新条款阻断：触发自愈，锁定当前账号，任务等待自愈完成
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="idle",
                        cooldown_until=None,
                        success=False,
                        db_path=self.db_path
                    )
                    db.update_task_status(
                        task_id=task_id,
                        status="queued",
                        clear_assigned_profile=False,
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    heal_msg = f"🔄 账号 [{profile.name}] 未绑定工程，已自动触发无头自愈初始化，任务已重新放回排队。"
                    db.log_task_event(task_id, "AUTO_ONBOARD", heal_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {heal_msg}")
                    try:
                        from .onboard import auto_onboard_profile
                        threading.Thread(
                            target=lambda: auto_onboard_profile(profile.name, create_default_project=True),
                            daemon=True,
                            name=f"AsyncOnboard-{profile.name}"
                        ).start()
                    except Exception:
                        pass
                    return

                if category == "PROFILE_LOCKED":
                    # 浏览器窗口独占占用：账号维持 idle，任务安全保留在排队中，不扣重试次数
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="idle",
                        cooldown_until=None,
                        success=False,
                        db_path=self.db_path
                    )
                    failover_msg = f"⏳ 账号 [{profile.name}] {friendly_msg}。任务已安全放回队列，等待 Chrome 窗口关闭后自动运行..."
                    db.update_task_status(
                        task_id=task_id,
                        status="queued",
                        clear_assigned_profile=False,
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "PROFILE_LOCKED", failover_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {failover_msg}")
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

                    failover_msg = f"⚡ 账号 [{profile.name}] {friendly_msg}。系统已将任务自动重置排队，正在切换至备用可用账号..."
                    db.update_task_status(
                        task_id=task_id,
                        status="queued",
                        clear_assigned_profile=True,  # 仅在账号彻底失效或耗尽时解绑换号
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "ACCOUNT_FAILOVER", failover_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {failover_msg}")
                    return

                if category in ("RATE_LIMITED", "NETWORK_TIMEOUT", "TRANSIENT_SERVER_ERROR", "BROWSER_SESSION_CLOSED"):
                    # 临时波动/短时超时/浏览器意外关闭：原地冷却等待，严格锁定原账号，绝不漂移切号引发同IP多账号连带风控
                    cooldown_sec = 45 if category == "NETWORK_TIMEOUT" else 30
                    cooldown_until = datetime.now() + timedelta(seconds=cooldown_sec)
                    db.update_profile_status(
                        profile_id=profile_id,
                        status="cooldown",
                        cooldown_until=cooldown_until,
                        success=False,
                        db_path=self.db_path
                    )

                    sticky_msg = f"⏳ 账号 [{profile.name}] 出现临时波动（{friendly_msg}）。系统保持锁定当前账号原地冷却 {cooldown_sec} 秒后重试，禁止跳号避让风控。"
                    db.update_task_status(
                        task_id=task_id,
                        status="queued",
                        clear_assigned_profile=False,  # 严格锁定当前账号，绝不切号！
                        error_code=category,
                        error_message=friendly_msg,
                        logs=logs,
                        db_path=self.db_path
                    )
                    db.log_task_event(task_id, "STICKY_RETRY", sticky_msg, db_path=self.db_path)
                    print(f"[{thread_name}] {sticky_msg}")
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
        """检查等待排队任务并派发到空闲可用 Profile"""
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
            active_count = len(self.active_tasks)
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

            profile = db.acquire_idle_profile(
                require_clean=task.require_clean_watermark,
                profile_id=task.assigned_profile_id,
                db_path=self.db_path
            )
            if not profile:
                continue

            # 标记任务进入 running 状态
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
