"""Regression: never discard frames, change providers, or fake running work."""
import pytest
from fastapi import HTTPException
from video_farm import db
from video_farm.models import Task
from video_farm.vids_router import _enqueue_shot_task


@pytest.fixture
def shot_factory(tmp_path):
    start = tmp_path / "start.png"
    end = tmp_path / "end.png"
    from PIL import Image
    Image.new("RGB", (64, 36), "blue").save(start)
    Image.new("RGB", (64, 36), "red").save(end)
    wf = db.create_vids_workflow("contract test", duration_per_shot=6)

    def make(**changes):
        args = dict(workflow_id=wf["id"], name="test", prompt="smooth movement",
                    duration=6, mode="image2video", image_url=str(start),
                    end_image_url="", engine="vids")
        args.update(changes)
        return db.create_vids_shot(**args), wf
    return make, str(end)


def task_count():
    conn = db.get_db_connection()
    try:
        return conn.execute("SELECT count(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()


def test_vids_double_frames_rejected_without_changing_engine(shot_factory):
    make, end = shot_factory
    shot, wf = make(mode="first_last_frame", end_image_url=end)
    with pytest.raises(HTTPException) as err:
        _enqueue_shot_task(shot, wf)
    assert err.value.status_code == 422
    assert "Vids" in str(err.value.detail)
    assert task_count() == 0
    assert db.get_vids_shot(shot["id"])["engine"] == "vids"


def test_missing_double_frame_rejected_before_enqueue(shot_factory):
    make, _ = shot_factory
    shot, wf = make(mode="first_last_frame", engine="flow")
    with pytest.raises(HTTPException) as err:
        _enqueue_shot_task(shot, wf)
    assert err.value.status_code == 422
    assert task_count() == 0


def test_missing_input_file_never_degrades_to_text_generation(shot_factory):
    make, _ = shot_factory
    shot, wf = make(image_url="not-a-real-file.png")
    with pytest.raises(HTTPException) as err:
        _enqueue_shot_task(shot, wf)
    assert err.value.status_code == 422
    assert task_count() == 0


def test_queued_shot_is_not_rendering(shot_factory):
    make, _ = shot_factory
    shot, wf = make()
    task_id = _enqueue_shot_task(shot, wf)
    current = db.get_vids_workflow(wf["id"])["shots"][0]
    assert db.get_task(task_id).status == "queued"
    assert current["status"] == "queued"
    assert current["progress"] == 0


def test_resubmission_cannot_orphan_an_active_task(shot_factory):
    make, _ = shot_factory
    shot, wf = make()
    old = Task(id="task_original", prompt="ongoing", engine="vids", status="running")
    db.add_task(old)
    db.update_vids_shot(shot["id"], {"task_id": old.id, "status": "running"})
    shot = db.get_vids_shot(shot["id"])
    with pytest.raises(HTTPException) as err:
        _enqueue_shot_task(shot, wf)
    assert err.value.status_code == 409
    assert task_count() == 1
    assert db.get_task(old.id).status == "running"


def test_corrupt_frame_rejected_before_enqueue(shot_factory, tmp_path):
    make, _ = shot_factory
    frame = tmp_path / "corrupt.png"
    frame.write_bytes(b"not an image")
    shot, wf = make(image_url=str(frame))
    with pytest.raises(HTTPException) as error:
        _enqueue_shot_task(shot, wf)
    assert error.value.status_code == 422
    assert task_count() == 0


def test_flow_duration_contract_enforced():
    from video_farm.video_contract import validate_video_request, VideoRequestError

    # Flow 10s with veo-lite is rejected
    t_invalid = Task(id="test_flow_10s_lite", prompt="test", engine="flow",
                     model="veo-lite", duration_sec=10, aspect_ratio="16:9")
    with pytest.raises(VideoRequestError, match="10秒时长仅支持 Omni"):
        validate_video_request(t_invalid)

    # Flow 10s with omni-flash is valid
    t_valid = Task(id="test_flow_10s_omni", prompt="test", engine="flow",
                   model="omni-flash", duration_sec=10, aspect_ratio="16:9")
    validate_video_request(t_valid)

    # Flow unsupported duration like 12s is rejected
    t_bad_dur = Task(id="test_flow_bad_dur", prompt="test", engine="flow",
                     model="omni-flash", duration_sec=12, aspect_ratio="16:9")
    with pytest.raises(VideoRequestError, match="仅支持 4、6、8、10 秒"):
        validate_video_request(t_bad_dur)
