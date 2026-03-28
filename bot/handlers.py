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
import tempfile
import time
from pathlib import Path
from typing import Optional

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from bot.config import (
    BOT_TOKEN,
    MEDIA_INCOMING_DIR,
    PROGRESS_POLL_INTERVAL,
    PROGRESS_TIMEOUT,
    logger,
)
from bot.db import (
    ensure_user,
    ensure_note_qa_session,
    fetch_note_qa_session_payload,
    get_job_row,
    get_note_for_job,
    get_note_qa_session_for_user,
    get_transcript_for_job,
    get_user_id_by_telegram_id,
    record_note_qa_message,
)
from bot.jobs import create_media_job
from transkribator_modules.beta.llm import (
    AgentLLMError,
    call_agent_llm_with_retry,
)
from transkribator_modules.search.service import NoteSearchError, run_note_search
from transkribator_modules.utils.large_file_downloader import download_large_file

# ── Текстовые шаблоны ────────────────────────────────────────────────────────

START_TEXT = (
    "👋 *Привет!* Я помогаю расшифровывать аудио и видео в текст, хранить заметки и искать по ним.\n\n"
    "Просто отправь мне файл или ссылку – я остальное сделаю сам."
)

PROGRESS_LABELS = {
    "queued": "⏳ Файл принят, начинаю обработку",
    "in_progress": "⚙️ Обрабатывается",
    "completed": "✅ Готово",
    "failed": "❌ Ошибка",
}

