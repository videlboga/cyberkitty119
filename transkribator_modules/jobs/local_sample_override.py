"""MEDIA_SERVICE_OVERRIDES factory for local sample file testing.

This override copies the repository `sample.wav` into the job workspace and
returns its path so the pipeline can transcribe it. Uses the same sync_transcribe
adapter as the OpenRouter override.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from transkribator_modules.config import logger


def download_sample(context) -> str:
    workspace = Path(context.artifacts.get("workspace_dir", "."))
    workspace_path = Path(workspace)
    workspace_path.mkdir(parents=True, exist_ok=True)
    src = Path("/app/sample.wav")
    if not src.exists():
        logger.error("Sample file not found", extra={"job_id": context.job.id, "path": str(src)})
        raise FileNotFoundError(f"Sample file not found: {src}")
    dest = workspace_path / src.name
    shutil.copy2(src, dest)
    logger.info("Sample file copied to workspace", extra={"job_id": context.job.id, "dest": str(dest)})
    return str(dest)


def sync_transcribe(context, media_path: str) -> str:
    # Lazy import to avoid circulars
    import asyncio
    from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio

    logger.info("Sync transcribe called for local sample", extra={"job_id": context.job.id, "media_path": media_path})
    return asyncio.run(transcribe_audio(media_path))


def build() -> dict[str, Any]:
    return {
        "download": download_sample,
        "transcribe": sync_transcribe,
    }


__all__ = ["build"]
