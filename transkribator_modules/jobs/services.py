"""Default service hooks for media processing pipeline."""

from __future__ import annotations

import asyncio
import os
import pathlib
import tempfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, NoteService
from transkribator_modules.db.models import NoteStatus, User

try:  # Optional dependency
    from transkribator_modules.note_utils import auto_finalize_note as _auto_finalize_note
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
    """Download media file or use pre-downloaded audio from handlers."""
    workspace = context.artifacts.get("workspace_dir")
    if not workspace:
        raise RuntimeError("Workspace missing; prepare stage must run first.")

    file_id = context.payload.file_id
    
    # Check if audio was already prepared by bot handler (non-blocking path)
    audio_path = context.payload.extra.get("audio_path")
    if audio_path:
        path_obj = pathlib.Path(audio_path)
        if path_obj.exists():
            logger.info(
                f"Using pre-downloaded audio from bot handler: {audio_path}",
                extra={"job_id": context.job.id, "file_id": file_id, "audio_path": audio_path},
            )
            return audio_path
        else:
            logger.warning(
                f"Pre-downloaded audio path does not exist. Path checked: {audio_path}. Payload extras: {context.payload.extra}",
                extra={"job_id": context.job.id, "audio_path": audio_path},
            )
    
    # Fallback: create placeholder
    fake_path = pathlib.Path(workspace) / f"{file_id}.media"
    fake_path.touch()
    logger.info(
        "Using placeholder media path",
        extra={"job_id": context.job.id, "file_id": file_id, "path": str(fake_path)},
    )
    return str(fake_path)