NOTE_STATUS_LABELS = {
    "ingested": "Черновик",
    "draft": "Черновик",
    "processed_raw": "Обработано (сырой текст)",
    "processed": "Готово",
    "approved": "Подтверждено",
    "backlog": "В планах",
    "new": "Новая",
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

_GLITCH_SYMBOLS = ["", "░", "▓"]
NOTE_QA_SESSIONS_KEY = "note_qa_sessions"
NOTE_QA_ACTIVE_KEY = "note_qa_active"
NOTE_SEARCH_BUTTON = "🔎 Поиск по заметкам"
MAX_QA_HISTORY_MESSAGES = 30
MAX_TRANSCRIPT_CHARS = 12000
MAIN_MENU_BUTTON = "🐱 Главное меню"
_ACTIVE_QA_SESSIONS: dict[int, dict[str, int]] = {}
_ACTIVE_SEARCH_USERS: set[int] = set()
_ACTIVE_SEARCH_USERS: set[int] = set()
MENU_RESPONSES = {
    "💎 Подписка": "Скоро здесь появятся тарифы и возможности на подписке. Пока просто отправь файл или ссылку — обработаю как обычно.",
    "🎁 Реферальная программа": "Готовим новую реферальную программу. А пока можно делиться ботом: чем больше файлов — тем лучше тестируем.",
    "⚙️ Настройки": "Настройки в разработке. Если нужно что-то сменить (например формат выхлопа) — напиши и помогу вручную.",
    "❓ Помощь": "Просто отправь файл — и я расскажу, что происходит. Если что-то пойдет не так, можно написать сюда же и я помогу разобраться.",
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


def _main_menu_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("💎 Подписка"), KeyboardButton("🎁 Реферальная программа")],
        [KeyboardButton("🔎 Поиск по заметкам")],
        [KeyboardButton("⚙️ Настройки"), KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


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


def _progress_from_stage_window(
    stage_window: Optional[tuple[int, int]],
    stage_progress: Optional[int],
) -> Optional[int]:
    """Approximate overall progress using the current stage window."""
    if not stage_window or stage_progress is None:
        return None
    start, end = stage_window
    span = max(end - start, 1)
    normalized_stage = max(0, min(100, int(stage_progress)))
    estimated = start + int(span * normalized_stage / 100)
    # Clamp to window bounds to avoid drifting on rounding.
    return max(start, min(end, estimated))


def _stage_progress_from_overall(
    stage_window: Optional[tuple[int, int]],
    progress: Optional[int],
) -> Optional[int]:
    """Translate overall progress into the stage-specific scale."""
    if not stage_window or progress is None:
        return None
    start, end = stage_window
    span = max(end - start, 1)
    if progress <= start:
        return 0
    if progress >= end:
        return 100
    return int((progress - start) / span * 100)


def _glitch_text(text: Optional[str], elapsed: float) -> Optional[str]:
    if not text:
        return text
    idx = int(elapsed // 3) % 3
    if idx == 0:
        return text
    center = max(1, min(len(text) - 1, len(text) // 2))
    if idx == 1:
        return text[:center] + _GLITCH_SYMBOLS[1] + text[center:]
    start = max(center - 1, 0)
    end = min(start + 3, len(text))
    glitch_block = _GLITCH_SYMBOLS[2] * max(1, end - start)
    return text[:start] + glitch_block + text[end:]


def _format_timestamp(value) -> str:
    if not value:
        return "-"
    try:
        return value.strftime("%d.%m.%Y %H:%M")
    except Exception:  # pragma: no cover - formatting fallback
        return str(value)


def _build_note_file_content(
    note: dict,
    raw_transcript: Optional[str],
    filename: str,
) -> str:
    title = note.get("title") or Path(filename).stem
    status = NOTE_STATUS_LABELS.get((note.get("status") or "").lower(), note.get("status", ""))
    tags = note.get("tags") or []
    tag_line = ", ".join(f"#{tag}" for tag in tags) if tags else "—"
    links = note.get("links") or {}
    if links:
        link_lines = "\n".join(f"- {key}: {value}" for key, value in links.items())
    else:
        link_lines = "—"

    summary = (note.get("summary") or "").strip() or "—"
    text_body = (note.get("text") or "").strip() or "—"
    raw_body = (raw_transcript or "").strip() or "—"

    sections = [
        "=== Файл ===",
        f"Оригинальный файл: {filename}",
        "",
        "=== Метаданные ===",
        f"Note ID: {note.get('id', '—')}",
        f"Название: {title}",
        f"Статус: {status or '—'}",
        f"Создана: {_format_timestamp(note.get('created_at'))}",
        f"Обновлена: {_format_timestamp(note.get('updated_at'))}",
        f"Теги: {tag_line}",
        "Ссылки:",
        link_lines,
        "",
        "=== Summary ===",
        summary,
        "",
        "=== Итоговая заметка ===",
        text_body,
        "",
        "=== Сырая транскрипция ===",
        raw_body,
    ]
    return "\n".join(sections)


def _build_progress_text(
    status: str,
    progress: Optional[int],
    stage_name: Optional[str],
    stage_label: Optional[str],
    stage_progress: Optional[int],
    filename: str,
    elapsed: float,
) -> str:
    status_label = PROGRESS_LABELS.get(status, status)
    elapsed_str = f"{int(elapsed)}с"

    def _bar_or_spinner(value: Optional[int]) -> str:
        return f"`[{_progress_bar(value)}]` {value}%" if value is not None else "🌀"

    lines = [f"📂 *{filename}*", ""]

    stage_title = stage_label or stage_name
    if stage_title:
        lines.append(f"🐱 {_glitch_text(stage_title, elapsed)}")
        lines.append(_bar_or_spinner(stage_progress))
        lines.append("")

    lines.append(f"🐱 {_glitch_text(status_label, elapsed)}")
    overall_line = _bar_or_spinner(progress)
    if progress is not None:
        overall_line += f" · ⏱ {elapsed_str}"
    lines.append(overall_line)

    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"🤖 Обработка /start от пользователя {update.message.from_user.id}")
    await update.message.reply_text(
        START_TEXT,
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )
    logger.info(f"✅ Отправлено главное меню пользователю {update.message.from_user.id}")


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
        _build_progress_text("queued", 0, None, None, None, filename, 0),
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
    last_stage_label: Optional[str] = None

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
        raw_progress = row.get("progress")
        progress: Optional[int]
        if raw_progress is None:
            progress = None
        else:
            try:
                progress = max(0, min(100, int(raw_progress)))
            except (TypeError, ValueError):
                progress = None
        error = row.get("error")

        stage_name = row.get("stage") or last_stage
        stage_label = row.get("stage_label") or last_stage_label
        stage_progress = row.get("stage_progress")
        stage_window = row.get("stage_window")
        if stage_progress is not None:
            try:
                stage_progress = max(0, min(100, int(stage_progress)))
            except (TypeError, ValueError):
                stage_progress = None
        if row.get("stage"):
            last_stage = row["stage"]
        if row.get("stage_label"):
            last_stage_label = row["stage_label"]
        derived_progress = _progress_from_stage_window(stage_window, stage_progress)
        if progress is None and derived_progress is not None:
            progress = derived_progress

        derived_stage_progress = _stage_progress_from_overall(stage_window, progress)
        if derived_stage_progress is not None:
            if stage_progress is None:
                stage_progress = derived_stage_progress
            else:
                stage_progress = max(int(stage_progress), derived_stage_progress)

        new_text = _build_progress_text(
            status,
            progress,
            stage_name,
            stage_label,
            stage_progress,
            filename,
            elapsed,
        )
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
    """Отправить файл с заметкой или fallback с текстовым файлом."""
    note = get_note_for_job(job_id)
    job_row = get_job_row(job_id)
    payload = (job_row or {}).get("payload") or {}
    result_blob = payload.get("_result") or {}
    raw_transcript = result_blob.get("raw_transcript")
    inline_transcript = result_blob.get("final_transcript")
    note_owner_id = (job_row or {}).get("user_id")

    if note:
        file_content = _build_note_file_content(note, raw_transcript, filename)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                prefix=f"{Path(filename).stem}_note_",
                delete=False,
            ) as tmp:
                tmp.write(file_content)
                temp_path = Path(tmp.name)

            with open(temp_path, "rb") as tmp_file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=tmp_file,
                    filename=f"{Path(filename).stem}_note.txt",
                    caption=f"📓 Заметка #{note.get('id', '')} готова",
                )
            await _safe_edit(status_msg, "✅ Файл с заметкой отправлен!", parse_mode="Markdown")

            session_owner = note_owner_id or note.get("user_id")
            session_id = None
            if session_owner:
                session_id = _prepare_note_session(
                    context,
                    note,
                    raw_transcript or inline_transcript or note.get("text"),
                    user_id=session_owner,
                )
            await context.bot.send_message(
                chat_id=chat_id,
                text="Хочешь обсудить заметку? Нажми кнопку ниже и задай вопрос.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "💬 Задать вопросы",
                                callback_data=f"noteqa:{note.get('id')}",
                            )
                        ]
                    ]
                ),
            )
            return
        except Exception as exc:
            logger.exception("Ошибка при отправке файла заметки job=%s", job_id)
            await _safe_edit(
                status_msg,
                "⚠️ Не удалось отправить файл заметки. Пробую отправить текст.",
                parse_mode="Markdown",
            )
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    transcript = inline_transcript or get_transcript_for_job(job_id)
    if not transcript:
        await _safe_edit(
            status_msg,
            "✅ Готово! Но заметку найти не удалось, и текст недоступен.",
        )
        return

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
        await _safe_edit(status_msg, "✅ Транскрипция отправлена!", parse_mode="Markdown")
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


