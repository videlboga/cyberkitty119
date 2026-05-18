import os
import tempfile

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import pytest

from transkribator_modules.db import database as db_module
from transkribator_modules.db.models import Base, User, ProcessingJob
from transkribator_modules.jobs.queue import enqueue_job, acquire_job, complete_job

import os
import tempfile

# Ensure models select JSON vs JSONB correctly for tests
os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import pytest

from transkribator_modules.db import database as db_module
from transkribator_modules.db.models import Base, User
from transkribator_modules.jobs.queue import enqueue_job, acquire_job, complete_job


@pytest.fixture(autouse=True)
def inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_job_queue_tests.sqlite")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert inspector.has_table("users")
    Session = sessionmaker(bind=engine)

    # Patch the project's SessionLocal to use the test session
    monkeypatch.setattr("transkribator_modules.db.database.SessionLocal", Session)
    # also update local import if other modules cached it
    db_module.SessionLocal = Session
    # ensure modules that imported SessionLocal directly also use the test Session
    monkeypatch.setattr("transkribator_modules.jobs.queue.SessionLocal", Session, raising=False)

    yield

    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def test_enqueue_and_acquire_flow():
    # create a user for FK constraint
    with db_module.SessionLocal() as session:
        user = User(telegram_id=9999, username="queue_tester")
        session.add(user)
        session.commit()
        user_id = user.id

    # enqueue a job
    job = enqueue_job(user_id=user_id, job_type="transcribe", payload={"file": "file_16.mp4"})
    # don't rely on returned detached instance for attributes; query fresh row
    with db_module.SessionLocal() as session:
        fresh = session.query(ProcessingJob).filter(ProcessingJob.user_id == user_id).order_by(ProcessingJob.created_at.desc()).first()
        assert fresh is not None
        job_id = fresh.id
        assert fresh.status == "queued"

    # acquire a job for processing
    acquired = acquire_job(worker_id="worker-1", job_types=None)
    assert acquired is not None
    # acquired is expunged from session in acquire_job; re-query to verify persisted state
    with db_module.SessionLocal() as session:
        persisted = session.get(ProcessingJob, acquired.id)
        assert persisted is not None
        assert persisted.status == "in_progress"
        assert persisted.locked_by == "worker-1"

    # complete the job and verify status
    complete_job(acquired.id)
    with db_module.SessionLocal() as session:
        fresh2 = session.get(ProcessingJob, acquired.id)
        assert fresh2.status == "completed"
