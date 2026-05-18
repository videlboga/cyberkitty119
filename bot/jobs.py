from __future__ import annotations

import httpx
from bot.config import logger, INTERNAL_BOT_API_BASE, CORE_API_TIMEOUT, core_api_headers

class FakeProcessingJob:
    def __init__(self, id):
        self.id = id

def create_media_job(
    *,
    user_id: int,
    telegram_id: int,
    file_id: str,
    audio_path: str,
    message_id: int,
):
    try:
        with httpx.Client(timeout=CORE_API_TIMEOUT) as client:
            resp = client.post(
                f"{INTERNAL_BOT_API_BASE}/jobs/enqueue_media",
                json={
                    "user_id": user_id,
                    "telegram_id": telegram_id,
                    "file_id": file_id,
                    "audio_path": audio_path,
                    "message_id": message_id
                },
                headers=core_api_headers(),
            )
            resp.raise_for_status()
            job_id = resp.json().get("job_id")
            logger.info("Создана задача job_id=%s file_id=%s audio_path=%s", job_id, file_id, audio_path)
            return FakeProcessingJob(job_id)
    except Exception as e:
        logger.error(f"Error creating job: {e}")
        return None
