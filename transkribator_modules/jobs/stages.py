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


class ExtractAudioStage(MediaPipelineStage):
    """Извлекает аудио из видео файлов перед транскрибацией."""
    name = "extract_audio"
    weight = 2

    def describe(self) -> str:
        return "Извлекаю аудио"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        media_path = context.artifacts.get("media_path")
        if not media_path:
            raise RuntimeError("Media path is missing; download stage must run first.")
            
        import asyncio
        from pathlib import Path
        from transkribator_modules.audio.extractor import extract_audio_from_video, compress_audio_for_api
        
        path_obj = Path(media_path)
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".3gp"}
        
        # Если это не видео, пропускаем
        if path_obj.suffix.lower() not in video_exts:
            return None
            
        # Извлекаем аудио (pcm_s16le кодек в extractor несовместим с .ogg — используем .wav)
        audio_path_obj = path_obj.with_suffix(".wav")
        success = asyncio.run(extract_audio_from_video(media_path, str(audio_path_obj)))
        if not success:
            raise RuntimeError("Failed to extract audio from video")
            
        # Сжимаем
        compressed_audio = asyncio.run(compress_audio_for_api(str(audio_path_obj)))
        
        # Обновляем media_path
        return {"media_path": str(compressed_audio)}


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


class TranscribeMediaGPUStage(MediaPipelineStage):
    """GPU-accelerated transcription stage using local Whisper model."""
    name = "transcribe_media_gpu"
    weight = 4

    def describe(self) -> str:
        return "GPU Транскрибирую"

    def run(self, context: "MediaPipelineContext") -> Optional[Dict[str, Any]]:
        """Execute GPU transcription using WhisperPipeline."""
        import time
        from pathlib import Path
        
        from transkribator_modules.config import logger
        
        media_path = context.artifacts.get("media_path")
        if not media_path:
            raise RuntimeError("Media path is missing; download stage must run first.")
        
        try:
            from pipeline_orchestrator import WhisperPipeline
            
            logger.info(
                "Starting GPU transcription",
                extra={"job_id": context.job.id, "media_path": media_path}
            )
            
            start_time = time.monotonic()
            pipeline = WhisperPipeline()
            result = pipeline.process(Path(media_path))
            elapsed = time.monotonic() - start_time
            
            if result["status"] != "success":
                raise RuntimeError(f"GPU transcription failed: {result.get('error', 'Unknown error')}")
            
            # Read transcription from result file
            result_file = result.get("result_file")
            if result_file and Path(result_file).exists():
                import json
                with open(result_file) as f:
                    transcription_data = json.load(f)
                    transcript = transcription_data.get("text", "")
            else:
                transcript = result.get("transcription_text", "")
            
            logger.info(
                "GPU transcription completed",
                extra={
                    "job_id": context.job.id,
                    "elapsed_seconds": round(elapsed, 2),
                    "transcript_length": len(transcript),
                }
            )
            
            return {
                "transcript": transcript,
                "gpu_job_id": result.get("job_id"),
                "gpu_transcription_time": result.get("transcription_time"),
            }
            
        except ImportError:
            logger.error("WhisperPipeline not available; cannot perform GPU transcription")
            raise RuntimeError("GPU pipeline not available")
        except Exception as exc:
            logger.exception("GPU transcription failed")
            raise


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
        ExtractAudioStage(),
        TranscribeMediaStage(),
        FinalizeNoteStage(),
        DeliverResultsStage(),
        CleanupStage(),
    ]


def default_media_gpu_stages() -> list[MediaPipelineStage]:
    """Return GPU-optimized pipeline for media jobs."""
    return [
        PrepareEnvironmentStage(),
        DownloadMediaStage(),
        ExtractAudioStage(),
        TranscribeMediaGPUStage(),  # Use GPU transcription
        FinalizeNoteStage(),
        DeliverResultsStage(),
        CleanupStage(),
    ]


__all__ = [
    "MediaPipelineStage",
    "PrepareEnvironmentStage",
    "DownloadMediaStage",
    "ExtractAudioStage",
    "TranscribeMediaStage",
    "TranscribeMediaGPUStage",
    "FinalizeNoteStage",
    "DeliverResultsStage",
    "CleanupStage",
    "default_media_stages",
    "default_media_gpu_stages",
]
