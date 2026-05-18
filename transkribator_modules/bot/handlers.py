"""
Обработчики сообщений для CyberKitty Transkribator
"""

import asyncio
import subprocess
import tempfile
import time
import html
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.audio.extractor import extract_audio_from_video, compress_audio_for_api
from transkribator_modules.note_utils import auto_finalize_note
from transkribator_modules.config import (
    logger,
    MAX_FILE_SIZE_MB,
    VIDEOS_DIR,
    AUDIO_DIR,
    TRANSCRIPTIONS_DIR,
    BOT_TOKEN,
    SUPPRESS_FAILURE_MESSAGES,
)
from transkribator_modules.wai_flow import wai_progress_placeholder, wai_menu_command, MAIN_MENU_BUTTON_TEXT
from transkribator_modules.manual_mode import manual_handle_message
from transkribator_modules.db.database import (
    SessionLocal,
    UserService,
    TranscriptionService,
    NoteService,
    log_telegram_event,
    log_event,
    get_media_duration,
)
from transkribator_modules.db.models import User, NoteStatus
from transkribator_modules.bot.logging_utils import log_step
from transkribator_modules.bot.commands import promo_codes_command
from transkribator_modules.transcribe.transcriber_v4 import (
    _postprocess_full_transcript,
    _basic_local_format,
    request_llm_response,
    generate_brief_summary,
    _load_segments_cache,
    _save_segments_cache,
)
from transkribator_modules.utils.large_file_downloader import download_large_file, get_file_info
from transkribator_modules.bot.processing_guard import guard
from transkribator_modules.bot.update_dedupe import should_process, should_process_message
from transkribator_modules.jobs.media import MediaJobPayload, enqueue_media_job


@dataclass(frozen=True)
class _YoutubeArtifacts:
    video_path: Path
    audio_path: Path
    transcript: str
    title: str
    video_id: str
    workspace: Path
    info: dict[str, Any]

def clean_html_entities(text: str) -> str:
    """Минимальная очистка текста: только удаление HTML-тегов.
    Не удаляем не-ASCII, чтобы не портить кириллицу. parse_mode=None.
    """
    if not text:
        return text
    return re.sub(r'<[^>]*>', '', text)


def _resolve_reply_target(update: Update):
    if getattr(update, "message", None):
        return update.message
    if getattr(update, "callback_query", None) and update.callback_query.message:
        return update.callback_query.message
    return None


async def _notify_free_quota_if_needed(update: Update, context: ContextTypes.DEFAULT_TYPE, user) -> None:
    message_text: str | None = None

    if getattr(user, "_was_created", False):
        message_text = (
            "🎁 В бесплатном тарифе доступны 3 видео в месяц. Используй их, чтобы попробовать все возможности."
        )
        setattr(user, "_was_created", False)
    elif getattr(user, "_usage_reset", False):
        message_text = "🔄 Лимит бесплатного тарифа обновился — снова доступны 3 бесплатные загрузки на этот месяц."
        setattr(user, "_usage_reset", False)

    if not message_text:
        return

    target = _resolve_reply_target(update)
    if target:
        await target.reply_text(message_text)
    else:
        effective_user = update.effective_user
        if effective_user:
            await context.bot.send_message(chat_id=effective_user.id, text=message_text)

# --- Helpers for the simplified processing/result flow ---