def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Transcribe media using TranscribeClient with configurable backend."""
    logger.info(
        "Transcribe media (default hook)",
        extra={"job_id": context.job.id, "media_path": media_path},
    )

    # Use new transcribe_client abstraction (now enabled by default)
    try:
        from transcribe_client import TranscribeClient

        # Get transcription mode from environment, default to "gpu" if available, else "auto"
        mode = os.environ.get("TRANSCRIBE_DEFAULT_MODE", "gpu")
        
        logger.info(
            "Initializing TranscribeClient",
            extra={"job_id": context.job.id, "mode": mode},
        )
        
        client = TranscribeClient(default_mode=mode)
        result = client.transcribe(media_path, mode=mode)
        
        logger.info(
            "TranscribeClient result",
            extra={
                "status": result.get("status"),
                "job_id": context.job.id,
                "meta": result.get("meta", {})
            }
        )
        
        if result.get("status") == "ok":
            text = result.get("text", "")
            context.artifacts["transcription_meta"] = result.get("meta")
            segments_payload = result.get("segments")
            if isinstance(segments_payload, list):
                context.artifacts["segments"] = segments_payload
            logger.info(
                "Transcription successful",
                extra={
                    "job_id": context.job.id,
                    "text_length": len(text),
                    "model": result.get("model"),
                }
            )
            return text
        else:
            error_msg = result.get("meta", {}).get("error", "Unknown error")
            logger.warning(
                "Transcribe client returned error",
                extra={
                    "job_id": context.job.id,
                    "error": error_msg,
                },
            )
            return f"⚠️ Ошибка при обработке аудио: {error_msg}"
    
    except Exception as exc:  # pragma: no cover - fallback
        logger.exception("Transcribe client invocation failed", extra={"job_id": context.job.id})
        error_msg = f"⚠️ Не удалось обработать файл: {str(exc)[:100]}"
        return error_msg


def _format_transcript_text(transcript: str) -> str:
    if not transcript or not transcript.strip():
        return transcript
    try:
        from transkribator_modules.transcribe.transcriber_v4 import _postprocess_full_transcript
    except ImportError:  # pragma: no cover - formatting optional
        return transcript

    try:
        return asyncio.run(_postprocess_full_transcript(transcript))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_postprocess_full_transcript(transcript))
        finally:
            asyncio.set_event_loop(None)
            loop.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Formatting transcript failed",
            extra={"error": str(exc)[:200]},
        )
        return transcript


def default_finalize_note(context: "MediaPipelineContext", transcript: str) -> Any:
    """Stub finalization that returns metadata."""
    raw_transcript = transcript
    context.artifacts["raw_transcript"] = raw_transcript
    formatted_transcript = _format_transcript_text(raw_transcript)
    context.artifacts["final_transcript"] = formatted_transcript
    note_id = context.payload.note_id

    created_note = None
    if note_id is None:
        db = SessionLocal()
        try:
            note_owner = db.get(User, context.job.user_id)
            if not note_owner:
                logger.warning(
                    "Finalize stage cannot create note – user missing",
                    extra={"job_id": context.job.id, "user_id": context.job.user_id},
                )
            else:
                note_service = NoteService(db)
                payload_meta = {
                    "job_id": context.job.id,
                    "file_id": context.payload.file_id,
                }
                try:
                    created_note = note_service.create_note(
                        user=note_owner,
                        text=formatted_transcript,
                        summary=None,
                        type_hint="transcription",
                        status=NoteStatus.INGESTED.value,
                        meta=payload_meta,
                    )
                    note_id = created_note.id
                    context.payload.note_id = note_id
                    logger.info(
                        "Created note for media job",
                        extra={
                            "job_id": context.job.id,
                            "note_id": note_id,
                            "user_id": context.job.user_id,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to create note during finalize stage",
                        extra={"job_id": context.job.id, "error": str(exc)},
                    )
        finally:
            db.close()

    if note_id is None:
        logger.warning(
            "Finalize stage has no note_id; skipping auto finalize",
            extra={"job_id": context.job.id},
        )
        return {"transcript": transcript}

    context.artifacts["note_id"] = note_id

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
    final_note = note_result or created_note
    if final_note is not None:
        context.artifacts["note"] = final_note
        return {"note": final_note, "note_id": note_id}
    return {"note_id": note_id, "transcript": formatted_transcript}


def _persist_result_to_job_payload(context: "MediaPipelineContext") -> None:
    """Persist transcript/note reference into job payload for the bot."""
    transcript = context.artifacts.get("final_transcript")
    raw_transcript = context.artifacts.get("raw_transcript")
    note_id = context.artifacts.get("note_id")
    segments = context.artifacts.get("segments")
    if not transcript and not note_id and not raw_transcript:
        return

    from transkribator_modules.db.models import ProcessingJob

    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, context.job.id)
        if not job:
            return
        payload = dict(job.payload or {})
        result_blob = dict(payload.get("_result") or {})
        if transcript:
            result_blob["final_transcript"] = transcript
        if raw_transcript:
            result_blob.setdefault("raw_transcript", raw_transcript)
        if note_id:
            result_blob["note_id"] = note_id
            if not job.note_id:
                job.note_id = note_id
        if segments:
            result_blob["segments"] = segments
        if not result_blob:
            return
        payload["_result"] = result_blob
        job.payload = payload
        db.commit()
        logger.debug(
            "Saved artifacts to job payload",
            extra={
                "job_id": context.job.id,
                "has_transcript": bool(transcript),
                "note_id": note_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to persist result to job payload",
            extra={"job_id": context.job.id, "error": str(exc)},
        )
    finally:
        db.close()


def default_deliver_results(context: "MediaPipelineContext") -> None:
    """Deliver result to Telegram using Bot API."""
    from transkribator_modules.config import BOT_TOKEN, LOCAL_BOT_API_URL, USE_LOCAL_BOT_API
    import httpx

    # Сохранить транскрипцию в payload._result — новый бот читает её оттуда
    _persist_result_to_job_payload(context)

    logger.info(
        "Delivering results via HTTP",
        extra={
            "job_id": context.job.id,
            "user_id": context.job.user_id,
            "artifacts": list(context.artifacts.keys()),
        },
    )
    
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN is not set, skipping delivery")
        return

    db = SessionLocal()
    try:
        user = db.get(User, context.job.user_id)
        if not user or not user.telegram_id:
            logger.warning("No user or telegram_id for job delivery")
            return

        is_max = getattr(context.job.payload, "extra", {}).get("platform") == "max"
        chat_id = getattr(context.job.payload, "extra", {}).get("chat_id")

        note_id = context.artifacts.get("note_id")
        transcript = context.artifacts.get("final_transcript")
        
        if note_id:
            message_text = "✅ Обработка завершена!"
        elif transcript:
            message_text = f"✅ Ваша расшифровка:\n{transcript}"
            if len(message_text) > 4000:
                message_text = message_text[:3990] + "..."
        else:
            message_text = "✅ Ваша задача обработана, текст не найден."

        if is_max:
            # MAX delivery is handled by max_bot/native_handlers.py via polling
            logger.info("MAX delivery skipped in worker, handled by max_bot_poller.")
            return

        if USE_LOCAL_BOT_API:
            base_url = (LOCAL_BOT_API_URL or "").rstrip("/")
            if not base_url:
                logger.error("USE_LOCAL_BOT_API enabled but LOCAL_BOT_API_URL empty; cannot deliver results")
                return
            url = f"{base_url}/bot{BOT_TOKEN}/sendMessage"
        else:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

        note_id = context.artifacts.get("note_id")
        transcript = context.artifacts.get("final_transcript")

        if note_id:
            message_text = "✅ Обработка завершена!"
        elif transcript:
            if len(transcript) > 4000:
                message_text = f"✅ Обработка завершена! Текст длинный.\nНачало:\n{transcript[:1500]}..."
            else:
                message_text = f"✅ Ваша расшифровка:\n{transcript}"
        else:
            message_text = "✅ Ваша задача обработана, текст не найден."

        payload = {
            "chat_id": user.telegram_id,
            "text": message_text,
            "parse_mode": "HTML",
        }

        if getattr(context.payload, "message_id", None):
            payload["reply_parameters"] = {"message_id": context.payload.message_id}

        with httpx.Client(proxies=None, timeout=15) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error("Failed to send telegram message", extra={"status": resp.status_code, "resp": resp.text})
            else:
                logger.info("Successfully delivered results to user via Telegram")

    except Exception:
        logger.exception("Error in Telegram HTTP delivery", extra={"job_id": context.job.id})
    finally:
        db.close()


def default_cleanup(context: "MediaPipelineContext") -> None:
    # 1. Clean up pre-downloaded audio path if it was passed
    audio_path = context.payload.extra.get("audio_path")
    if audio_path:
        audio_path_obj = pathlib.Path(audio_path)
        if audio_path_obj.exists() and audio_path_obj.is_file():
            try:
                audio_path_obj.unlink()
                logger.debug("Cleaned up pre-downloaded audio", extra={"job_id": context.job.id, "audio_path": str(audio_path_obj)})
            except Exception as exc:
                logger.warning("Failed to clean up pre-downloaded audio", extra={"job_id": context.job.id, "audio_path": str(audio_path_obj), "error": str(exc)})

    # 2. Clean up workspace directory
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


def vk_ytdlp_download_mp3(context: "MediaPipelineContext") -> str:
    """
    Download audio from VK/YouTube (or any yt-dlp supported) and save as mp3.
    Expects context.payload to have 'url' (VK/YouTube link).
    Returns path to mp3 file as string.
    """
    from .vk_ytdlp_downloader import download_vk_or_youtube_audio_mp3
    workspace = context.artifacts.get("workspace_dir")
    url = getattr(context.payload, "url", None) or context.payload.extra.get("url")
    if not url:
        raise ValueError("Media job payload must include 'url' for VK/YouTube download.")
    mp3_path = download_vk_or_youtube_audio_mp3(url, workspace)
    logger.info(
        "Downloaded mp3 via yt-dlp",
        extra={"job_id": context.job.id, "url": url, "mp3_path": str(mp3_path)},
    )
    return str(mp3_path)
