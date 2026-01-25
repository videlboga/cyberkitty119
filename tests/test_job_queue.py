import pytest

from transkribator_modules.jobs.queue import enqueue_job


def test_enqueue_job_returns_job_dict():
    payload = {"user_id": 123, "media_file_id": "file_16.mp4"}
    job = enqueue_job(payload)
    assert isinstance(job, dict)
    assert job.get("status") == "queued"
    assert job.get("payload") is payload
