import os
import tempfile
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import pytest

from minimal_app import db as minimal_db
from minimal_app.db import Base
from minimal_app.models import ProcessingJob
from minimal_app.queue import enqueue_job, acquire_job, complete_job


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_minimal.sqlite")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("minimal_app.db.SessionLocal", Session)
    # ensure queue module's SessionLocal also uses the test Session
    monkeypatch.setattr("minimal_app.queue.SessionLocal", Session, raising=False)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def test_enqueue_acquire_complete():
    enqueue_job(user_id=1, job_type="transcribe", payload={"file_ref": "file_1"})
    # reload persisted row
    with minimal_db.SessionLocal() as s:
        persisted = s.query(ProcessingJob).order_by(ProcessingJob.created_at.desc()).first()
        assert persisted is not None
        job_id = persisted.id
        assert persisted.status == "queued"

    acquired = acquire_job(worker_id="w1")
    assert acquired is not None
    with minimal_db.SessionLocal() as s:
        p2 = s.get(ProcessingJob, acquired.id)
        assert p2.status == "in_progress"

    complete_job(acquired.id)
    with minimal_db.SessionLocal() as s:
        p3 = s.get(ProcessingJob, acquired.id)
        assert p3.status == "completed"