def _format_timestamp(total_seconds: float | int | None) -> str:
    if total_seconds is None:
        return "00:00"
    try:
        seconds = max(0, int(total_seconds))
    except Exception:
        seconds = 0
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_timecode_text(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for segment in segments or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_timestamp(segment.get("start"))
        end = _format_timestamp(segment.get("end"))
        lines.append(f"[{start} - {end}] {text}")
    return "\n".join(lines)


async def _fetch_segments_with_client(audio_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Best-effort attempt to obtain segments via transcribe_client (local Whisper)."""
    cached = _load_segments_cache(audio_path)
    if cached:
        return cached
    try:
        from transcribe_client import TranscribeClient
    except Exception:
        return [], None

    mode = os.getenv("TRANSCRIBE_DEFAULT_MODE", "auto")
    client = TranscribeClient(default_mode=mode)
    try:
        result = await asyncio.to_thread(client.transcribe, str(audio_path), mode)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to fetch segments via transcribe_client", extra={"error": str(exc)})
        return [], None

    if not isinstance(result, dict):
        return [], None
    segments = result.get("segments") or []
    transcript = result.get("text")
    _save_segments_cache(audio_path, segments, transcript)
    return segments, transcript


async def _generate_summary_text(transcript: str) -> str | None:
    if not transcript or not transcript.strip():
        return None
    summary = None
    try:
        summary = await generate_brief_summary(transcript)
        if summary and summary.strip():
            return summary.strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to generate summary via LLM", extra={"error": str(exc)})
    return _fallback_summary_text(transcript)


def _fallback_summary_text(transcript: str, *, limit: int = 320) -> str | None:
    """Simple local summarizer used when LLM summary is unavailable."""
    text = (transcript or "").strip()
    if not text:
        return None

    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not sentences:
        sentences = [text]
    summary = " ".join(sentences[:2]).strip()
    if not summary:
        summary = text[:limit].strip()
    if len(summary) > limit:
        summary = summary[: limit - 1].rstrip() + "…"
    return summary


def _store_last_result(context: ContextTypes.DEFAULT_TYPE, payload: dict[str, Any]) -> None:
    context.chat_data["last_transcription_result"] = payload


def _get_last_result(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    return context.chat_data.get("last_transcription_result")


def _clear_last_result(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.pop("last_transcription_result", None)


def _clear_question_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.pop("qa_session", None)


def _start_question_session(context: ContextTypes.DEFAULT_TYPE, transcript: str, summary: str | None) -> None:
    context.chat_data["qa_session"] = {
        "transcript": transcript,
        "summary": summary or "",
        "history": [],
    }


def _prepare_new_media(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Сбрасывает сохранённые результаты и QA-сессию перед новой обработкой."""
    _clear_last_result(context)
    _clear_question_session(context)


async def _handle_question_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session = context.chat_data.get("qa_session")
    if not session:
        return
    question = (update.message.text or "").strip()
    if not question:
        return

    transcript = session.get("transcript") or ""
    summary = session.get("summary") or ""
    history: list[dict[str, str]] = session.setdefault("history", [])

    history_text = ""
    for item in history[-5:]:
        q = item.get("q", "")
        a = item.get("a", "")
        if q and a:
            history_text += f"Вопрос: {q}\nОтвет: {a}\n\n"

    transcript_excerpt = transcript[:6000]
    system_prompt = (
        "Ты помогаешь с вопросами по одному транскрибированному файлу. "
        "Отвечай по существу, используй информацию из транскрипта. "
        "Если вопрос не связан с файлом, можешь отвечать как обычный ИИ."
    )
    user_prompt = (
        f"Краткое содержание:\n{summary}\n\n"
        f"Фрагмент транскрипта:\n{transcript_excerpt}\n\n"
        f"История диалога:\n{history_text}\n"
        f"Вопрос пользователя: {question}\n\n"
        "Дай развёрнутый ответ на русском языке."
    )

    answer = None
    try:
        answer = await request_llm_response(system_prompt, user_prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("QA LLM request failed", extra={"error": str(exc)})

    if not answer:
        answer = "Не удалось получить ответ. Попробуйте сформулировать вопрос иначе."

    history.append({"q": question, "a": answer})
    await update.message.reply_text(answer)


async def _deliver_transcription_result(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status_msg,
    *,
    summary: str | None,
    filename: str,
    file_size_mb: float | None,
    text_path: str,
    timecodes_path: str,
    transcript: str,
    source_url: str | None = None,
) -> None:
    payload = {
        "text_path": text_path,
        "timecodes_path": timecodes_path,
        "transcript": transcript,
        "summary": summary,
        "filename": filename,
        "file_size_mb": file_size_mb,
        "source_url": source_url,
    }
    _store_last_result(context, payload)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📄 Скачать текст", callback_data="result:download_text")],
            [InlineKeyboardButton("🔎 Задать вопросы", callback_data="result:ask")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main:menu")],
        ]
    )

    result_message = "✅ Обработка завершена!\n\n"
    if summary:
        result_message += f"📝 {summary}\n\n"
    if source_url:
        result_message += f"🔗 Оригинал: {source_url}\n\n"
    result_message += "Выберите действие:"

    try:
        if status_msg:
            await status_msg.edit_text(result_message, reply_markup=keyboard)
        elif update.message:
            await update.message.reply_text(result_message, reply_markup=keyboard)
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id if update.effective_chat else update.effective_user.id,
                text=result_message,
                reply_markup=keyboard,
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to send result message", extra={"error": str(exc)})


def _write_transcript_files(base_name: str, body: str, segments: list[dict[str, Any]]) -> tuple[str, str]:
    TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    text_path = TRANSCRIPTIONS_DIR / f"{base_name}.txt"
    needs_newline = body and not body.endswith("\n")
    text_path.write_text(body + ("\n" if needs_newline else ""), encoding="utf-8")

    timecodes_text = _build_timecode_text(segments) if segments else ""
    if not timecodes_text:
        timecodes_text = "Таймкоды недоступны для этого файла."
    timecodes_path = TRANSCRIPTIONS_DIR / f"{base_name}_timecodes.txt"
    timecodes_path.write_text(timecodes_text, encoding="utf-8")
    return str(text_path), str(timecodes_path)


async def _finalize_transcription_output(
    *,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status_msg,
    user,
    transcription_service: TranscriptionService,
    filename: str,
    file_size_mb: float | None,
    duration_minutes: float | None,
    base_name: str,
    transcript: str,
    audio_reference: Path | None = None,
    source_url: str | None = None,
) -> None:
    """Форматирует текст, сохраняет заметку и показывает итоговое меню."""
    formatted_transcript: str | None = None
    raw_transcript = transcript or ""

    if transcript:
        try:
            formatted_transcript = await _postprocess_full_transcript(transcript)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Postprocess failed", extra={"error": str(exc)})

    # Используем локальный Whisper для таймкодов + альтернативного текста
    segments: list[dict[str, Any]] = []
    if audio_reference and audio_reference.exists():
        segments, alt_text = await _fetch_segments_with_client(audio_reference)
        if alt_text and len(alt_text) > len(raw_transcript):
            raw_transcript = alt_text
            try:
                formatted_transcript = await _postprocess_full_transcript(alt_text)
            except Exception:
                pass

    transcript_body = (formatted_transcript or raw_transcript or "").strip()
    if not transcript_body:
        if status_msg:
            await status_msg.edit_text("❌ Не удалось создать транскрипцию")
        elif update.message:
            await update.message.reply_text("❌ Не удалось создать транскрипцию")
        return

    summary = await _generate_summary_text(transcript_body)
    text_path, timecodes_path = _write_transcript_files(base_name, transcript_body, segments)

    try:
        transcription_service.save_transcription(
            user=user,
            filename=filename,
            file_size_mb=file_size_mb,
            audio_duration_minutes=duration_minutes,
            raw_transcript=raw_transcript,
            formatted_transcript=transcript_body,
            processing_time=0.0,
            transcription_service="openrouter",
            formatting_service="llm",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to save transcription", extra={"error": str(exc)})

    created_note_id: int | None = None
    note_db = SessionLocal()
    try:
        note_user = note_db.get(User, user.id)
        if note_user:
            note_service = NoteService(note_db)
            payload_meta = {"transcription_file": base_name}
            logger.debug(
                "Creating note from transcription",
                extra={
                    "user_id": user.id,
                    "summary_chars": len(summary or ""),
                    "text_chars": len(transcript_body),
                    "raw_link": source_url,
                    "meta": payload_meta,
                },
            )
            try:
                note = note_service.create_note(
                    user=note_user,
                    text=transcript_body,
                    summary=summary,
                    type_hint="transcription",
                    status=NoteStatus.INGESTED.value,
                    raw_link=source_url,
                    meta=payload_meta,
                )
                created_note_id = note.id
                logger.info(
                    "Created note from transcription",
                    extra={"note_id": note.id, "user_id": user.id},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to create note from transcription",
                    extra={"error": str(exc), "user_id": user.id},
                )
    finally:
        note_db.close()

    if created_note_id:
        try:
            await auto_finalize_note(created_note_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Auto finalize note failed",
                extra={"note_id": created_note_id, "error": str(exc)},
            )
        try:
            payload = MediaJobPayload(
                file_id=base_name,
                message_id=getattr(getattr(update, "effective_message", None), "message_id", None),
                note_id=created_note_id,
                extra={
                    "filename": filename,
                    "source_url": source_url,
                    "platform": getattr(update, "provider_platform", "telegram"),
                    "chat_id": update.effective_chat.id if update.effective_chat else None,
                },
            )
            enqueue_media_job(user_id=user.id, payload=payload)
            logger.debug(
                "Enqueued media job for post-processing",
                extra={"note_id": created_note_id, "user_id": user.id},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Failed to enqueue media job",
                extra={"note_id": created_note_id, "error": str(exc)},
            )

    await _deliver_transcription_result(
        update,
        context,
        status_msg,
        summary=summary,
        filename=filename,
        file_size_mb=file_size_mb,
        text_path=text_path,
        timecodes_path=timecodes_path,
        transcript=transcript_body,
        source_url=source_url,
    )


def _classify_media_file(path: Path) -> tuple[bool, bool]:
    ext = path.suffix.lower()
    is_video = ext in VIDEO_FORMATS
    is_audio = ext in AUDIO_FORMATS
    if not is_video and not is_audio:
        try:
            import magic  # type: ignore

            mime = magic.from_file(str(path), mime=True)
            is_video = mime.startswith("video/")
            is_audio = mime.startswith("audio/")
        except Exception:  # noqa: BLE001
            return False, False
    return is_video, is_audio


async def _prepare_audio_file(file_path: Path, status_msg) -> tuple[Path, bool]:
    is_video, is_audio = _classify_media_file(file_path)
    if not is_video and not is_audio:
        return file_path, False
    if is_video or file_path.suffix.lower() != ".wav":
        await _safe_edit_message(status_msg, "🎛️ Конвертирую аудио…")
        converted = await asyncio.to_thread(_convert_to_wav, file_path)
        return converted, True
    return file_path, True


async def _process_external_audio(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    status_msg,
    audio_path: Path,
    filename: str,
    file_size_mb: float | None,
    source_url: str | None = None,
) -> None:
    """Отправляет локальный файл (после загрузки из облака) в очередь обработки."""
    # Получить пользователя и проверить лимит ПЕРЕД добавлением в очередь
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        duration_minutes = get_media_duration(str(video_path))
        can_use, limit_message = user_service.check_usage_limit(user)
        await _notify_free_quota_if_needed(update, context, user)
        if not can_use:
            if status_msg:
                await status_msg.edit_text(f"❌ {limit_message}")
            elif update.message:
                await update.message.reply_text(f"❌ {limit_message}")
            return

        # Зарезервировать минуты СЕЙЧАС (до обработки)
        user_service.add_usage(user, duration_minutes)
        user_id = user.id
    finally:
        db.close()

    # Отправить в очередь ВМЕСТО блокирующей транскрипции
    base_name = f"external_{audio_path.stem}_{int(time.time())}"
    try:
        if status_msg:
            await status_msg.edit_text("✅ Файл принят! Транскрипция началась…\n⏱️ Это может занять некоторое время.")

        payload = MediaJobPayload(
            file_id=base_name,
            message_id=getattr(getattr(update, "effective_message", None), "message_id", None),
            extra={
                "audio_path": str(audio_path),
                "filename": filename,
                "file_size_mb": file_size_mb,
                "duration_minutes": duration_minutes,
                "source_url": source_url,
                "source_type": "external",
                "platform": getattr(update, "provider_platform", "telegram"),
                "chat_id": update.effective_chat.id if update.effective_chat else None,
            },
        )
        enqueue_media_job(user_id=user_id, payload=payload)
        logger.info(
            "Enqueued external audio for processing (non-blocking)",
            extra={
                "user_id": user_id,
                "file_id": base_name,
                "source_url": source_url,
                "duration_minutes": duration_minutes,
            },
        )
        try:
            log_event(
                user,
                "external_audio_queued_for_processing",
                {
                    "filename": filename,
                    "duration_minutes": duration_minutes,
                    "file_size_mb": file_size_mb,
                    "source": source_url,
                },
            )
        except Exception:
            logger.debug("Failed to log external audio queued event", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to enqueue external audio processing job",
            extra={"error": str(exc), "base_name": base_name},
        )
        if status_msg:
            await status_msg.edit_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")
        elif update.message:
            await update.message.reply_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")

# Поддерживаемые форматы
VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp'}
AUDIO_FORMATS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}

_YOUTUBE_URL_RE = re.compile(
    r"(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)[\w-]+(?:[^\s]*)?|youtu\.be/[\w-]+(?:[^\s]*)?))",
    re.IGNORECASE,
)
_VK_VIDEO_URL_RE = re.compile(
    r"(https?://(?:www\.)?(?:vkvideo\.ru|vk\.com)/(?:video|clip)?[-\w]+)",
    re.IGNORECASE,
)

async def generate_friendly_title_async(transcript: str, timestamp: datetime | None = None) -> str:
    """
    Асинхронно генерирует дружелюбное название транскрипции с помощью LLM.
    
    Пример: "2025-11-05 • Встреча про проект"
    """
    import re
    
    if timestamp is None:
        timestamp = datetime.now()
    
    # Форматируем дату в формате YYYY-MM-DD
    date_str = timestamp.strftime("%Y-%m-%d")
    
    # Пробуем сгенерировать умное название с помощью LLM
    try:
        from transkribator_modules.transcribe.transcriber_v4 import generate_title_with_llm
        smart_title = await generate_title_with_llm(transcript)
        if smart_title and len(smart_title.strip()) > 3:
            # Используем LLM-название
            return f"{date_str} • {smart_title}"
    except Exception as e:
        logger.debug(f"Не удалось сгенерировать умное название: {e}")
    
    # Fallback: используем первые значимые слова из транскрипции
    # Убираем лишние пробелы и знаки препинания
    clean_text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', transcript[:300])  # Первые 300 символов
    words = [w for w in clean_text.split() if len(w) > 2]  # Только слова длиннее 2 символов
    
    # Берём первые 4-5 значимых слов
    if len(words) >= 5:
        content = ' '.join(words[:5])
    elif len(words) >= 4:
        content = ' '.join(words[:4])
    elif len(words) >= 3:
        content = ' '.join(words[:3])
    elif len(words) >= 2:
        content = ' '.join(words[:2])
    elif len(words) >= 1:
        content = words[0]
    else:
        content = "Транскрипция"
    
    # Ограничиваем длину
    if len(content) > 45:
        content = content[:42] + "..."
    
    return f"{date_str} • {content}"

def generate_friendly_title(transcript: str, timestamp: datetime | None = None) -> str:
    """
    Синхронная обёртка для generate_friendly_title_async.
    Использует простой fallback без LLM для синхронных вызовов.
    
    Пример: "31 окт • Встреча про проект"
    """
    import re
    
    if timestamp is None:
        timestamp = datetime.now()
    
    # Форматируем дату
    months = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
    date_str = f"{timestamp.day} {months[timestamp.month - 1]}"
    
    # Простой подход - первые 2-3 слова (для синхронных вызовов)
    clean_text = re.sub(r'[^\w\s\u0400-\u04FF]', ' ', transcript[:200])
    words = [w for w in clean_text.split() if len(w) > 2]
    
    if len(words) >= 3:
        content = ' '.join(words[:3])
    elif len(words) >= 2:
        content = ' '.join(words[:2])
    elif len(words) >= 1:
        content = words[0]
    else:
        content = "Транскрипция"
    
    # Ограничиваем длину
    if len(content) > 40:
        content = content[:37] + "..."
    
    return f"{date_str} • {content}"

def _schedule_background_task(
    context: ContextTypes.DEFAULT_TYPE,
    coro,  # type: ignore[var-annotated]
    *,
    description: str,
) -> None:
    """Запускает корутину в фоне и логирует необработанные исключения."""

    task = context.application.create_task(coro)

    def _on_done(finished_task: asyncio.Task) -> None:
        try:
            finished_task.result()
        except asyncio.CancelledError:
            logger.info(
                "Фоновая задача отменена",
                extra={"description": description},
            )
        except Exception as exc:  # noqa: BLE001 - хотим видеть стек
            logger.exception(
                "Ошибка фоновой задачи",
                extra={"description": description, "error": str(exc)},
            )

    task.add_done_callback(_on_done)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    log_step(update, "bot_start_command")
    # Делегируем формирование приветствия модулю команд, чтобы единообразно
    # показывать обновлённое меню и уведомления про бесплатные лимиты.
    from transkribator_modules.bot.commands import start_command as commands_start_command

    await commands_start_command(update, context)
    try:
        log_telegram_event(
            update.effective_user,
            "command_start",
            {"chat_id": update.effective_chat.id if update.effective_chat else None},
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to log /start event", exc_info=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """📖 **Справка по CyberKitty Transkribator**

**Основные возможности:**
• Транскрипция видео и аудио файлов
• Поддержка файлов до 2 ГБ
• Автоматическое извлечение аудио из видео
• ИИ-форматирование текста

**Команды:**
/start - Начать работу
/help - Показать эту справку
/status - Проверить статус бота

**Поддерживаемые форматы:**

🎥 **Видео:** MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V, 3GP
🎵 **Аудио:** MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS

**Ограничения:**
• Максимальный размер файла: 2 ГБ
• Максимальная длительность: 4 часа

**Как это работает:**
1. Вы отправляете файл
2. Если это видео - я извлекаю аудио
3. Аудио отправляется в AI API для транскрипции
4. Текст форматируется с помощью LLM
5. Вы получаете готовую транскрипцию

Просто отправьте файл и я начну обработку! 🚀"""

    await update.message.reply_text(help_text, parse_mode='Markdown')
    try:
        log_telegram_event(
            update.effective_user,
            "command_help",
            {"chat_id": update.effective_chat.id if update.effective_chat else None},
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to log /help event", exc_info=True)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    status_text = """✅ **Статус CyberKitty Transkribator**

🤖 Бот: Активен
🌐 Telegram Bot API Server: Активен
🎵 Обработка аудио: Доступна
🎥 Обработка видео: Доступна
🧠 ИИ транскрипция: Подключена
📝 ИИ форматирование: Активно

**Настройки:**
• Макс. размер файла: 2 ГБ
• Макс. длительность: 4 часа
• Форматы видео: 9 поддерживаемых
• Форматы аудио: 8 поддерживаемых

Готов к работе! 🚀"""

    await update.message.reply_text(status_text, parse_mode='Markdown')
    try:
        log_telegram_event(
            update.effective_user,
            "command_status",
            {"chat_id": update.effective_chat.id if update.effective_chat else None},
        )
    except Exception:  # noqa: BLE001
        logger.debug("Failed to log /status event", exc_info=True)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик документов (файлов)"""
    document = update.message.document

    if not document:
        await update.message.reply_text("❌ Не удалось получить информацию о файле.")
        return

    # Логируем получение документа
    try:
        log_telegram_event(
            update.effective_user,
            "message_document",
            {
                "chat_id": update.effective_chat.id if update.effective_chat else None,
                "file_id": document.file_id,
                "file_name": document.file_name,
                "file_size": document.file_size,
                "mime_type": document.mime_type,
            }
        )
    except Exception:
        logger.debug("Failed to log document message", exc_info=True)

    # Проверяем размер файла
    file_size_mb = document.file_size / (1024 * 1024) if document.file_size else 0

    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Файл слишком большой: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return

    # Определяем тип файла по расширению
    file_extension = Path(document.file_name).suffix.lower() if document.file_name else ''

    if file_extension in VIDEO_FORMATS:
        _prepare_new_media(context)
        status_msg = await wai_progress_placeholder(update, context)
        _schedule_background_task(
            context,
            process_video_file(update, context, document, status_message=status_msg),
            description="document_video_processing",
        )
    elif file_extension in AUDIO_FORMATS:
        _prepare_new_media(context)
        status_msg = await wai_progress_placeholder(update, context)
        _schedule_background_task(
            context,
            process_audio_file(update, context, document, status_message=status_msg),
            description="document_audio_processing",
        )
    else:
        await update.message.reply_text(
            f"❌ Неподдерживаемый формат файла: {file_extension}\n\n"
            f"Поддерживаемые форматы:\n"
            f"🎥 Видео: {', '.join(sorted(VIDEO_FORMATS))}\n"
            f"🎵 Аудио: {', '.join(sorted(AUDIO_FORMATS))}"
        )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_step(update, "message_video_received")
    """Обработчик видео файлов"""
    video = update.message.video

    if not video:
        await update.message.reply_text("❌ Не удалось получить информацию о видео.")
        return

    # Проверяем размер файла
    file_size_mb = video.file_size / (1024 * 1024) if video.file_size else 0

    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Видео слишком большое: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return

    _prepare_new_media(context)
    status_msg = await wai_progress_placeholder(update, context)

    _schedule_background_task(
        context,
        process_video_file(update, context, video, status_message=status_msg),
        description="video_processing",
    )

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    log_step(update, "message_audio_or_voice_received")
    """Обработчик аудио файлов"""
    audio = update.message.audio or update.message.voice

    if not audio:
        await update.message.reply_text("❌ Не удалось получить информацию об аудио.")
        return

    # Проверяем размер файла
    file_size_mb = audio.file_size / (1024 * 1024) if audio.file_size else 0

    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Аудио слишком большое: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return

    _prepare_new_media(context)
    status_msg = await wai_progress_placeholder(update, context)

    _schedule_background_task(
        context,
        process_audio_file(update, context, audio, status_message=status_msg),
        description="audio_processing",
    )

async def process_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE, video_file, *, status_message=None) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else 0
    message_id = update.effective_message.message_id if update.effective_message else 0
    async with guard(chat_id, message_id) as proceed:
        if not proceed:
            return

    log_step(
        update,
        "process_video_file:start",
        {
            "file_id": getattr(video_file, "file_id", None),
            "file_size": getattr(video_file, "file_size", None),
            "duration": getattr(video_file, "duration", None),
        },
    )

    file_size_mb = video_file.file_size / (1024 * 1024) if video_file.file_size else 0
    filename = getattr(video_file, "file_name", f"video_{video_file.file_id}")
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    status_msg = status_message
    _prepare_new_media(context)

    if not status_msg and not is_group and update.message:
        status_msg = await update.message.reply_text("Файл принят! Готовлю обработку…")

    video_path = VIDEOS_DIR / f"telegram_video_{video_file.file_id}.mp4"
    audio_path = AUDIO_DIR / f"telegram_audio_{video_file.file_id}.wav"

    last_progress = [0.0]

    async def progress_callback(downloaded: int, total: int) -> None:
        if not status_msg or not total:
            return
        now = time.time()
        if now - last_progress[0] < 1.5:
            return
        last_progress[0] = now
        percent = int(downloaded / total * 100)
        filled = int(percent / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        try:
            await status_msg.edit_text(
                f"🎬 Загружаю видео…\n📊 Размер: {file_size_mb:.1f} МБ\n{bar} {percent}%"
            )
        except Exception:
            pass

    try:
        success = await download_large_file(
            bot_token=BOT_TOKEN,
            file_id=video_file.file_id,
            destination=video_path,
            progress_callback=progress_callback,
            expected_size_bytes=getattr(video_file, "file_size", None) or int(file_size_mb * 1024 * 1024),
            file_url=getattr(video_file, "file_url", None),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Video download failed", extra={"error": str(exc)})
        success = False

    if not success:
        if status_msg:
            await status_msg.edit_text("❌ Не удалось скачать видео. Попробуйте позже.")
        elif not SUPPRESS_FAILURE_MESSAGES and update.message:
            await update.message.reply_text("❌ Не удалось скачать видео. Попробуйте позже.")
        return

    if status_msg:
        try:
            await status_msg.edit_text("🎵 Подготовка видео…")
        except Exception:
            pass

    # Получить пользователя и проверить лимит ПЕРЕД добавлением в очередь
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )
        duration_minutes = get_media_duration(str(video_path))
        can_use, limit_message = user_service.check_usage_limit(user)
        await _notify_free_quota_if_needed(update, context, user)
        if not can_use:
            if status_msg:
                await status_msg.edit_text(f"❌ {limit_message}")
            elif not SUPPRESS_FAILURE_MESSAGES and update.message:
                await update.message.reply_text(f"❌ {limit_message}")
            return

        # Зарезервировать минуты СЕЙЧАС (до обработки)
        user_service.add_usage(user, duration_minutes)
        user_id = user.id
    finally:
        db.close()

    # Отправить в очередь ВМЕСТО блокирующей транскрипции
    base_name = f"telegram_video_{video_file.file_id}"
    try:
        if status_msg:
            await status_msg.edit_text("✅ Файл принят! Транскрипция началась…\n⏱️ Это может занять некоторое время.")

        payload = MediaJobPayload(
            file_id=base_name,
            message_id=getattr(getattr(update, "effective_message", None), "message_id", None),
            extra={
                "audio_path": str(video_path),
                "filename": filename,
                "file_size_mb": file_size_mb,
                "duration_minutes": duration_minutes,
                "source_type": "video",
                "platform": getattr(update, "provider_platform", "telegram"),
                "chat_id": update.effective_chat.id if update.effective_chat else None,
            },
        )
        enqueue_media_job(user_id=user_id, payload=payload)
        logger.info(
            "Enqueued video for processing (non-blocking)",
            extra={
                "user_id": user_id,
                "file_id": base_name,
                "duration_minutes": duration_minutes,
            },
        )
        try:
            log_event(
                user,
                "video_queued_for_processing",
                {
                    "filename": filename,
                    "duration_minutes": duration_minutes,
                    "file_size_mb": file_size_mb,
                },
            )
        except Exception:
            logger.debug("Failed to log video queued event", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to enqueue video processing job",
            extra={"error": str(exc), "base_name": base_name},
        )
        if status_msg:
            await status_msg.edit_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")
        elif not SUPPRESS_FAILURE_MESSAGES and update.message:
            await update.message.reply_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")

    try:
        # Do not unlink video_path as it is sent to worker
        # We DO NOT unlink compressed_audio (or audio_path if it is the same)
        # as it will be used by the background worker. The worker will clean it up.
        if audio_path.exists() and str(audio_path) != str(compressed_audio):
            audio_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to cleanup video temp files", extra={"error": str(exc)})

async def process_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE, audio_file, *, status_message=None) -> None:
    chat_id = update.effective_chat.id if update.effective_chat else 0
    message_id = update.effective_message.message_id if update.effective_message else 0
    async with guard(chat_id, message_id) as proceed:
        if not proceed:
            return

    log_step(
        update,
        "process_audio_file:start",
        {
            "file_id": getattr(audio_file, "file_id", None),
            "file_size": getattr(audio_file, "file_size", None),
            "duration": getattr(audio_file, "duration", None),
            "filename": getattr(audio_file, "file_name", None),
        },
    )

    file_size_mb = audio_file.file_size / (1024 * 1024) if audio_file.file_size else 0
    filename = getattr(audio_file, "file_name", f"audio_{audio_file.file_id}")
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    status_msg = status_message
    _prepare_new_media(context)

    if not status_msg and not is_group and update.message:
        status_msg = await update.message.reply_text("Файл принят! Готовлю обработку…")

    audio_path = AUDIO_DIR / f"telegram_audio_{audio_file.file_id}.mp3"

    last_progress = [0.0]

    async def progress_callback(downloaded: int, total: int) -> None:
        if not status_msg or not total:
            return
        now = time.time()
        if now - last_progress[0] < 1.5:
            return
        last_progress[0] = now
        percent = int(downloaded / total * 100)
        filled = int(percent / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        try:
            await status_msg.edit_text(
                f"🎵 Загружаю аудио…\n📊 Размер: {file_size_mb:.1f} МБ\n{bar} {percent}%"
            )
        except Exception:
            pass

    success = await download_large_file(
        bot_token=BOT_TOKEN,
        file_id=audio_file.file_id,
        destination=audio_path,
        progress_callback=progress_callback,
        expected_size_bytes=getattr(audio_file, "file_size", None) or int(file_size_mb * 1024 * 1024),
        file_url=getattr(audio_file, "file_url", None),
    )

    if not success:
        if status_msg:
            await status_msg.edit_text("❌ Не удалось скачать аудио. Попробуйте позже.")
        elif not SUPPRESS_FAILURE_MESSAGES and update.message:
            await update.message.reply_text("❌ Не удалось скачать аудио. Попробуйте позже.")
        return

    if status_msg:
        try:
            await status_msg.edit_text("🗜️ Подготавливаю аудио…")
        except Exception:
            pass

    processed_audio = await compress_audio_for_api(audio_path)

    # Получить пользователя и проверить лимит ПЕРЕД добавлением в очередь
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        duration_minutes = get_media_duration(str(audio_path))
        can_use, limit_message = user_service.check_usage_limit(user)
        await _notify_free_quota_if_needed(update, context, user)
        if not can_use:
            if status_msg:
                await status_msg.edit_text(f"❌ {limit_message}")
            elif not SUPPRESS_FAILURE_MESSAGES and update.message:
                await update.message.reply_text(f"❌ {limit_message}")
            return

        # Зарезервировать минуты СЕЙЧАС (до обработки)
        user_service.add_usage(user, duration_minutes)
        user_id = user.id
    finally:
        db.close()

    # Отправить в очередь ВМЕСТО блокирующей транскрипции
    base_name = f"telegram_audio_{audio_file.file_id}"
    try:
        if status_msg:
            await status_msg.edit_text("✅ Файл принят! Транскрипция началась…\n⏱️ Это может занять некоторое время.")

        payload = MediaJobPayload(
            file_id=base_name,
            message_id=getattr(getattr(update, "effective_message", None), "message_id", None),
            extra={
                "audio_path": str(processed_audio),
                "filename": filename,
                "file_size_mb": file_size_mb,
                "duration_minutes": duration_minutes,
                "source_type": "audio",
                "platform": getattr(update, "provider_platform", "telegram"),
                "chat_id": update.effective_chat.id if update.effective_chat else None,
            },
        )
        enqueue_media_job(user_id=user_id, payload=payload)
        logger.info(
            "Enqueued audio for processing (non-blocking)",
            extra={
                "user_id": user_id,
                "file_id": base_name,
                "duration_minutes": duration_minutes,
            },
        )
        try:
            log_event(
                user,
                "audio_queued_for_processing",
                {
                    "filename": filename,
                    "duration_minutes": duration_minutes,
                    "file_size_mb": file_size_mb,
                },
            )
        except Exception:
            logger.debug("Failed to log audio queued event", exc_info=True)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to enqueue audio processing job",
            extra={"error": str(exc), "base_name": base_name},
        )
        if status_msg:
            await status_msg.edit_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")
        elif not SUPPRESS_FAILURE_MESSAGES and update.message:
            await update.message.reply_text("⚠️ Ошибка при постановке на обработку. Попробуйте позже.")

    try:
        # We DO NOT unlink processed_audio as it will be used by the background worker.
        if audio_path.exists() and str(audio_path) != str(processed_audio):
            audio_path.unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to cleanup audio temp files", extra={"error": str(exc)})

def _extract_youtube_links(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(1) for match in _YOUTUBE_URL_RE.finditer(text)]


def _extract_vk_video_links(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(1) for match in _VK_VIDEO_URL_RE.finditer(text)]


async def _handle_youtube_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    status_message=None,
) -> None:
    status_msg = status_message
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    platform_name = "VK видео" if _VK_VIDEO_URL_RE.match(url or "") else "YouTube"

    if not status_msg and not is_group and update.message:
        try:
            status_msg = await update.message.reply_text(
                f"🎬 Нашёл ссылку на {platform_name}, готовлю обработку…",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            status_msg = None

    artifacts: _YoutubeArtifacts | None = None
    try:
        artifacts = await _process_youtube_ingest(update, url, status_msg)
        file_size_mb = artifacts.video_path.stat().st_size / (1024 * 1024)
        await _process_external_audio(
            update,
            context,
            status_msg=status_msg,
            audio_path=artifacts.audio_path,
            filename=artifacts.video_path.name,
            file_size_mb=file_size_mb,
            source_url=url,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось обработать видео ссылку", extra={"error": str(exc), "url": url})
        error_text = "⚠️ Не удалось обработать ссылку на видео. Попробуйте позже."
        if status_msg:
            await _safe_edit_message(status_msg, error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        if artifacts:
            _cleanup_workspace(artifacts.workspace)


async def _handle_gdrive_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    status_message=None,
) -> None:
    from transkribator_modules.utils.gdrive_downloader import (
        download_from_gdrive,
        GDriveDownloadError,
        extract_gdrive_id,
    )

    user_id = update.effective_user.id if update.effective_user else "unknown"
    file_id = extract_gdrive_id(url)
    status_msg = status_message
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    if not status_msg and not is_group and update.message:
        try:
            status_msg = await update.message.reply_text(
                "📎 Нашёл ссылку на Google Drive, начинаю скачивание…\n"
                "⏳ Это может занять несколько минут для больших файлов (2-3 GB)",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            status_msg = None

    workspace: Path | None = None
    try:
        workspace = Path(tempfile.mkdtemp(prefix="gdrive_"))
        await _safe_edit_message(status_msg, "📥 Скачиваю файл с Google Drive…")
        downloaded_file = await asyncio.to_thread(
            download_from_gdrive,
            url,
            workspace / f"gdrive_{file_id}",
            quiet=False,
        )
        audio_path, supported = await _prepare_audio_file(downloaded_file, status_msg)
        if not supported:
            message = "❌ Файл имеет неподдерживаемый формат. Поддерживаются видео и аудио."
            if status_msg:
                await _safe_edit_message(status_msg, message)
            else:
                await update.message.reply_text(message)
            return
        file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)
        await _process_external_audio(
            update,
            context,
            status_msg=status_msg,
            audio_path=audio_path,
            filename=downloaded_file.name,
            file_size_mb=file_size_mb,
            source_url=url,
        )
    except GDriveDownloadError as exc:
        if status_msg:
            await _safe_edit_message(status_msg, str(exc))
        else:
            await update.message.reply_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error processing Google Drive link",
            extra={"error": str(exc), "url": url, "user_id": user_id, "file_id": file_id},
        )
        error_text = (
            "⚠️ Не удалось обработать файл с Google Drive. "
            "Попробуйте отправить файл напрямую или проверьте доступность ссылки."
        )
        if status_msg:
            await _safe_edit_message(status_msg, error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        if workspace and workspace.exists():
            _cleanup_workspace(workspace)


async def _handle_dropbox_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    status_message=None,
) -> None:
    from transkribator_modules.utils.dropbox_downloader import (
        download_from_dropbox,
        DropboxDownloadError,
        extract_dropbox_id,
    )

    user_id = update.effective_user.id if update.effective_user else "unknown"
    dropbox_id = extract_dropbox_id(url) or url
    status_msg = status_message
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    if not status_msg and not is_group and update.message:
        try:
            status_msg = await update.message.reply_text(
                "📎 Нашёл ссылку на Dropbox, начинаю скачивание…\n"
                "⏳ Это может занять несколько минут для больших файлов (2-3 GB)",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            status_msg = None

    workspace: Path | None = None
    try:
        workspace = Path(tempfile.mkdtemp(prefix="dropbox_"))
        await _safe_edit_message(status_msg, "📥 Скачиваю файл с Dropbox…")
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or "dropbox_file"
        downloaded_file = await asyncio.to_thread(
            download_from_dropbox,
            url,
            workspace / filename,
        )
        audio_path, supported = await _prepare_audio_file(downloaded_file, status_msg)
        if not supported:
            if status_msg:
                await _safe_edit_message(status_msg, "❌ Поддерживаются только видео и аудио файлы.")
            else:
                await update.message.reply_text("❌ Поддерживаются только видео и аудио файлы.")
            return
        file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)
        await _process_external_audio(
            update,
            context,
            status_msg=status_msg,
            audio_path=audio_path,
            filename=downloaded_file.name,
            file_size_mb=file_size_mb,
            source_url=url,
        )
    except DropboxDownloadError as exc:
        if status_msg:
            await _safe_edit_message(status_msg, str(exc))
        else:
            await update.message.reply_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error processing Dropbox link",
            extra={"error": str(exc), "url": url, "user_id": user_id},
        )
        error_text = "⚠️ Не удалось обработать файл с Dropbox. Попробуйте отправить его напрямую."
        if status_msg:
            await _safe_edit_message(status_msg, error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        if workspace and workspace.exists():
            _cleanup_workspace(workspace)


async def _handle_mega_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    status_message=None,
) -> None:
    from transkribator_modules.utils.mega_downloader import (
        download_from_mega,
        MegaDownloadError,
        extract_mega_id,
    )

    user_id = update.effective_user.id if update.effective_user else "unknown"
    mega_id = extract_mega_id(url) or url
    status_msg = status_message
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    if not status_msg and not is_group and update.message:
        try:
            status_msg = await update.message.reply_text(
                "📎 Нашёл ссылку на Mega.nz, начинаю скачивание…\n"
                "⏳ Это может занять несколько минут для больших файлов (до 20 GB)",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            status_msg = None

    workspace: Path | None = None
    try:
        workspace = Path(tempfile.mkdtemp(prefix="mega_"))
        await _safe_edit_message(status_msg, "📥 Скачиваю файл с Mega.nz…")
        downloaded_file = await asyncio.to_thread(
            download_from_mega,
            url,
            workspace / "mega_file",
        )
        audio_path, supported = await _prepare_audio_file(downloaded_file, status_msg)
        if not supported:
            msg = "❌ Файл имеет неподдерживаемый формат. Поддерживаются видео/аудио."
            if status_msg:
                await _safe_edit_message(status_msg, msg)
            else:
                await update.message.reply_text(msg)
            return
        file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)
        await _process_external_audio(
            update,
            context,
            status_msg=status_msg,
            audio_path=audio_path,
            filename=downloaded_file.name,
            file_size_mb=file_size_mb,
            source_url=url,
        )
    except MegaDownloadError as exc:
        if status_msg:
            await _safe_edit_message(status_msg, str(exc))
        else:
            await update.message.reply_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error processing Mega.nz link",
            extra={"error": str(exc), "url": url, "user_id": user_id},
        )
        error_text = "⚠️ Не удалось обработать файл с Mega.nz. Попробуйте отправить его напрямую."
        if status_msg:
            await _safe_edit_message(status_msg, error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        if workspace and workspace.exists():
            _cleanup_workspace(workspace)


async def _handle_yandex_disk_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    status_message=None,
) -> None:
    from transkribator_modules.utils.yandex_disk_downloader import (
        download_from_yandex_disk,
        YandexDiskDownloadError,
        extract_yandex_disk_id,
    )

    user_id = update.effective_user.id if update.effective_user else "unknown"
    yadisk_id = extract_yandex_disk_id(url) or url
    status_msg = status_message
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
    if not status_msg and not is_group and update.message:
        try:
            status_msg = await update.message.reply_text(
                "📎 Нашёл ссылку на Яндекс.Диск, начинаю скачивание…\n"
                "⏳ Это может занять несколько минут для больших файлов (до 50 GB)",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            status_msg = None

    workspace: Path | None = None
    try:
        workspace = Path(tempfile.mkdtemp(prefix="yadisk_"))
        await _safe_edit_message(status_msg, "📥 Скачиваю файл с Яндекс.Диска…")
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or "yadisk_file"
        downloaded_file = await asyncio.to_thread(
            download_from_yandex_disk,
            url,
            workspace / filename,
        )
        audio_path, supported = await _prepare_audio_file(downloaded_file, status_msg)
        if not supported:
            msg = "❌ Файл имеет неподдерживаемый формат. Поддерживаются видео/аудио."
            if status_msg:
                await _safe_edit_message(status_msg, msg)
            else:
                await update.message.reply_text(msg)
            return
        file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)
        await _process_external_audio(
            update,
            context,
            status_msg=status_msg,
            audio_path=audio_path,
            filename=downloaded_file.name,
            file_size_mb=file_size_mb,
            source_url=url,
        )
    except YandexDiskDownloadError as exc:
        if status_msg:
            await _safe_edit_message(status_msg, str(exc))
        else:
            await update.message.reply_text(str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Unexpected error processing Yandex.Disk link",
            extra={"error": str(exc), "url": url, "user_id": user_id},
        )
        error_text = "⚠️ Не удалось обработать файл с Яндекс.Диска. Попробуйте отправить его напрямую."
        if status_msg:
            await _safe_edit_message(status_msg, error_text)
        else:
            await update.message.reply_text(error_text)
    finally:
        if workspace and workspace.exists():
            _cleanup_workspace(workspace)

