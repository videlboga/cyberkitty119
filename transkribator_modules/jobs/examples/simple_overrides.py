"""Example media service overrides for local testing."""

from __future__ import annotations

import pathlib
from typing import Any

from transkribator_modules.config import logger


def prepare(context) -> None:
    workspace = pathlib.Path(context.artifacts.get("workspace_dir", "."))
    context.artifacts["workspace_dir"] = str(workspace)
    logger.info("Example prepare executed", extra={"job_id": context.job.id})


def download(context) -> str:
    workspace = pathlib.Path(context.artifacts["workspace_dir"])
    dummy_path = workspace / "example.media"
    dummy_path.write_text("dummy")
    logger.info("Example download executed", extra={"job_id": context.job.id, "path": str(dummy_path)})
    return str(dummy_path)


def transcribe(context, media_path: str) -> str:
    logger.info("Example transcribe executed", extra={"job_id": context.job.id, "media": media_path})
    return f"Transcribed from {media_path}"


def finalize(context, transcript: str) -> dict[str, Any]:
    context.artifacts["example_transcript"] = transcript
    logger.info("Example finalize executed", extra={"job_id": context.job.id, "length": len(transcript)})
    return {"transcript": transcript}


def deliver(context) -> None:
    logger.info(
        "Example deliver executed",
        extra={"job_id": context.job.id, "artifacts": list(context.artifacts.keys())},
    )


def cleanup(context) -> None:
    workspace = context.artifacts.get("workspace_dir")
    if not workspace:
        return
    path = pathlib.Path(workspace)
    if path.exists():
        for file in path.glob("example.media"):
            file.unlink(missing_ok=True)
    logger.info("Example cleanup executed", extra={"job_id": context.job.id})


def build() -> dict[str, object]:
    """Return mapping usable by build_services."""
    return {
        "prepare": prepare,
        "download": download,
        "transcribe": transcribe,
        "finalize": finalize,
        "deliver": deliver,
        "cleanup": cleanup,
    }


__all__ = ["build", "prepare", "download", "transcribe", "finalize", "deliver", "cleanup"]
