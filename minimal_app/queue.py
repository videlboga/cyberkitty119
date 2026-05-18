from contextlib import contextmanager
from typing import Optional, Dict, Any
import datetime as dt
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from .db import SessionLocal, get_engine
from .models import ProcessingJob
from .config import JOB_LOCK_TIMEOUT_SECONDS


def _utcnow():
    return dt.datetime.utcnow()


@contextmanager
def _session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def enqueue_job(*, user_id: Optional[int] = None, job_type: str, payload: Dict[str, Any]):
    job = ProcessingJob(user_id=user_id, job_type=job_type, status="queued", payload=payload or {})
    with _session_scope() as session:
        session.add(job)
        session.flush()
        session.refresh(job)
        return job


def acquire_job(*, worker_id: str, job_types: Optional[list[str]] = None):
    """Acquire next queued job. This is a simple implementation suitable for single-process tests.
    For production with Postgres, use SELECT ... FOR UPDATE SKIP LOCKED.
    """
    now = _utcnow()
    engine = get_engine()
    dialect = getattr(engine, "dialect", None)

    # Postgres: use SELECT ... FOR UPDATE SKIP LOCKED to safely acquire across processes
    if dialect is not None and getattr(dialect, "name", "") in ("postgresql", "psycopg2"):
        with _session_scope() as session:
            q = select(ProcessingJob).where(ProcessingJob.status == "queued")
            if job_types:
                q = q.where(ProcessingJob.job_type.in_(job_types))
            q = q.order_by(ProcessingJob.created_at.asc()).limit(1).with_for_update(skip_locked=True)
            result = session.execute(q).scalars().first()
            if not result:
                return None
            # mark in progress inside the same transaction holding the row lock
            result.status = "in_progress"
            result.locked_by = worker_id
            result.locked_at = now
            result.attempts = (result.attempts or 0) + 1
            if not result.started_at:
                result.started_at = now
            session.flush()
            # detach and return
            session.expunge(result)
            return result

    # Fallback (SQLite, tests): simple select-then-update
    with _session_scope() as session:
        q = select(ProcessingJob).where(ProcessingJob.status == "queued")
        if job_types:
            q = q.where(ProcessingJob.job_type.in_(job_types))
        q = q.order_by(ProcessingJob.created_at.asc()).limit(1)
        result = session.execute(q).scalars().first()
        if not result:
            return None
        # mark in progress
        result.status = "in_progress"
        result.locked_by = worker_id
        result.locked_at = now
        result.attempts = (result.attempts or 0) + 1
        if not result.started_at:
            result.started_at = now
        session.flush()
        # return an expunged (detached) instance
        session.expunge(result)
        return result


def complete_job(job_id: int):
    with _session_scope() as session:
        j = session.get(ProcessingJob, job_id)
        if not j:
            return
        j.status = "completed"
        j.finished_at = _utcnow()
        j.locked_by = None
        j.locked_at = None
        session.flush()


def fail_job(job_id: int, error_message: str):
    with _session_scope() as session:
        j = session.get(ProcessingJob, job_id)
        if not j:
            return
        j.status = "failed"
        j.finished_at = _utcnow()
        j.error = error_message[:4000]
        j.locked_by = None
        j.locked_at = None
        session.flush()
