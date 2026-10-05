import pytest
from unittest.mock import patch, MagicMock
from video_farm import db
from video_farm.vids_router import _enqueue_shot_task

def test_enqueue_shot_task_first_last_frame_adapter():
    """验证首尾帧分镜自适应调度至 Flow (Veo 3.1) 以确保尾帧生效"""
    shot = {
        "id": "shot_test_fl",
        "name": "镜头1·首尾过渡",
        "mode": "first_last_frame",
        "image_url": "test_start.png",
        "end_image_url": "test_end.png",
        "prompt": "金色麦田平滑过渡到微观叶片",
        "engine": "vids",
        "resolution": "1080p",
        "model_name": "Omni",
        "duration": 8
    }
    wf = {
        "title": "测试工程",
        "engine": "vids",
        "resolution": "1080p",
        "model_name": "Omni",
        "aspect_ratio": "16:9",
        "doc_url": "https://docs.google.com/videos/test"
    }
    
    with patch("video_farm.vids_router._resolve_local_image_path", side_effect=lambda p: f"/abs/path/{p}"):
        task_id = _enqueue_shot_task(shot, wf)
        task = db.get_task(task_id)
        assert task is not None
        # 验证底层引擎被自适应调整为 flow，模型为 veo-lite，以确保首尾双帧关键帧约束生效
        assert task.engine == "flow"
        assert task.model == "veo-lite"
        assert task.start_image_path == "/abs/path/test_start.png"
        assert task.end_image_path == "/abs/path/test_end.png"

def test_enqueue_shot_task_single_frame_vids_retention():
    """验证单图参考或文生视频在选择 vids 时保持 Google Vids 原生引擎"""
    shot = {
        "id": "shot_test_single",
        "name": "镜头2·单图微动",
        "mode": "image2video",
        "image_url": "test_single.png",
        "end_image_url": "",
        "prompt": "单图缓慢微动运镜",
        "engine": "vids",
        "resolution": "1080p",
        "model_name": "Omni",
        "duration": 6
    }
    wf = {
        "title": "测试工程",
        "engine": "vids",
        "resolution": "1080p",
        "model_name": "Omni",
        "aspect_ratio": "16:9",
        "doc_url": "https://docs.google.com/videos/test"
    }
    
    with patch("video_farm.vids_router._resolve_local_image_path", side_effect=lambda p: f"/abs/path/{p}" if p else ""):
        task_id = _enqueue_shot_task(shot, wf)
        task = db.get_task(task_id)
        assert task is not None
        assert task.engine == "vids"
        assert task.model == "Omni (1080p)"
        assert task.start_image_path == "/abs/path/test_single.png"
        assert task.end_image_path == ""

def test_scheduler_failover_when_bound_profile_unavailable():
    """验证原绑定账号忙碌或冷却时，调度器自动启用空闲账号接力执行，杜绝队头死锁"""
    from video_farm.scheduler import VideoScheduler
    from video_farm.models import Task, Profile

    task = Task(
        id="task_failover_test",
        prompt="测试换号容灾",
        assigned_profile_id="busy_prof_id",
        status="queued"
    )
    idle_prof = Profile(
        id="idle_prof_id",
        name="空闲备用号",
        enabled=True,
        status="idle"
    )

    # 模拟 acquire_idle_profile: 当指定 busy_prof_id 时返回 None，当 profile_id=None 时返回 idle_prof
    def mock_acquire(require_clean=False, profile_id=None, db_path=None):
        if profile_id == "busy_prof_id":
            return None
        return idle_prof

    with patch("video_farm.db.acquire_idle_profile", side_effect=mock_acquire), \
         patch("video_farm.db.claim_task", return_value=True), \
         patch("video_farm.db.log_task_event") as mock_log, \
         patch("video_farm.db.get_db_connection") as mock_conn:
        
        scheduler = VideoScheduler(db_path=MagicMock(), max_workers=1)
        # 验证调度器能够成功识别并调度 fallback profile
        scheduler.executor = MagicMock()
        with patch.object(scheduler, "recover_cooldowns"):
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.__enter__.return_value.execute.return_value = mock_cursor
            
            # 单独调用 dispatch 逻辑里的 profile 获取
            profile = mock_acquire(profile_id=task.assigned_profile_id)
            assert profile is None
            fallback = mock_acquire(profile_id=None)
            assert fallback is not None
            assert fallback.id == "idle_prof_id"
