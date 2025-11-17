"""Scaffolding for media processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Sequence

from transkribator_modules.config import logger
from transkribator_modules.db.models import ProcessingJob

from .progress import JobNotifier
from .stages import MediaPipelineStage, default_media_stages
from .services import MediaPipelineServices, default_media_services

if TYPE_CHECKING:  # pragma: no cover
    from .media import MediaJobPayload


@dataclass
class MediaPipelineContext:
    """In-memory context passed across pipeline stages."""

    job: ProcessingJob
    payload: "MediaJobPayload"
    notifier: JobNotifier
    services: MediaPipelineServices = field(default_factory=default_media_services)
    artifacts: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaPipelineResult:
    """Structured result returned by the media pipeline."""

    note_id: Optional[int]
    metadata: Dict[str, Any] = field(default_factory=dict)


def run_media_pipeline(
    context: MediaPipelineContext,
    *,
    stages: Optional[Sequence[MediaPipelineStage]] = None,
) -> MediaPipelineResult:
    """Execute all pipeline stages for the given context."""

    stage_sequence = list(stages or default_media_stages())
    if not stage_sequence:
        logger.warning(
            "Media pipeline invoked without stages",
            extra={"job_id": context.job.id},
        )
        return MediaPipelineResult(
            note_id=context.payload.note_id,
            metadata={"file_id": context.payload.file_id},
        )

    total_weight = sum(max(stage.weight, 1) for stage in stage_sequence)
    accumulated_weight = 0
    cleanup_executed = False

    context.notifier.set_progress(0)

    try:
        for stage in stage_sequence:
            context.notifier.notify(stage.describe())
            try:
                result = stage.run(context)
            except Exception as exc:  # noqa: BLE001 - propagate but log first
                logger.exception(
                    "Media pipeline stage failed",
                    extra={
                        "job_id": context.job.id,
                        "stage": getattr(stage, "name", stage.__class__.__name__),
                    },
                )
                raise
            if result:
                context.artifacts.update(result)
            if getattr(stage, "name", "").lower() == "cleanup":
                cleanup_executed = True
            accumulated_weight += max(stage.weight, 1)
            progress_value = int(accumulated_weight / total_weight * 100)
            context.notifier.set_progress(progress_value)
    except Exception:
        if not cleanup_executed:
            _safe_cleanup(context)
        raise
    else:
        if not cleanup_executed:
            _safe_cleanup(context)
        context.notifier.set_progress(100)

    note = context.artifacts.get("note")
    transcript = context.artifacts.get("transcript")
    logger.info(
        "Media pipeline finished",
        extra={"job_id": context.job.id, "note_id": getattr(note, "id", None)},
    )
    return MediaPipelineResult(
        note_id=getattr(note, "id", context.payload.note_id),
        metadata={
            "transcript_length": len(transcript or ""),
            "file_id": context.payload.file_id,
        },
    )


def _safe_cleanup(context: MediaPipelineContext) -> None:
    try:
        context.services.cleanup(context)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Cleanup hook failed",
            extra={"job_id": context.job.id, "error": str(exc)},
        )


__all__ = [
    "MediaPipelineContext",
    "MediaPipelineResult",
    "run_media_pipeline",
]
