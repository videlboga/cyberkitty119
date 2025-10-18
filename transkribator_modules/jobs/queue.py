"""Database-backed job queue helpers."""

from __future__ import annotations

import contextlib
import datetime as dt
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from transkribator_modules.config import logger, DATABASE_URL
from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import ProcessingJob, ProcessingJobStatus

LOCK_TIMEOUT_SECONDS = int(
    float(
        # give ability to override if needed
        (  # pragma: no cover - env fallback
            __import__("os").environ.get("JOB_LOCK_TIMEOUT_SECONDS", "600")
        )
    )
)


def _utcnow() -> dt.datetime:
    return dt.datetime.utcnow()


@contextlib.contextmanager
def _session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def enqueue_job(
    *,
    user_id: int,
    job_type: str,
    payload: dict[str, Any],
    note_id: Optional[int] = None,
) -> ProcessingJob:
    """Create a new processing job."""
    job = ProcessingJob(
        user_id=user_id,
        note_id=note_id,
        job_type=job_type,
        status=ProcessingJobStatus.QUEUED.value,
        payload=payload or {},
    )
    with _session_scope() as session:
        session.add(job)
        session.flush()
        session.refresh(job)
        logger.info("Job enqueued", extra={"job_id": job.id, "job_type": job_type, "user_id": user_id})
        return job


def _backend_supports_skip_locked() -> bool:
    return DATABASE_URL.startswith("postgresql")


def acquire_job(
    *,
    worker_id: str,
    job_types: Optional[list[str]] = None,
) -> Optional[ProcessingJob]:
    """Pick the next queued job and lock it for processing."""
    now = _utcnow()
    with _session_scope() as session:
        job = _fetch_job_for_update(session, job_types, now)
        if not job:
            return None

        job.status = ProcessingJobStatus.IN_PROGRESS.value
        job.locked_by = worker_id
        job.locked_at = now
        job.attempts = (job.attempts or 0) + 1
        if not job.started_at:
            job.started_at = now
        session.flush()
        session.expunge(job)
        logger.debug("Job acquired", extra={"job_id": job.id, "worker_id": worker_id})
        return job


def _fetch_job_for_update(
    session: Session,
    job_types: Optional[list[str]],
    now: dt.datetime,
) -> Optional[ProcessingJob]:
    filters = [ProcessingJob.status == ProcessingJobStatus.QUEUED.value]
    if job_types:
        filters.append(ProcessingJob.job_type.in_(job_types))

    query = (
        select(ProcessingJob)
        .where(and_(*filters))
        .order_by(ProcessingJob.created_at.asc())
        .limit(1)
    )

    if _backend_supports_skip_locked():
        try:
            result = session.execute(query.with_for_update(skip_locked=True)).scalar_one_or_none()
            if result:
                return result
        except OperationalError:
            logger.warning("FOR UPDATE SKIP LOCKED failed; falling back to non-locking query.")

    result = session.execute(query).scalar_one_or_none()
    if result:
        timeout_threshold = now - dt.timedelta(seconds=LOCK_TIMEOUT_SECONDS)
        if (
            result.status == ProcessingJobStatus.IN_PROGRESS.value
            and result.locked_at
            and result.locked_at > timeout_threshold
        ):
            return None
        if result.status == ProcessingJobStatus.IN_PROGRESS.value:
            # Reclaim stale job
            logger.info("Reclaiming stale job", extra={"job_id": result.id})
    return result


def mark_job_progress(job_id: int, *, progress: Optional[int] = None) -> None:
    with _session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            logger.warning("Progress update skipped; job missing", extra={"job_id": job_id})
            return
        job.progress = progress
        job.locked_at = _utcnow()
        session.flush()


def complete_job(job_id: int) -> None:
    with _session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            logger.warning("Completion skipped; job missing", extra={"job_id": job_id})
            return
        job.status = ProcessingJobStatus.COMPLETED.value
        job.finished_at = _utcnow()
        job.locked_by = None
        job.locked_at = None
        session.flush()
        logger.info("Job completed", extra={"job_id": job_id})


def fail_job(job_id: int, error_message: str) -> None:
    with _session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            logger.warning("Fail skipped; job missing", extra={"job_id": job_id})
            return
        job.status = ProcessingJobStatus.FAILED.value
        job.finished_at = _utcnow()
        job.error = error_message[:4000]
        job.locked_by = None
        job.locked_at = None
        session.flush()
        logger.error("Job failed", extra={"job_id": job_id, "error": error_message})


def release_job(job_id: int) -> None:
    """Return job to queue (e.g., graceful shutdown)."""
    with _session_scope() as session:
        job = session.get(ProcessingJob, job_id)
        if not job:
            return
        job.status = ProcessingJobStatus.QUEUED.value
        job.locked_by = None
        job.locked_at = None
        session.flush()
