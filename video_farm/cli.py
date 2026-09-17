from __future__ import annotations
import argparse
import sys
import json
import uuid
from pathlib import Path
from datetime import datetime

from . import db
from .models import Profile, Task
from .scheduler import VideoScheduler
from .verify import verify_task_video

def cmd_init_db(args):
    db.init_db()
    print("数据库初始化成功：video_farm_data/tasks.db")

def cmd_profile_add(args):
    db.init_db()
    name = args.name
    existing = db.get_profile_by_name(name)
    prof_id = existing.id if existing else f"prof_{uuid.uuid4().hex[:8]}"
    
    prof_path = args.path
    if not prof_path:
        default_dir = Path.home() / "AppData" / "Local" / "ffroliva" / "gflow-cli" / f"profile_{name}"
        if default_dir.exists():
            prof_path = str(default_dir)
            
    p = Profile(
        id=prof_id,
        name=name,
        profile_path=prof_path or "",
        account_label=args.label or "",
        status=args.status or "idle",
        watermark_mode=args.watermark or "unknown",
        enabled=not args.disabled,
        notes=args.notes or ""
    )
    db.add_profile(p)
    print(f"Profile [{name}] 注册/更新成功 (ID: {prof_id}, 状态: {p.status}, 水印: {p.watermark_mode}, 路径: {p.profile_path})")

def cmd_profile_list(args):
    db.init_db()
    profiles = db.list_profiles()
    if not profiles:
        print("暂无已注册的 Profile。使用 'profile add <name>' 添加。")
        return
        
    print(f"{'ID':<14} {'Name':<15} {'Status':<10} {'Watermark':<14} {'Enabled':<8} {'Last Success':<20} {'Cooldown Until'}")
    print("-" * 95)
    for p in profiles:
        succ = (p.last_success_at or "-")[:19]
        cd = (p.cooldown_until or "-")[:19]
        en = "Yes" if p.enabled else "No"
        print(f"{p.id:<14} {p.name:<15} {p.status:<10} {p.watermark_mode:<14} {en:<8} {succ:<20} {cd}")

def cmd_profile_set_status(args):
    db.init_db()
    p = db.get_profile_by_name(args.name)
    if not p:
        print(f"未找到 Profile: {args.name}")
        return
    db.update_profile_status(p.id, args.status)
    print(f"Profile [{args.name}] 状态已变更为: {args.status}")

def cmd_task_add(args):
    db.init_db()
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    t = Task(
        id=task_id,
        prompt=args.prompt,
        start_image_path=str(Path(args.start).resolve()),
        end_image_path=str(Path(args.end).resolve()),
        aspect_ratio=args.aspect,
        duration_sec=args.duration,
        priority=args.priority,
        require_clean_watermark=args.clean
    )
    db.add_task(t)
    print(f"任务已创建并入队：")
    print(f"  任务ID: {task_id}")
    print(f"  首帧: {t.start_image_path}")
    print(f"  尾帧: {t.end_image_path}")
    print(f"  画幅: {t.aspect_ratio} | 时长: {t.duration_sec}s | 优先级: {t.priority}")
    print(f"  要求无水印: {'是' if t.require_clean_watermark else '否'}")
    print(f"  提示词: {t.prompt}")

def cmd_task_batch_add(args):
    db.init_db()
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"分镜清单文件不存在: {file_path}")
        return
    
    with open(file_path, "r", encoding="utf-8") as f:
        shots = json.load(f)
        
    if not isinstance(shots, list):
        print("错误: 批量清单文件必须是包含分镜字典的 JSON 列表格式。")
        return
        
    created_count = 0
    print(f"正在从 [{file_path.name}] 批量导入 {len(shots)} 个分镜任务...")
    for idx, item in enumerate(shots, 1):
        prompt = item.get("prompt", "")
        start_p = item.get("start") or item.get("start_image") or item.get("start_frame")
        end_p = item.get("end") or item.get("end_image") or item.get("end_frame")
        aspect = item.get("aspect", "9:16")
        duration = int(item.get("duration", 8))
        priority = int(item.get("priority", 10))
        clean = bool(item.get("clean", False))
        
        if not start_p or not end_p or not prompt:
            print(f"  [跳过] 分镜 #{idx}: 缺少必要参数 (start, end 或 prompt)")
            continue
            
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        t = Task(
            id=task_id,
            prompt=prompt,
            start_image_path=str(Path(start_p).resolve()),
            end_image_path=str(Path(end_p).resolve()),
            aspect_ratio=aspect,
            duration_sec=duration,
            priority=priority,
            require_clean_watermark=clean
        )
        db.add_task(t)
        created_count += 1
        print(f"  [成功] 分镜 #{idx} -> TaskID: {task_id} ({aspect}, {duration}s)")
        
    print(f"批量导入完成：成功入队 {created_count} / {len(shots)} 个任务。")

