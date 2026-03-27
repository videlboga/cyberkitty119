"""
Обработчики Telegram-бота.

handle_start        — /start, /help
handle_media_file   — любой медиафайл:
    1. Отправить «принял файл» сообщение
    2. Скачать файл через Bot API → media/incoming/
    3. Создать ProcessingJob в БД
    4. Запустить background-task: polling прогресса + отправка результата
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from telegram import Message, Update
from telegram.ext import ContextTypes

from bot.config import (
    BOT_TOKEN,
    MEDIA_INCOMING_DIR,
    PROGRESS_POLL_INTERVAL,
    PROGRESS_TIMEOUT,
    logger,
)
from bot.db import get_job_row, get_user_id_by_telegram_id, ensure_user
from bot.jobs import create_media_job
from transkribator_modules.utils.large_file_downloader import download_large_file

# ── Текстовые шаблоны ────────────────────────────────────────────────────────

START_TEXT = (
    "👋 *Привет!* Я транскрибирую аудио и видео в текст.\n\n"
    "Просто отправь мне:\n"
    "• 🎙 Голосовое сообщение\n"
    "• 🎵 Аудиофайл (mp3, m4a, ogg, wav…)\n"
    "• 🎬 Видеофайл (mp4, mkv, webm…)\n"
    "• 📎 Любой документ с аудио/видео\n\n"
    "Я скачаю его, обработаю и верну текстовый файл."
)

PROGRESS_LABELS = {
    "queued": "⏳ В очереди",
    "in_progress": "⚙️ Обрабатывается",
    "completed": "✅ Готово",
    "failed": "❌ Ошибка",
}

STAGE_EMOJIS = {
    "prepare_environment": "🛠",
    "download_media": "⬇️",
    "transcribe_media": "🎙",
    "transcribe_media_gpu": "⚡",
    "finalize_note": "📝",
    "deliver_results": "📤",
    "cleanup": "🧹",
}


# ── Утилиты ──────────────────────────────────────────────────────────────────

def _file_from_update(update: Update):
    """Вернуть объект файла из апдейта, независимо от типа."""
    msg = update.message
    if msg.voice:
        return msg.voice
    if msg.audio:
        return msg.audio
    if msg.video:
        return msg.video
    if msg.document:
        return msg.document
    if hasattr(msg, "video_note") and msg.video_note:
        return msg.video_note
_LOCAL_DATA_SUBDIR: Optional[Path] = None


def _original_filename(update: Update, file_obj) -> str:
    """Попытаться определить исходное имя файла."""
    msg = update.message
    if msg.document and getattr(msg.document, "file_name", None):
        return msg.document.file_name
    ext_map = {
        "voice": "ogg",
        "audio": getattr(file_obj, "mime_type", "audio/mpeg").split("/")[-1].split(";")[0],
        "video": "mp4",
        "video_note": "mp4",
        "document": "bin",
    }
    kind = "voice" if msg.voice else (
        "audio" if msg.audio else (
            "video" if msg.video else (
                "video_note" if (hasattr(msg, "video_note") and msg.video_note) else "document"
            )
        )
    )
    ext = ext_map.get(kind, "bin")
    return f"media_{file_obj.file_id[:12]}.{ext}"


def _progress_bar(progress: Optional[int], width: int = 12) -> str:
    if progress is None:
        return "▒" * width
    filled = int(width * progress / 100)
    return "█" * filled + "▒" * (width - filled)


def _build_progress_text(
    status: str,
    progress: Optional[int],
    stage_hint: Optional[str],
    filename: str,
    elapsed: float,
) -> str:
    status_label = PROGRESS_LABELS.get(status, status)
    bar = _progress_bar(progress)
    pct = f"{progress}%" if progress is not None else "—"
    stage_emoji = STAGE_EMOJIS.get(stage_hint or "", "•") if stage_hint else "•"
    elapsed_str = f"{int(elapsed)}с"

    lines = [
        f"📂 *{filename}*",
        "",
        f"{status_label}",
        f"`[{bar}]` {pct}",
        "",
        f"{stage_emoji} {stage_hint or ''}  ·  ⏱ {elapsed_str}",
    ]
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"🤖 Обработка /start от пользователя {update.message.from_user.id}")
    await update.message.reply_text(START_TEXT, parse_mode="Markdown")
    logger.info(f"✅ Отправлено приветствие пользователю {update.message.from_user.id}")


async def handle_media_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Основной обработчик медиафайлов."""
    msg: Message = update.message
    telegram_id = msg.from_user.id
    logger.info(f"📎 Обработка медиафайла от {telegram_id}")

    file_obj = _file_from_update(update)
    if not file_obj:
        logger.warning(f"Не определен тип файла от {telegram_id}")
        await msg.reply_text("⚠️ Не могу определить тип файла. Попробуй ещё раз.")
        return

    filename = _original_filename(update, file_obj)
    file_id = file_obj.file_id
    logger.info(f"📎 Файл: {filename} (ID: {file_id})")

    # ── 1. Принять и сообщить ────────────────────────────────────────────────
    status_msg = await msg.reply_text(
        f"📥 *Получил файл:* `{filename}`\n⬇️ Скачиваю…",
        parse_mode="Markdown",
    )

    # ── 2. Скачать через Bot API ──────────────────────────────────────────────
    dest_path = MEDIA_INCOMING_DIR / f"{file_id}_{filename}"
    try:
        success = await download_large_file(
            bot_token=BOT_TOKEN,
            file_id=file_id,
            destination=dest_path,
            expected_size_bytes=getattr(file_obj, "file_size", None),
        )
    except Exception as exc:
        logger.exception("Ошибка скачивания файла %s", file_id)
        await status_msg.edit_text(f"❌ Не удалось скачать файл: {exc}")
        return

    if not success or not dest_path.exists():
        await status_msg.edit_text("❌ Не удалось скачать файл: Bot API вернул пустой ответ")
        return

    await status_msg.edit_text(
        f"📂 *{filename}*\n✅ Скачан. Ставлю в очередь…",
        parse_mode="Markdown",
    )

    # ── 3. Создать задачу на воркер ───────────────────────────────────────────
    try:
        user_id = await ensure_user(telegram_id)
        job = create_media_job(
            user_id=user_id,
            telegram_id=telegram_id,
            file_id=file_id,
            audio_path=str(dest_path),
            message_id=msg.message_id,
        )
        logger.info("Job создан: id=%s user_id=%s", job.id, user_id)
    except Exception as exc:
        logger.exception("Не удалось создать job для %s", file_id)
        await status_msg.edit_text("❌ Не удалось поставить задачу в очередь. Попробуй позже.")
        return

    await status_msg.edit_text(
        _build_progress_text("queued", 0, None, filename, 0),
        parse_mode="Markdown",
    )

    # ── 4. Background: polling прогресса ──────────────────────────────────────
    asyncio.create_task(
        _poll_and_deliver(
            chat_id=msg.chat_id,
            status_msg=status_msg,
            job_id=job.id,
            filename=filename,
            dest_path=dest_path,
            context=context,
        ),
        name=f"poll_job_{job.id}",
    )


