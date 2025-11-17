"""Pipeline stage definitions for media processing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .pipeline import MediaPipelineContext


class MediaPipelineStage(ABC):
    """Base class for a pipeline stage."""

    name: str = "stage"
    weight: int = 1

    def describe(self) -> str:
        return self.name

    @abstractmethod
    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        """Execute stage and optionally return artifact updates."""


class PrepareEnvironmentStage(MediaPipelineStage):
    name = "prepare_environment"
    weight = 1

    def describe(self) -> str:
        return "Готовлю окружение"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        context.services.prepare(context)
        return None


class DownloadMediaStage(MediaPipelineStage):
    name = "download_media"
    weight = 3

    def describe(self) -> str:
        return "Скачиваю медиа"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        media_path = context.services.download(context)
        if not media_path:
            raise ValueError("Downloader did not return media path.")
        return {"media_path": media_path}


class TranscribeMediaStage(MediaPipelineStage):
    name = "transcribe_media"
    weight = 4

    def describe(self) -> str:
        return "Транскрибирую"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        media_path = context.artifacts.get("media_path")
        if not media_path:
            raise RuntimeError("Media path is missing; download stage must run first.")
        transcript = context.services.transcribe(context, media_path)
        if transcript is None:
            raise ValueError("Transcriber returned None.")
        return {"transcript": transcript}


class FinalizeNoteStage(MediaPipelineStage):
    name = "finalize_note"
    weight = 2

    def describe(self) -> str:
        return "Обновляю заметку"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        transcript = context.artifacts.get("transcript")
        if transcript is None:
            raise RuntimeError("Transcript is missing; transcription stage must run first.")
        note = context.services.finalize(context, transcript)
        if note is None:
            return None
        return {"note": note}


class DeliverResultsStage(MediaPipelineStage):
    name = "deliver_results"
    weight = 1

    def describe(self) -> str:
        return "Отправляю результат"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        context.services.deliver(context)
        return None


class CleanupStage(MediaPipelineStage):
    name = "cleanup"
    weight = 1

    def describe(self) -> str:
        return "Прибираю временные файлы"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        context.services.cleanup(context)
        return None


def default_media_stages() -> list[MediaPipelineStage]:
    """Return default stage pipeline for media jobs."""
    return [
        PrepareEnvironmentStage(),
        DownloadMediaStage(),
        TranscribeMediaStage(),
        FinalizeNoteStage(),
        DeliverResultsStage(),
        CleanupStage(),
    ]


__all__ = [
    "MediaPipelineStage",
    "PrepareEnvironmentStage",
    "DownloadMediaStage",
    "TranscribeMediaStage",
    "FinalizeNoteStage",
    "DeliverResultsStage",
    "CleanupStage",
    "default_media_stages",
]
