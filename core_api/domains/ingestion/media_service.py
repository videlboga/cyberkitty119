from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from transkribator_modules.db.database import UserService
from transkribator_modules.db.models import ProcessingJob
from transkribator_modules.jobs.media import MediaJobPayload, enqueue_media_job

logger = logging.getLogger(__name__)


class MediaIngestionError(Exception):
    """Base exception for ingestion domain."""


class JobNotFoundError(MediaIngestionError):
    """Raised when requested job does not exist."""


@dataclass(slots=True)
class JobStatus:
    id: int
    status: str
    progress: float
    error: Optional[str]
    stage: Optional[str]
    stage_label: Optional[str]
    stage_progress: Optional[float]
    result_transcript: Optional[str]
    note_id: Optional[int]


class MediaIngestionService:
    """Доменные операции захвата/очереди медиа."""

    def __init__(self, db: Session):
        self.db = db
        self._user_service = UserService(db)

    def enqueue_media_job(self, *, telegram_id: int, file_id: str, audio_path: str, message_id: Optional[int]) -> int:
        """Поставить медиа-файл в очередь обработки."""
        if not file_id:
            raise MediaIngestionError("Не указан file_id.")

        user = self._user_service.get_or_create_user(telegram_id=telegram_id)

        payload = MediaJobPayload(
            file_id=file_id,
            message_id=message_id,
            extra={
                "audio_path": audio_path,
                "telegram_id": telegram_id,
            },
        )
        try:
            job = enqueue_media_job(user_id=user.id, payload=payload)
        except Exception as exc:  # pragma: no cover - защитный блок
            logger.exception("Failed to enqueue media job", extra={"telegram_id": telegram_id})
            raise MediaIngestionError("Не удалось поставить задачу в очередь.") from exc

        return int(job.id)

    def get_job_status(self, job_id: int) -> JobStatus:
        job = self.db.get(ProcessingJob, job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")

        payload = self._ensure_dict(job.payload)
        status_blob = self._ensure_dict(payload.get("_status"))
        result_blob = self._ensure_dict(payload.get("_result"))

        stage_progress = status_blob.get("stage_progress")
        try:
            stage_progress = float(stage_progress) if stage_progress is not None else None
        except (TypeError, ValueError):
            stage_progress = None

        note_id = payload.get("note_id") or getattr(job, "note_id", None)
        if not note_id:
            note_id = result_blob.get("note_id")

        transcript = result_blob.get("final_transcript") or result_blob.get("raw_transcript")

        try:
            progress_value = float(job.progress or 0.0)
        except (TypeError, ValueError):
            progress_value = 0.0

        return JobStatus(
            id=job.id,
            status=job.status,
            progress=progress_value,
            error=job.error,
            stage=status_blob.get("stage"),
            stage_label=status_blob.get("stage_label"),
            stage_progress=stage_progress,
            result_transcript=transcript,
            note_id=note_id,
        )

    @staticmethod
    def _ensure_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}
