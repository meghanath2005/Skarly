import pytest

from app.services import jobs


def setup_function():
    jobs.clear_jobs()


def test_create_and_get_job():
    created = jobs.create_job({"message": "queued"})
    loaded = jobs.get_job(created["job_id"])

    assert created["job_id"]
    assert loaded["message"] == "queued"
    assert loaded["status"] == "queued"


def test_update_job():
    created = jobs.create_job({"message": "queued"})
    updated = jobs.update_job(created["job_id"], {"status": "completed_mock", "progress": 1.0})

    assert updated["status"] == "completed_mock"
    assert updated["progress"] == 1.0


def test_update_job_rejects_unknown_status():
    created = jobs.create_job({"message": "queued"})

    with pytest.raises(ValueError):
        jobs.update_job(created["job_id"], {"status": "rendering"})


def test_list_jobs():
    jobs.create_job({"message": "one"})
    jobs.create_job({"message": "two"})

    assert len(jobs.list_jobs()) == 2