async def _process_youtube_ingest(
    update: Update,
    url: str,
    status_msg,
) -> _YoutubeArtifacts:
    workspace = Path(tempfile.mkdtemp(prefix="video_ingest_"))
    try:
        await _safe_edit_message(status_msg, "📥 Скачиваю видео…")
        download_path, info = await asyncio.to_thread(_download_youtube_media, url, workspace)

        await _safe_edit_message(status_msg, "🎛️ Конвертирую аудио…")
        wav_path = await asyncio.to_thread(_convert_to_wav, download_path)

        title = (info.get("title") or "").strip() or "Видео"
        video_id = info.get("id") or download_path.stem
        return _YoutubeArtifacts(
            video_path=download_path,
            audio_path=wav_path,
            transcript="",
            title=title,
            video_id=video_id,
            workspace=workspace,
            info=info or {},
        )
    except Exception:
        _cleanup_workspace(workspace)
        raise


def _download_youtube_media(url: str, workspace: Path) -> tuple[Path, dict]:
    try:
        import yt_dlp  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover - внешняя зависимость
        raise RuntimeError("Пакет yt-dlp не установлен для обработки ссылок YouTube/VK.") from exc

    workspace.mkdir(parents=True, exist_ok=True)
    output_template = workspace / "%(id)s.%(ext)s"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_template),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    proxy_url = os.getenv("YTDLP_PROXY", "").strip()
    if proxy_url:
        ydl_opts["proxy"] = proxy_url
        try:
            parsed_proxy = urlparse(proxy_url)
            logger.info(
                "🛡️ Использую прокси для YouTube загрузки",
                extra={
                    "proxy_scheme": parsed_proxy.scheme or "",
                    "proxy_host": parsed_proxy.hostname or "",
                    "proxy_port": parsed_proxy.port,
                },
            )
        except Exception:  # noqa: BLE001
            logger.info("🛡️ Использую прокси для YouTube загрузки", extra={"proxy": "custom"})
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    file_path = Path(filename)
    if not file_path.exists():
        # yt_dlp может складывать в workspace под другим расширением
        candidates = sorted(workspace.glob(f"{info.get('id', '')}.*"))
        if not candidates:
            raise FileNotFoundError("Не удалось скачать видео с YouTube/VK")
        file_path = candidates[0]
    return file_path, info