def _prepare_note_session(
    context: ContextTypes.DEFAULT_TYPE,
    note: dict,
    transcript: Optional[str],
    *,
    user_id: int,
) -> int:
    """Создать/обновить QA-сессию в БД и закешировать session_id."""
    sessions = context.user_data.setdefault(NOTE_QA_SESSIONS_KEY, {})
    snapshot_raw = (transcript or note.get("text") or "").strip()
    snapshot = snapshot_raw[:MAX_TRANSCRIPT_CHARS]
    session_id = ensure_note_qa_session(
        user_id=user_id,
        note=note,
        context_snapshot=snapshot,
    )
    sessions[note["id"]] = session_id
    return session_id


def _get_note_session_id(
    context: ContextTypes.DEFAULT_TYPE,
    note_id: int,
    *,
    user_id: int,
) -> Optional[int]:
    sessions = context.user_data.get(NOTE_QA_SESSIONS_KEY, {})
    session_id = sessions.get(note_id)
    if session_id:
        return session_id
    session_id = get_note_qa_session_for_user(user_id, note_id)
    if session_id:
        sessions[note_id] = session_id
    return session_id


def _set_active_note_session(
    *,
    telegram_id: Optional[int],
    note_id: Optional[int],
    session_id: Optional[int],
) -> None:
    if not telegram_id:
        return
    if note_id is None or session_id is None:
        _ACTIVE_QA_SESSIONS.pop(telegram_id, None)
        logger.debug("QA session cleared for telegram_id=%s", telegram_id)
    else:
        _ACTIVE_QA_SESSIONS[telegram_id] = {
            "note_id": note_id,
            "session_id": session_id,
        }
        _set_search_active(telegram_id, False)
        logger.debug(
            "QA session activated telegram_id=%s note_id=%s session_id=%s",
            telegram_id,
            note_id,
            session_id,
        )