async def _poll_and_deliver(
    *,
    chat_id: int,
    status_msg: Message,
    job_id: int,
    filename: str,
    dest_path: Path,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Polling БД и обновление статусного сообщения. По завершении — отправить файл."""
    started = time.monotonic()
    last_text: Optional[str] = None
    last_stage: Optional[str] = None

    while True:
        elapsed = time.monotonic() - started

        if elapsed > PROGRESS_TIMEOUT:
            await _safe_edit(status_msg, "⏰ Превышено время ожидания. Задача могла зависнуть.")
            return

        row = get_job_row(job_id)
        if row is None:
            await asyncio.sleep(PROGRESS_POLL_INTERVAL)
            continue

        status = row["status"]
        progress = row.get("progress")
        error = row.get("error")

        # Попытаться вытащить текущий stage из error/artifacts (воркер пишет stage name в notifier)
        stage_hint = last_stage  # сохраняем между итерациями

        new_text = _build_progress_text(status, progress, stage_hint, filename, elapsed)
        if new_text != last_text:
            await _safe_edit(status_msg, new_text, parse_mode="Markdown")
            last_text = new_text

        if status == "completed":
            await _deliver_result(
                chat_id=chat_id,
                status_msg=status_msg,
                job_id=job_id,
                filename=filename,
                context=context,
            )
            return

        if status == "failed":
            err_short = (error or "неизвестная ошибка")[:300]
            await _safe_edit(
                status_msg,
                f"❌ *Ошибка при обработке:*\n`{err_short}`",
                parse_mode="Markdown",
            )
            return

        await asyncio.sleep(PROGRESS_POLL_INTERVAL)


async def _deliver_result(
    *,
    chat_id: int,
    status_msg: Message,
    job_id: int,
    filename: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Получить транскрипцию из БД/артефактов и отправить пользователю файлом."""
    from bot.db import get_transcript_for_job

    transcript = get_transcript_for_job(job_id)

    if not transcript:
        await _safe_edit(
            status_msg,
            "✅ Готово! Но текст не найден в базе. Возможно, файл был пустым.",
        )
        return

    # Сохранить во временный .txt и отправить как документ
    import tempfile
    stem = Path(filename).stem
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".txt",
        prefix=f"{stem}_",
        delete=False,
    ) as f:
        f.write(transcript)
        txt_path = Path(f.name)

    try:
        with open(txt_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=f"{stem}_transcript.txt",
                caption=f"✅ *Транскрипция готова!*\nФайл: `{filename}`",
                parse_mode="Markdown",
            )
        await _safe_edit(status_msg, f"✅ *Транскрипция отправлена!*", parse_mode="Markdown")
    except Exception as exc:
        logger.exception("Ошибка при отправке файла результата job=%s", job_id)
        await _safe_edit(status_msg, f"❌ Не удалось отправить файл: {exc}")
    finally:
        txt_path.unlink(missing_ok=True)


async def _safe_edit(msg: Message, text: str, **kwargs) -> None:
    """Редактировать сообщение, игнорируя ошибку 'message is not modified'."""
    try:
        await msg.edit_text(text, **kwargs)
    except Exception as exc:
        err = str(exc).lower()
        if "message is not modified" not in err:
            logger.debug("edit_text failed: %s", exc)