def _convert_to_wav(input_path: Path) -> Path:
    output_path = input_path.with_suffix(".wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return output_path


def _cleanup_workspace(path: Path) -> None:
    for item in sorted(path.glob("**/*"), reverse=True):
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                item.rmdir()
        except FileNotFoundError:
            continue
    try:
        path.rmdir()
    except Exception:  # noqa: BLE001
        logger.debug("Не удалось полностью очистить временную директорию YouTube", exc_info=True)


async def _safe_edit_message(message, text: str) -> None:
    if not message:
        return
    try:
        await message.edit_text(text, disable_web_page_preview=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось обновить статусное сообщение", extra={"error": str(exc)})

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        m = getattr(update, "message", None)
        kinds = []
        if m:
            if getattr(m, "voice", None):
                kinds.append("voice")
            if getattr(m, "audio", None):
                kinds.append("audio")
            if getattr(m, "video", None):
                kinds.append("video")
            if getattr(m, "video_note", None):
                kinds.append("video_note")
            if getattr(m, "document", None):
                kinds.append("document")
            if getattr(m, "text", None):
                kinds.append("text")
        logger.info(
            "handle_message: entered",
            extra={
                "chat_id": getattr(getattr(update, "effective_chat", None), "id", None),
                "msg_kinds": ",".join(kinds) if kinds else None,
            },
        )
    except Exception:
        pass
    """Интегрированный обработчик для всех типов сообщений с поддержкой Bot API Server."""
    # Some update types (e.g., channel posts/service updates) may not have a user.
    # Guard against None to avoid crashing the handler.
    if not update.effective_chat:
        logger.warning("Получен update без чата, пропускаем")
        return
    if not update.message:
        logger.warning("Получен update без сообщения, пропускаем")
        return
    if not update.effective_user:
        logger.warning(
            "Получен update без пользователя, пропускаем",
            extra={"chat_id": getattr(update.effective_chat, "id", None)},
        )
        return

    # Идемпотентность: один и тот же update обрабатываем ровно один раз
    if getattr(update, "update_id", None) is not None:
        if not should_process(update.update_id):
            return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Защита от повторной обработки одного и того же сообщения (на всякий случай)
    if getattr(update, "message", None) and getattr(update.message, "message_id", None) is not None:
        if not should_process_message(chat_id, update.message.message_id):
            return

    # Логируем сообщение
    logger.info(f"Получено сообщение от пользователя {user_id} в чате {chat_id}")

    # Определяем, работает ли бот в групповом чате
    is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")

    text_content = (update.message.text or update.message.caption or "").strip()
    if text_content and text_content.lower() == MAIN_MENU_BUTTON_TEXT.lower():
        await wai_menu_command(update, context)
        return

    # Команды обрабатываются телеграмом отдельно, поэтому не трогаем сообщения, начинающиеся с "@".
    if text_content.startswith("/"):
        return

    if text_content:
        if await manual_handle_message(update, context):
            return

    if text_content.lower().startswith("promo"):
        parts = text_content.split()
        if parts:
            # Поддерживаем как "promo CODE", так и "PROMO CODE" (без слеша).
            context.args = parts[1:]
            await promo_codes_command(update, context)
            return

    if update.message.text and context.chat_data.get("qa_session"):
        await _handle_question_message(update, context)
        return

    # Проверяем облачные хранилища ПЕРЕД бета-режимом (чтобы работало всегда)
    if text_content:
        # Проверяем Google Drive ссылки
        from transkribator_modules.utils.gdrive_downloader import extract_gdrive_links
        gdrive_links = extract_gdrive_links(text_content)
        if gdrive_links:
            logger.info("Обнаружена ссылка на Google Drive, запускаю обработку")
            # Логируем Google Drive ссылку
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_gdrive_link",
                    {
                        "url": gdrive_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log gdrive link event", exc_info=True)

            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                _handle_gdrive_link(update, context, gdrive_links[0], status_message=status_msg),
                description="gdrive_link_processing",
            )
            return
        
        # Проверяем Dropbox ссылки
        from transkribator_modules.utils.dropbox_downloader import extract_dropbox_links
        dropbox_links = extract_dropbox_links(text_content)
        if dropbox_links:
            logger.info("Обнаружена ссылка на Dropbox, запускаю обработку")
            # Логируем Dropbox ссылку
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_dropbox_link",
                    {
                        "url": dropbox_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log dropbox link event", exc_info=True)

            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                _handle_dropbox_link(update, context, dropbox_links[0], status_message=status_msg),
                description="dropbox_link_processing",
            )
            return
        
        # Проверяем Mega.nz ссылки
        from transkribator_modules.utils.mega_downloader import extract_mega_links
        mega_links = extract_mega_links(text_content)
        if mega_links:
            logger.info("Обнаружена ссылка на Mega.nz, запускаю обработку")
            # Логируем Mega.nz ссылку
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_mega_link",
                    {
                        "url": mega_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log mega link event", exc_info=True)

            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                _handle_mega_link(update, context, mega_links[0], status_message=status_msg),
                description="mega_link_processing",
            )
            return
        
        # Проверяем Яндекс.Диск ссылки
        from transkribator_modules.utils.yandex_disk_downloader import extract_yandex_disk_links
        yadisk_links = extract_yandex_disk_links(text_content)
        if yadisk_links:
            logger.info("Обнаружена ссылка на Яндекс.Диск, запускаю обработку")
            # Логируем Яндекс.Диск ссылку
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_yandex_disk_link",
                    {
                        "url": yadisk_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log yandex disk link event", exc_info=True)
            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                _handle_yandex_disk_link(update, context, yadisk_links[0], status_message=status_msg),
                description="yandex_disk_link_processing",
            )
            return

    if text_content:
        youtube_links = _extract_youtube_links(text_content)
        if youtube_links:
            logger.info("Обнаружена ссылка на YouTube, запускаю обработку")
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_youtube_link",
                    {
                        "url": youtube_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log youtube link event", exc_info=True)
            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            await _handle_youtube_link(update, context, youtube_links[0], status_message=status_msg)
            return
        vk_video_links = _extract_vk_video_links(text_content)
        if vk_video_links:
            logger.info("Обнаружена ссылка на VK видео, запускаю обработку")
            try:
                log_event(
                    update.effective_user.id,
                    "bot_media_vk_link",
                    {
                        "url": vk_video_links[0],
                        "chat_id": chat_id,
                    }
                )
            except Exception:
                logger.debug("Failed to log vk link event", exc_info=True)
            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            await _handle_youtube_link(update, context, vk_video_links[0], status_message=status_msg)
            return

    # Обработка видео
    if update.message.video:
        logger.info(f"Получено видео от пользователя {user_id}")
        try:
            log_telegram_event(
                update.effective_user,
                "message_video",
                {
                    "chat_id": chat_id,
                    "file_id": update.message.video.file_id,
                    "file_size": update.message.video.file_size,
                    "caption": update.message.caption,
                },
            )
        except Exception:
            logger.debug("Failed to log video message", exc_info=True)
        _prepare_new_media(context)
        status_msg = await wai_progress_placeholder(update, context)
        _schedule_background_task(
            context,
            process_video_file(update, context, update.message.video, status_message=status_msg),
            description="message_video_processing",
        )
        return

    # Обработка аудио
    if update.message.audio:
        logger.info(f"Получено аудио от пользователя {user_id}")
        try:
            log_telegram_event(
                update.effective_user,
                "message_audio",
                {
                    "chat_id": chat_id,
                    "file_id": update.message.audio.file_id,
                    "file_size": update.message.audio.file_size,
                    "duration": update.message.audio.duration,
                    "caption": update.message.caption,
                },
            )
        except Exception:
            logger.debug("Failed to log audio message", exc_info=True)
        _prepare_new_media(context)
        status_msg = await wai_progress_placeholder(update, context)
        _schedule_background_task(
            context,
            process_audio_file(update, context, update.message.audio, status_message=status_msg),
            description="message_audio_processing",
        )
        return

    # Обработка голосовых сообщений
    if update.message.voice:
        logger.info(f"Получено голосовое сообщение от пользователя {user_id}")
        try:
            log_telegram_event(
                update.effective_user,
                "message_voice",
                {
                    "chat_id": chat_id,
                    "file_id": update.message.voice.file_id,
                    "file_size": update.message.voice.file_size,
                    "duration": update.message.voice.duration,
                },
            )
        except Exception:
            logger.debug("Failed to log voice message", exc_info=True)
        _prepare_new_media(context)
        status_msg = await wai_progress_placeholder(update, context)
        _schedule_background_task(
            context,
            process_audio_file(update, context, update.message.voice, status_message=status_msg),
            description="voice_processing",
        )
        return

    # Обработка документов (видео/аудио файлы)
    if update.message.document:
        document = update.message.document
        filename = document.file_name.lower() if document.file_name else ""

        # Проверяем, является ли документ видео или аудио
        if any(ext in filename for ext in VIDEO_FORMATS):
            logger.info(
                f"Получен видео-документ от пользователя {user_id}: {filename}",
                extra={
                    "file_size_mb": document.file_size / (1024 * 1024) if document.file_size else 0,
                    "mime_type": document.mime_type,
                },
            )
            try:
                log_telegram_event(
                    update.effective_user,
                    "message_document_video",
                    {
                        "chat_id": chat_id,
                        "file_id": document.file_id,
                        "file_size": document.file_size,
                        "file_name": document.file_name,
                        "mime_type": document.mime_type,
                    },
                )
            except Exception:
                logger.debug("Failed to log document video", exc_info=True)
            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                process_video_file(update, context, document, status_message=status_msg),
                description="message_document_video_processing",
            )
            return
        elif any(ext in filename for ext in AUDIO_FORMATS):
            logger.info(f"Получен аудио-документ от пользователя {user_id}: {filename}")
            try:
                log_telegram_event(
                    update.effective_user,
                    "message_document_audio",
                    {
                        "chat_id": chat_id,
                        "file_id": document.file_id,
                        "file_size": document.file_size,
                        "file_name": document.file_name,
                    },
                )
            except Exception:
                logger.debug("Failed to log document audio", exc_info=True)
            _prepare_new_media(context)
            status_msg = await wai_progress_placeholder(update, context)
            _schedule_background_task(
                context,
                process_audio_file(update, context, document, status_message=status_msg),
                description="message_document_audio_processing",
            )
            return

    # Если это обычное текстовое сообщение
    if update.message.text:
        # Проверяем, что это не группа или что бот упомянут в сообщении
        is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
        bot_mentioned = False

        if is_group:
            # В группах проверяем, упомянут ли бот
            bot_username = context.bot.username
            if bot_username and f"@{bot_username}" in update.message.text:
                bot_mentioned = True

        # Отвечаем только в личных чатах или если бот упомянут в группе
        if not is_group or bot_mentioned:
            # Проверяем, ожидаем ли мы задачу для обработки транскрипции
            if context.user_data.get('waiting_for_task', False):
                await handle_transcript_processing_task(update, context)
            else:
                await update.message.reply_text(
                    "Привет! 🐱 Отправь мне видео или аудио файл, и я создам для тебя транскрипцию!\n\n"
                    "Поддерживаемые форматы:\n"
                    "📹 Видео: MP4, AVI, MOV, MKV и другие\n"
                    "🎵 Аудио: MP3, WAV, M4A, OGG и другие\n"
                    "🎤 Голосовые сообщения\n\n"
                    "Максимальный размер файла: 2 ГБ\n"
                    "Максимальная длительность: 4 часа\n\n"
                    "Используй /help для получения дополнительной информации!"
                )
            try:
                log_telegram_event(
                    update.effective_user,
                    "message_text",
                    {
                        "chat_id": chat_id,
                        "text": update.message.text,
                    },
                )
            except Exception:
                logger.debug("Failed to log text message", exc_info=True)

async def handle_transcript_processing_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения с задачами для обработки транскрипции."""
    try:
        user_id = update.effective_user.id
        task_description = update.message.text

        # Сбрасываем флаг ожидания задачи
        context.user_data['waiting_for_task'] = False

        # Отправляем сообщение о начале обработки
        processing_msg = await update.message.reply_text(
            "🤖 Обрабатываю транскрипцию согласно твоей задаче...\n\n"
            "*сосредоточенно работает*\n"
            "Это может занять некоторое время...",
            parse_mode='Markdown'
        )

        # Получаем последнюю транскрипцию пользователя из базы данных
        from transkribator_modules.db.database import SessionLocal, UserService, TranscriptionService

        db = SessionLocal()
        try:
            user_service = UserService(db)
            transcription_service = TranscriptionService(db)

            # Получаем пользователя
            user = user_service.get_or_create_user(telegram_id=user_id)

            # Получаем последнюю транскрипцию пользователя
            transcriptions = transcription_service.get_user_transcriptions(user, limit=1)

            if not transcriptions:
                await processing_msg.edit_text(
                    "❌ Не найдено транскрипций для обработки.\n\n"
                    "Сначала отправьте файл для транскрипции!"
                )
                return

            latest_transcription = transcriptions[0]
            transcript_text = latest_transcription.formatted_transcript or latest_transcription.raw_transcript

            if not transcript_text:
                await processing_msg.edit_text("❌ Транскрипция пуста")
                return

            # Обрабатываем транскрипцию согласно задаче
            processed_text = await process_transcript_with_task(transcript_text, task_description)

            if not processed_text:
                await processing_msg.edit_text(
                    "❌ Не удалось обработать транскрипцию.\n\n"
                    "Возможно, сервис временно недоступен. Попробуйте позже."
                )
                return

            # Отправляем результат
            result_text = f"✅ **Результат обработки:**\n\n{processed_text}\n\n@CyberKitty19_bot"

            # Если результат длинный, отправляем файлом
            if len(result_text) > 4000:
                # Убеждаемся, что директория существует
                TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
                txt_path = TRANSCRIPTIONS_DIR / f"processed_transcript_{user_id}.txt"
                sections = [
                    "Обработанная транскрипция",
                    f"Задача: {task_description}",
                    "",
                    processed_text,
                ]
                txt_content = "\n".join(sections)
                txt_path.write_text(txt_content, encoding="utf-8")

                with open(txt_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename="processed_transcript.txt",
                        caption="✅ Результат обработки готов!\n\n@CyberKitty19_bot"
                    )

                # Удаляем временный файл
                txt_path.unlink(missing_ok=True)
            else:
                # Отправляем без parse_mode чтобы избежать ошибок с markdown entities
                await update.message.reply_text(result_text)

            # Обновляем сообщение о завершении
            await processing_msg.edit_text("✅ Обработка завершена!")

            # Показываем главное меню (личный кабинет)
            from transkribator_modules.bot.commands import personal_cabinet_command
            await personal_cabinet_command(update, context)

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при обработке задачи транскрипции: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке транскрипции.\n\n"
            "Попробуйте позже или обратитесь в поддержку."
        )

async def process_transcript_with_task(transcript_text: str, task_description: str) -> str:
    """Обрабатывает транскрипцию согласно задаче пользователя."""
    try:
        from transkribator_modules.transcribe.transcriber_v4 import request_llm_response

        system_prompt = (
            "Ты эксперт по обработке транскрипций. Твоя задача — читать запрос пользователя "
            "и выдавать готовый результат по предоставленной расшифровке.")
        user_prompt = (
            "ЗАДАЧА: {task}\n\n"
            "ТРАНСКРИПЦИЯ:\n{transcript}\n\n"
            "Обработай транскрипцию согласно задаче. Если указан конкретный формат, следуй ему точно."
        ).format(task=task_description, transcript=transcript_text)

        processed_text = None
        if request_llm_response:
            processed_text = await request_llm_response(system_prompt, user_prompt)

        if processed_text:
            cleaned_text = processed_text.strip().replace("*", "").replace("_", "").replace("`", "")
            if cleaned_text:
                return cleaned_text

        logger.warning("LLM не вернул результат для пользовательской задачи, отдаю исходную транскрипцию")
        return (
            "Не удалось обработать транскрипцию через ИИ. Вот исходная транскрипция:\n\n"
            f"{transcript_text}"
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке транскрипции с задачей: {e}")
        return f"Произошла ошибка при обработке: {str(e)}"