def _get_active_note_session(telegram_id: Optional[int]) -> Optional[dict]:
    if not telegram_id:
        return None
    return _ACTIVE_QA_SESSIONS.get(telegram_id)


def _set_search_active(telegram_id: Optional[int], active: bool) -> None:
    if not telegram_id:
        return
    if active:
        _ACTIVE_SEARCH_USERS.add(telegram_id)
        logger.debug("Search session activated telegram_id=%s", telegram_id)
    else:
        _ACTIVE_SEARCH_USERS.discard(telegram_id)
        logger.debug("Search session cleared telegram_id=%s", telegram_id)


def _is_search_active(telegram_id: Optional[int]) -> bool:
    if not telegram_id:
        return False
    return telegram_id in _ACTIVE_SEARCH_USERS


async def handle_note_qa_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()
    try:
        _, note_id_raw = query.data.split(":", 1)
        note_id = int(note_id_raw)
    except Exception:
        await query.edit_message_text("⚠️ Не удалось открыть чат для этой заметки.")
        return

    telegram_id = query.from_user.id if query and query.from_user else None
    user_id = None
    if telegram_id:
        user_id = get_user_id_by_telegram_id(telegram_id)
        if user_id is None:
            user_id = await ensure_user(telegram_id)

    if not user_id:
        await query.edit_message_text("⚠️ Не удалось определить пользователя для этой заметки.")
        return

    session_id = _get_note_session_id(context, note_id, user_id=user_id)
    if not session_id:
        await query.edit_message_text("⚠️ Не нашёл контекст заметки. Отправь файл заново.")
        return

    _set_active_note_session(telegram_id=telegram_id, note_id=note_id, session_id=session_id)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="💬 Спросите что угодно по заметке. Я в контексте всей транскрипции.",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(MAIN_MENU_BUTTON)]],
            resize_keyboard=True,
            one_time_keyboard=False,
        ),
    )


async def handle_note_qa_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    telegram_id = update.message.from_user.id if update.message.from_user else None
    state = _get_active_note_session(telegram_id)
    logger.debug(
        "QA message received telegram_id=%s state_exists=%s", telegram_id, bool(state)
    )
    if not state:
        return
    active_note_id = state.get("note_id")
    session_id = state.get("session_id")
    if not active_note_id or not session_id:
        return

    text = update.message.text.strip()
    if text == MAIN_MENU_BUTTON:
        _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        await update.message.reply_text("🐱 Вернулся в главное меню.", reply_markup=_main_menu_keyboard())
        return

    session_payload = fetch_note_qa_session_payload(session_id, history_limit=MAX_QA_HISTORY_MESSAGES)
    if not session_payload:
        await update.message.reply_text("⚠️ Контекст заметки недоступен. Попробуй отправить файл заново.", reply_markup=ReplyKeyboardRemove())
        _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        return

    record_note_qa_message(session_id, "user", text)
    session_payload["messages"].append({"role": "user", "content": text})
    if len(session_payload["messages"]) > MAX_QA_HISTORY_MESSAGES:
        session_payload["messages"] = session_payload["messages"][-MAX_QA_HISTORY_MESSAGES :]

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await _run_note_agent(session_payload)
    except AgentLLMError as exc:
        await update.message.reply_text(f"⚠️ LLM сейчас недоступна: {exc}", reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True))
        return

    record_note_qa_message(session_id, "assistant", answer)
    session_payload["messages"].append({"role": "assistant", "content": answer})
    if len(session_payload["messages"]) > MAX_QA_HISTORY_MESSAGES:
        session_payload["messages"] = session_payload["messages"][-MAX_QA_HISTORY_MESSAGES :]

    await update.message.reply_text(answer, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True))


