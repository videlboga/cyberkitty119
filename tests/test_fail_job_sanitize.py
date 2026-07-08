"""Tests for fail_job traceback sanitization."""
from __future__ import annotations

import os
import tempfile

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from transkribator_modules.db import database as db_module
from transkribator_modules.db.models import Base, User, ProcessingJob
from transkribator_modules.jobs.queue import enqueue_job, fail_job

os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite://")


@pytest.fixture(autouse=True)
def inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_fail_job_tests.sqlite")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert inspector.has_table("users")
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr("transkribator_modules.db.database.SessionLocal", Session)
    db_module.SessionLocal = Session
    monkeypatch.setattr("transkribator_modules.jobs.queue.SessionLocal", Session, raising=False)

    yield

    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def test_fail_job_stores_short_message():
    """fail_job with a normal error message stores it as-is."""
    with db_module.SessionLocal() as session:
        user = User(telegram_id=12345, username="test_user")
        session.add(user)
        session.commit()
        user_id = user.id

    enqueue_job(user_id=user_id, job_type="transcribe", payload={"file": "test.mp3"})

    with db_module.SessionLocal() as session:
        fresh = session.query(ProcessingJob).filter(
            ProcessingJob.user_id == user_id
        ).order_by(ProcessingJob.created_at.desc()).first()
        job_id = fresh.id

    fail_job(job_id, error_message="Transcription failed: HTTP 429: rate limited")

    with db_module.SessionLocal() as session:
        fresh = session.get(ProcessingJob, job_id)
        assert fresh.status == "failed"
        assert "Traceback" not in fresh.error
        assert "Transcription failed" in fresh.error


def test_fail_job_santizes_traceback():
    """fail_job with a raw traceback replaces it with generic message."""
    with db_module.SessionLocal() as session:
        user = User(telegram_id=12346, username="test_user2")
        session.add(user)
        session.commit()
        user_id = user.id

    enqueue_job(user_id=user_id, job_type="transcribe", payload={"file": "test2.mp3"})

    with db_module.SessionLocal() as session:
        fresh = session.query(ProcessingJob).filter(
            ProcessingJob.user_id == user_id
        ).order_by(ProcessingJob.created_at.desc()).first()
        job_id = fresh.id

    raw_traceback = (
        "Traceback (most recent call last):\n"
        '  File "/app/job_worker.py", line 199, in _handle_failure\n'
        "    raise RuntimeError(\"boom\")\n"
        "RuntimeError: boom"
    )
    fail_job(job_id, error_message=raw_traceback)

    with db_module.SessionLocal() as session:
        fresh = session.get(ProcessingJob, job_id)
        assert fresh.status == "failed"
        assert "Traceback" not in fresh.error
        assert fresh.error == "Internal processing error"