"""MEDIA_SERVICE_OVERRIDES factory: download via yt-dlp and transcribe via OpenRouter (sync wrapper).

This module is intended for local E2E testing. The factory `build` returns a mapping
compatible with `build_services` where `download` uses the built-in yt-dlp downloader
and `transcribe` is a small synchronous adapter that calls the async transcribe_audio
implementation using `asyncio.run`.
"""
from __future__ import annotations

import asyncio
from typing import Any

from transkribator_modules.config import logger


def sync_transcribe(context, media_path: str) -> str:
    """Synchronous wrapper that runs the async `transcribe_audio` and returns text.

    Uses asyncio.run to execute the coroutine in a fresh event loop. Exceptions
    are propagated so the worker will mark the job failed on error.
    """
    try:
        # Import inside function to avoid circular imports at module load time
        from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio

        logger.info("Sync transcribe called", extra={"job_id": context.job.id, "media_path": media_path})
        return asyncio.run(transcribe_audio(media_path))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sync transcribe failed", extra={"job_id": getattr(context.job, 'id', None), 'error': str(exc)})
        raise


def build() -> dict[str, Any]:
    """Return overrides mapping for `build_services`.

    - download: use the pipeline helper in `transkribator_modules.jobs.services` (vk_ytdlp_download_mp3)
    - transcribe: use the synchronous wrapper above
    """
    return {
        "download": "transkribator_modules.jobs.services:vk_ytdlp_download_mp3",
        "transcribe": sync_transcribe,
    }


__all__ = ["build", "sync_transcribe"]