async def handle_note_search_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    telegram_id = update.message.from_user.id if update.message.from_user else None
    logger.debug("Search message from %s active=%s", telegram_id, _is_search_active(telegram_id))
    if not _is_search_active(telegram_id):
        return

    text = update.message.text.strip()
    if text == MAIN_MENU_BUTTON:
        _set_search_active(telegram_id, False)
        await update.message.reply_text(
            "🐱 Завершил поиск. Возвращаю меню.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    if not telegram_id:
        await update.message.reply_text("⚠️ Не удалось определить пользователя для поиска.")
        return

    user_id = get_user_id_by_telegram_id(telegram_id)
    if not user_id:
        user_id = await ensure_user(telegram_id)

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        result = await run_note_search(user_id=user_id, query=text)
    except NoteSearchError as exc:
        await update.message.reply_text(
            f"⚠️ Не удалось выполнить поиск: {exc}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True),
        )
        return

    await update.message.reply_text(
        result["response"],
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True),
    )


async def handle_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder responses for menu buttons."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if text == NOTE_SEARCH_BUTTON:
        telegram_id = update.message.from_user.id if update.message.from_user else None
        logger.info("🔎 Search mode requested by %s", telegram_id)
        _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        _set_search_active(telegram_id, True)
        await update.message.reply_text(
            "🔎 Напиши, что найти в заметках. Я поищу по содержимому и тегам.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(MAIN_MENU_BUTTON)]],
                resize_keyboard=True,
                one_time_keyboard=False,
            ),
        )
        return

    if text not in MENU_RESPONSES and text != MAIN_MENU_BUTTON:
        return

    if text == MAIN_MENU_BUTTON:
        telegram_id = update.message.from_user.id if update.message.from_user else None
        active_qa = _get_active_note_session(telegram_id) is not None
        active_search = _is_search_active(telegram_id)
        if active_qa:
            _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        if active_search:
            _set_search_active(telegram_id, False)

        await update.message.reply_text(
            START_TEXT if not (active_qa or active_search) else "🐱 Вернулся в главное меню.",
            parse_mode="Markdown",
            reply_markup=_main_menu_keyboard(),
        )
        return

    response = MENU_RESPONSES.get(text)
    if response:
        await update.message.reply_text(
            response,
            reply_markup=_main_menu_keyboard(),
        )


async def _run_note_agent(session_payload: dict) -> str:
    transcript = (session_payload.get("context_snapshot") or "").strip()
    if not transcript:
        transcript = (session_payload.get("text") or "").strip()

    truncated_transcript = transcript[:MAX_TRANSCRIPT_CHARS]
    intro = (
        "Ты внимательный ассистент и отвечаешь на вопросы по встрече.\n"
        "Всегда опирайся только на текст транскрипции ниже. "
        "Если ответ отсутствует, честно скажи об этом. Отвечай лаконично на русском.\n"
        f"Название заметки: {session_payload.get('title') or 'без названия'}\n"
        "Транскрипция:\n"
        f"{truncated_transcript}"
    )

    history = session_payload.get("messages", []) or []
    if len(history) > MAX_QA_HISTORY_MESSAGES:
        history = history[-MAX_QA_HISTORY_MESSAGES:]

    messages = [{"role": "system", "content": intro}]
    messages.extend({"role": msg["role"], "content": msg["content"]} for msg in history if msg.get("content"))

    if len(messages) == 1:
        raise AgentLLMError("Нет вопросов для обработки.")

    answer = await call_agent_llm_with_retry(messages, timeout=40.0)
    return answer