def cmd_task_list(args):
    db.init_db()
    tasks = db.list_tasks(status=args.status, limit=args.limit)
    if not tasks:
        print("当前无符合条件的任务。")
        return
        
    print(f"{'Task ID':<18} {'Status':<12} {'Profile':<14} {'Aspect':<6} {'First NCC':<10} {'Last NCC':<10} {'Watermark':<12} {'Submit Time'}")
    print("-" * 105)
    for t in tasks:
        p_name = t.assigned_profile_id or "-"
        fncc = f"{t.first_frame_ncc:.4f}" if t.first_frame_ncc is not None else "-"
        lncc = f"{t.last_frame_ncc:.4f}" if t.last_frame_ncc is not None else "-"
        sub_time = (t.submit_time or "")[:19]
        print(f"{t.id:<18} {t.status:<12} {p_name:<14} {t.aspect_ratio:<6} {fncc:<10} {lncc:<10} {t.watermark_check:<12} {sub_time}")

def cmd_task_show(args):
    db.init_db()
    t = db.get_task(args.task_id)
    if not t:
        print(f"任务不存在: {args.task_id}")
        return
        
    print("=" * 60)
    print(f"任务详情: {t.id}")
    print("=" * 60)
    print(f"状态: {t.status}")
    print(f"分配 Profile: {t.assigned_profile_id or '未分配'}")
    print(f"画幅 / 时长: {t.aspect_ratio} / {t.duration_sec}s")
    print(f"提示词: {t.prompt}")
    print(f"首帧路径: {t.start_image_path}")
    print(f"尾帧路径: {t.end_image_path}")
    print(f"成片路径: {t.output_video_path or '无'}")
    print(f"首帧 NCC: {t.first_frame_ncc} (匹配: {t.first_frame_matched})")
    print(f"尾帧 NCC: {t.last_frame_ncc} (匹配: {t.last_frame_matched})")
    print(f"防静止参比: {t.last_vs_start_ncc}")
    print(f"水印状态: {t.watermark_check}")
    print(f"重试次数: {t.retry_count} / {t.max_retries}")
    if t.error_code:
        print(f"错误代码: {t.error_code}")
        print(f"错误信息: {t.error_message}")
        
    print("\n--- 事件日志 (Task Events) ---")
    events = db.list_task_events(t.id)
    for e in events:
        ts = e.get("created_at", "")[:19]
        print(f"[{ts}] {e.get('event_type')}: {e.get('message')}")

def cmd_run(args):
    db.init_db()
    sched = VideoScheduler(
        max_workers=args.workers,
        worker_timeout_sec=args.timeout,
        mock_sample_video=args.mock_sample
    )
    sched.run_loop(
        poll_interval_sec=args.interval,
        stop_when_idle=args.stop_when_idle
    )

def cmd_verify(args):
    db.init_db()
    t = db.get_task(args.task_id)
    if not t:
        print(f"未找到任务: {args.task_id}")
        return
    if not t.output_video_path or not Path(t.output_video_path).exists():
        print(f"任务视频尚未生成或文件不存在: {t.output_video_path}")
        return
        
    qa_dir = Path("video_farm_data/qa") / t.id
    res = verify_task_video(t.output_video_path, t.start_image_path, t.end_image_path, qa_dir)
    print("手动质检结果：")
    for k, v in res.items():
        print(f"  {k}: {v}")

