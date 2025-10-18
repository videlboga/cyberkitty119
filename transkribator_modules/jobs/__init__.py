"""Job queue utilities package."""

from .queue import (
    enqueue_job,
    acquire_job,
    mark_job_progress,
    complete_job,
    fail_job,
    release_job,
)
from .handlers import (
    register_handler,
    unregister_handler,
    dispatch_job,
    get_handler,
    registry,
    UnknownJobTypeError,
)
from .media import (
    MediaJobPayload,
    MEDIA_JOB_TYPE,
    enqueue_media_job,
    process_media_job,
)
from .progress import JobNotifier
from .pipeline import MediaPipelineContext, MediaPipelineResult, run_media_pipeline
from .stages import (
    MediaPipelineStage,
    PrepareEnvironmentStage,
    DownloadMediaStage,
    TranscribeMediaStage,
    FinalizeNoteStage,
    DeliverResultsStage,
    CleanupStage,
    default_media_stages,
)
from .service_factory import build_services
from .services import (
    MediaPipelineServices,
    default_media_services,
    default_prepare_environment,
    default_download_media,
    default_transcribe_media,
    default_finalize_note,
    default_deliver_results,
    default_cleanup,
)
from .examples import simple_overrides
from .bootstrap import register_builtin_handlers

__all__ = [
    "enqueue_job",
    "acquire_job",
    "mark_job_progress",
    "complete_job",
    "fail_job",
    "release_job",
    "register_handler",
    "unregister_handler",
    "dispatch_job",
    "get_handler",
    "registry",
    "UnknownJobTypeError",
    "MediaJobPayload",
    "MEDIA_JOB_TYPE",
    "enqueue_media_job",
    "process_media_job",
    "JobNotifier",
    "MediaPipelineContext",
    "MediaPipelineResult",
    "run_media_pipeline",
    "MediaPipelineStage",
    "PrepareEnvironmentStage",
    "DownloadMediaStage",
    "TranscribeMediaStage",
    "FinalizeNoteStage",
    "DeliverResultsStage",
    "CleanupStage",
    "default_media_stages",
    "build_services",
    "MediaPipelineServices",
    "default_media_services",
    "default_prepare_environment",
    "default_download_media",
    "default_transcribe_media",
    "default_finalize_note",
    "default_deliver_results",
    "default_cleanup",
    "simple_overrides",
    "register_builtin_handlers",
]
