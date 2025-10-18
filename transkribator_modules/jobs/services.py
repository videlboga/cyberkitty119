"""Default service hooks for media processing pipeline."""

from __future__ import annotations

import asyncio
import pathlib
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from transkribator_modules.config import logger

try:  # Optional dependency
    from transkribator_modules.beta.note_utils import auto_finalize_note as _auto_finalize_note
except ImportError:  # pragma: no cover - best effort
    _auto_finalize_note = None


if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from .pipeline import MediaPipelineContext

PrepareFn = Callable[["MediaPipelineContext"], None]
DownloadFn = Callable[["MediaPipelineContext"], str]
TranscribeFn = Callable[["MediaPipelineContext", str], str]
FinalizeFn = Callable[["MediaPipelineContext", str], Any]
DeliverFn = Callable[["MediaPipelineContext"], None]
CleanupFn = Callable[["MediaPipelineContext"], None]


@dataclass
class MediaPipelineServices:
    """Collection of callables used by media pipeline stages."""

    prepare: PrepareFn
    download: DownloadFn
    transcribe: TranscribeFn
    finalize: FinalizeFn
    deliver: DeliverFn
    cleanup: CleanupFn


def _unimplemented(name: str) -> None:
    logger.error("Pipeline service not implemented", extra={"service": name})
    raise NotImplementedError(f"Pipeline service '{name}' is not implemented yet.")


def default_prepare_environment(context: "MediaPipelineContext") -> None:
    """Prepare temporary workspace for subsequent stages."""
    if "workspace_dir" in context.artifacts:
        return

    base_dir = tempfile.mkdtemp(prefix="transkribator_job_")
    context.artifacts["workspace_dir"] = base_dir
    logger.debug(
        "Workspace prepared",
        extra={"job_id": context.job.id, "workspace": base_dir},
    )


def default_download_media(context: "MediaPipelineContext") -> str:
    """Download media file placeholder."""
    workspace = context.artifacts.get("workspace_dir")
    if not workspace:
        raise RuntimeError("Workspace missing; prepare stage must run first.")

    file_id = context.payload.file_id
    fake_path = pathlib.Path(workspace) / f"{file_id}.media"
    fake_path.touch()
    logger.info(
        "Pretend downloaded media",
        extra={"job_id": context.job.id, "file_id": file_id, "path": str(fake_path)},
    )
    return str(fake_path)


def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Stub transcription that returns placeholder text."""
    logger.info(
        "Pretend transcribing media",
        extra={"job_id": context.job.id, "media_path": media_path},
    )
    return "TRANSCRIPTION_PLACEHOLDER"


def default_finalize_note(context: "MediaPipelineContext", transcript: str) -> Any:
    """Stub finalization that returns metadata."""
    context.artifacts["final_transcript"] = transcript
    note_id = context.payload.note_id

    if note_id is None:
        logger.warning(
            "Finalize stage has no note_id; skipping auto finalize",
            extra={"job_id": context.job.id},
        )
        return {"transcript": transcript}

    note_result = None
    if _auto_finalize_note is None:
        logger.debug(
            "Auto finalize note unavailable; dependency missing",
            extra={"job_id": context.job.id, "note_id": note_id},
        )
    else:
        try:
            note_result = asyncio.run(_auto_finalize_note(note_id))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                note_result = loop.run_until_complete(_auto_finalize_note(note_id))
            finally:
                asyncio.set_event_loop(None)
                loop.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Auto finalize note failed",
                extra={"job_id": context.job.id, "note_id": note_id, "error": str(exc)},
            )

    logger.info(
        "Attempted note finalization",
        extra={
            "job_id": context.job.id,
            "note_id": note_id,
            "transcript_length": len(transcript),
        },
    )
    return note_result or {"transcript": transcript}


def default_deliver_results(context: "MediaPipelineContext") -> None:
    """Stub deliverer that logs completion."""
    logger.info(
        "Pretend delivering results",
        extra={
            "job_id": context.job.id,
            "user_id": context.job.user_id,
            "artifacts": list(context.artifacts.keys()),
        },
    )


def default_cleanup(context: "MediaPipelineContext") -> None:
    workspace = context.artifacts.get("workspace_dir")
    if not workspace:
        return
    base_path = pathlib.Path(workspace)
    try:
        if not base_path.exists():
            return
        for path in sorted(base_path.glob("**/*"), reverse=True):
            if path.is_file() or path.is_symlink():
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    continue
        base_path.rmdir()
        logger.debug(
            "Workspace cleaned",
            extra={"job_id": context.job.id, "workspace": workspace},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Workspace cleanup failed",
            extra={"job_id": context.job.id, "workspace": workspace, "error": str(exc)},
        )


def default_media_services() -> MediaPipelineServices:
    """Return default service implementations."""
    return MediaPipelineServices(
        prepare=default_prepare_environment,
        download=default_download_media,
        transcribe=default_transcribe_media,
        finalize=default_finalize_note,
        deliver=default_deliver_results,
        cleanup=default_cleanup,
    )


__all__ = [
    "MediaPipelineServices",
    "default_media_services",
    "default_prepare_environment",
    "default_download_media",
    "default_transcribe_media",
    "default_finalize_note",
    "default_deliver_results",
    "default_cleanup",
]