def main():
    parser = argparse.ArgumentParser(description="VideoFarm: 多Profile Google Flow首尾帧调度管理系统")
    subparsers = parser.add_subparsers(dest="subcommand", help="子命令")

    # web
    w_parser = subparsers.add_parser("web", help="启动网页管理控制台")
    w_parser.add_argument("--port", type=int, default=8088, help="服务端口 (默认 8088)")
    w_parser.add_argument("--host", type=str, default="127.0.0.1", help="绑定地址 (默认 127.0.0.1)")

    # init-db
    subparsers.add_parser("init-db", help="初始化SQLite数据库")

    # profile
    p_parser = subparsers.add_parser("profile", help="管理Profile账号")
    p_sub = p_parser.add_subparsers(dest="profile_cmd")
    
    p_add = p_sub.add_parser("add", help="添加或更新Profile")
    p_add.add_argument("name", help="Profile名称 (如 gflow-test)")
    p_add.add_argument("--path", help="Chrome Profile存储路径")
    p_add.add_argument("--label", help="账号备注说明")
    p_add.add_argument("--status", choices=["idle", "busy", "cooldown", "disabled", "restricted"], default="idle")
    p_add.add_argument("--watermark", choices=["clean", "forced_visible", "unknown"], default="unknown")
    p_add.add_argument("--disabled", action="store_true", help="初始停用")
    p_add.add_argument("--notes", help="额外备注")
    
    p_sub.add_parser("list", help="列出所有Profile")
    
    p_set = p_sub.add_parser("set-status", help="修改Profile状态")
    p_set.add_argument("name", help="Profile名称")
    p_set.add_argument("status", choices=["idle", "busy", "cooldown", "disabled", "restricted"])

    # task
    t_parser = subparsers.add_parser("task", help="管理生成任务")
    t_sub = t_parser.add_subparsers(dest="task_cmd")
    
    t_add = t_sub.add_parser("add", help="投递单任务")
    t_add.add_argument("--prompt", required=True, help="动态提示词")
    t_add.add_argument("--start", required=True, help="首帧图片路径")
    t_add.add_argument("--end", required=True, help="尾帧图片路径")
    t_add.add_argument("--aspect", choices=["9:16", "16:9"], default="9:16", help="画幅比例")
    t_add.add_argument("--duration", type=int, choices=[4, 6, 8, 10], default=8, help="时长(秒)")
    t_add.add_argument("--priority", type=int, default=10, help="优先级 (数字越大越优先)")
    t_add.add_argument("--clean", action="store_true", help="强制要求分配无水印账号")

    t_badd = t_sub.add_parser("batch-add", help="从JSON文件批量投递分镜任务")
    t_badd.add_argument("--file", required=True, help="分镜JSON文件路径")
    
    t_list = t_sub.add_parser("list", help="查看任务列表")
    t_list.add_argument("--status", choices=["queued", "running", "verifying", "completed", "failed", "retry_wait"])
    t_list.add_argument("--limit", type=int, default=30)
    
    t_show = t_sub.add_parser("show", help="查看任务详情")
    t_show.add_argument("task_id", help="任务ID")

    # run
    r_parser = subparsers.add_parser("run", help="启动调度器轮询引擎")
    r_parser.add_argument("--workers", type=int, default=2, help="最大并发工作线程数")
    r_parser.add_argument("--interval", type=float, default=3.0, help="轮询间隔(秒)")
    r_parser.add_argument("--timeout", type=int, default=360, help="单任务执行超时时间(秒)")
    r_parser.add_argument("--stop-when-idle", action="store_true", help="队列清空且无活跃任务时自动退出")
    r_parser.add_argument("--mock-sample", help="使用已有视频样例进行无消耗模拟调度与真实抽帧质检")

    # verify
    v_parser = subparsers.add_parser("verify", help="对指定任务输出手动触发抽帧验证")
    v_parser.add_argument("task_id", help="任务ID")

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        return

    if args.subcommand == "init-db":
        cmd_init_db(args)
    elif args.subcommand == "profile":
        if args.profile_cmd == "add":
            cmd_profile_add(args)
        elif args.profile_cmd == "list":
            cmd_profile_list(args)
        elif args.profile_cmd == "set-status":
            cmd_profile_set_status(args)
        else:
            p_parser.print_help()
    elif args.subcommand == "task":
        if args.task_cmd == "add":
            cmd_task_add(args)
        elif args.task_cmd == "batch-add":
            cmd_task_batch_add(args)
        elif args.task_cmd == "list":
            cmd_task_list(args)
        elif args.task_cmd == "show":
            cmd_task_show(args)
        else:
            t_parser.print_help()
    elif args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "verify":
        cmd_verify(args)

if __name__ == "__main__":
    main()
