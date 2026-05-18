"""Create media job for Max messenger.

This mirrors `bot/jobs.py` but stores provider-specific extra metadata.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Optional

from transkribator_modules.db.models import ProcessingJob
from transkribator_modules.jobs.media import MediaJobPayload, enqueue_media_job
from max_bot.config import logger


def create_media_job(
    *,
    user_id: int,
    max_user_id: str,
    file_id: str,
    audio_path: str,
    message_id: Optional[str] = None,
) -> ProcessingJob:
    payload = MediaJobPayload(
        file_id=file_id,
        message_id=message_id,
        extra={
            "audio_path": audio_path,
            "max_user_id": max_user_id,
            "provider": "max",
        },
    )

    job = enqueue_media_job(
        user_id=user_id,
        payload=payload,
    )

    logger.info(
        "Создана задача (max) job_id=%s file_id=%s audio_path=%s",
        job.id, file_id, audio_path,
    )
    return job
