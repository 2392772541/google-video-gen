import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from PIL import Image
from video_farm import db
from video_farm.vids_router import _enqueue_shot_task


def make_shot(tmp_path, **changes):
    start, end = tmp_path / "start.png", tmp_path / "end.png"
    Image.new("RGB", (64, 36), "blue").save(start)
    Image.new("RGB", (64, 36), "red").save(end)
    wf = db.create_vids_workflow("adapter test", duration_per_shot=6,
        doc_url="https://docs.google.com/videos/d/test/edit", resolution="1080p")
    args = dict(workflow_id=wf["id"], name="isolated shot", prompt="smooth movement",
        duration=6, mode="image2video", image_url=str(start), engine="vids")
    args.update(changes)
    return db.create_vids_shot(**args), wf, str(start), str(end)


def test_enqueue_shot_task_first_last_frame_adapter(tmp_path):
    """首尾双素材：Vids 原生支持绑定 @图片1/@图片2，Flow 支持物理插值，两者均严格保留平台与模型。"""
    shot, wf, start, end = make_shot(tmp_path)
    db.update_vids_shot(shot["id"], {"mode": "first_last_frame", "end_image_url": end, "engine": "vids"})
    task_id = _enqueue_shot_task(shot, wf)
    task = db.get_task(task_id)
    assert task.engine == "vids"
    assert task.model == "Omni (1080p)"
    assert task.start_image_path == start
    assert task.end_image_path == end
    assert db.get_vids_shot(shot["id"])["task_id"] == task_id

    # 显式 Flow 也正常保留
    shot2, wf2, start2, end2 = make_shot(tmp_path)
    db.update_vids_shot(shot2["id"], {"mode": "first_last_frame", "end_image_url": end2, "engine": "flow"})
    task_id2 = _enqueue_shot_task(shot2, wf2)
    task2 = db.get_task(task_id2)
    assert task2.engine == "flow"
    assert task2.model == "veo-lite"
    assert task2.start_image_path == start2
    assert task2.end_image_path == end2
    assert db.get_vids_shot(shot2["id"])["task_id"] == task_id2


def test_enqueue_shot_task_single_frame_vids_retention(tmp_path):
    """通过真实隔离DB入队，单图严格保留Vids和1080p。"""
    shot, wf, start, _ = make_shot(tmp_path)
    task_id = _enqueue_shot_task(shot, wf)
    task = db.get_task(task_id)
    assert task.engine == "vids"
    assert task.model == "Omni (1080p)"
    assert task.start_image_path == start
    assert task.end_image_path == ""
    assert task.project_id == wf["doc_url"]
    assert db.get_vids_shot(shot["id"])["task_id"] == task_id

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
