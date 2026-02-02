import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest

from minimal_app.db import Base, SessionLocal as RealSession
from minimal_app import db as minimal_db
from minimal_app.models import ProcessingJob, Transcription
from minimal_app.queue import enqueue_job
from minimal_app.worker import run_once


@pytest.fixture(autouse=True)
def setup_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_minimal_pipeline.sqlite")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("minimal_app.db.SessionLocal", Session)
    # ensure modules that imported SessionLocal also use the test session
    monkeypatch.setattr("minimal_app.queue.SessionLocal", Session, raising=False)
    monkeypatch.setattr("minimal_app.worker.SessionLocal", Session, raising=False)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def test_pipeline_enqueue_worker_creates_transcription():
    # enqueue a job
    enqueue_job(user_id=42, job_type="transcribe", payload={"file_ref": "file_a.mp4"})

    # run a single worker iteration
    job_id = run_once(worker_id="w1")
    assert job_id is not None

    # verify job completed and transcription created
    with minimal_db.SessionLocal() as s:
        tr = s.query(Transcription).filter(Transcription.job_id == job_id).one_or_none()
        assert tr is not None
        assert "Transcript of" in tr.raw_transcript
