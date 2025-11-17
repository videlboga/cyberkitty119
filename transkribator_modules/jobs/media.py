"""Media processing job definitions and helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from transkribator_modules.config import logger, load_media_service_overrides
from transkribator_modules.db.models import ProcessingJob

from .pipeline import MediaPipelineContext, run_media_pipeline
from .service_factory import build_services
from .progress import JobNotifier
from .queue import enqueue_job

MEDIA_JOB_TYPE = "media_processing"


@dataclass
class MediaJobPayload:
    """Serializable payload describing media to process."""

    file_id: str
    message_id: Optional[int] = None
    file_unique_id: Optional[str] = None
    note_id: Optional[int] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "message_id": self.message_id,
            "file_unique_id": self.file_unique_id,
            "note_id": self.note_id,
            "extra": self.extra,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "MediaJobPayload":
        if "file_id" not in data or data.get("file_id") is None:
            raise ValueError("Media job payload must include 'file_id'.")
        return cls(
            file_id=str(data["file_id"]),
            message_id=data.get("message_id"),
            file_unique_id=data.get("file_unique_id"),
            note_id=data.get("note_id"),
            extra=dict(data.get("extra") or {}),
        )


def enqueue_media_job(
    *,
    user_id: int,
    payload: MediaJobPayload,
) -> ProcessingJob:
    """Schedule media processing for the given user."""
    job = enqueue_job(
        user_id=user_id,
        job_type=MEDIA_JOB_TYPE,
        payload=payload.to_dict(),
        note_id=payload.note_id,
    )
    logger.debug(
        "Media job enqueued",
        extra={"job_id": job.id, "user_id": user_id, "note_id": payload.note_id},
    )
    return job


def process_media_job(job: ProcessingJob) -> None:
    """Execute the media processing pipeline for the given job."""
    try:
        payload = MediaJobPayload.from_mapping(job.payload or {})
    except ValueError as exc:
        logger.error(
            "Bad media job payload",
            extra={"job_id": job.id, "payload": job.payload, "error": str(exc)},
        )
        raise

    notifier = JobNotifier(job.id)
    services_config = load_media_service_overrides()
    services = build_services(services_config)
    context = MediaPipelineContext(
        job=job,
        payload=payload,
        notifier=notifier,
        services=services,
    )

    logger.info(
        "Media job handler invoked",
        extra={
            "job_id": job.id,
            "user_id": job.user_id,
            "file_id": payload.file_id,
            "note_id": payload.note_id,
        },
    )
    result = run_media_pipeline(context)
    notifier.notify("Обработка завершена")
    logger.info(
        "Media job completed",
        extra={
            "job_id": job.id,
            "note_id": result.note_id,
            "metadata": result.metadata,
        },
    )


__all__ = ["MediaJobPayload", "MEDIA_JOB_TYPE", "enqueue_media_job", "process_media_job"]
