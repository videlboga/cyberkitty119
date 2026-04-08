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
import html
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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
from telegram.ext import ContextTypes, ConversationHandler

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
from transkribator_modules.bot.payments import show_payment_plans
from transkribator_modules.bot.callbacks import (
    show_personal_cabinet,
    CABINET_SUPPRESS_INLINE_FLAG,
    CABINET_REPLY_MARKUP_KEY,
)
from transkribator_modules.config import TELEGRAM_REFERRAL_URL
from transkribator_modules.db.database import ReferralService, SessionLocal, UserService

try:
    from transkribator_modules.search.service import NoteSearchError, run_note_search
except ImportError:
    pass

from transkribator_modules.utils.large_file_downloader import download_large_file

# ── Текстовые шаблоны ────────────────────────────────────────────────────────

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
_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\r\n]+')
RESULT_CAPTION_MARKDOWN = "[CyberKitty119 Транскрибатор](https://t.me/CyberKitty19_bot)"
NOTE_QA_SESSIONS_KEY = "note_qa_sessions"
NOTE_QA_ACTIVE_KEY = "note_qa_active"
NOTE_SEARCH_BUTTON = "🔎 Поиск по заметкам"
MAX_QA_HISTORY_MESSAGES = 30
MAX_TRANSCRIPT_CHARS = 12000
MAIN_MENU_BUTTON = "🐱 Главное меню"
_ACTIVE_QA_SESSIONS: dict[int, dict[str, int]] = {}
_ACTIVE_SEARCH_USERS: set[int] = set()
MENU_RESPONSES = {
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
        [KeyboardButton("💎 Подписка"), KeyboardButton("🐱 Личный кабинет")],
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
    if value is None:
        return "—"

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return "—"
        normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            dt = None
        if dt:
            return dt.strftime("%Y-%m-%d %H:%M")

    try:
        seconds = max(0, int(float(value)))
    except Exception:
        return str(value)

    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _build_timecode_text(segments: Optional[list[dict[str, Any]]]) -> str:
    lines: list[str] = []
    for segment in segments or []:
        text = (segment.get("text") or "").strip()
        if not text:
            continue
        start = _format_timestamp(segment.get("start"))
        end_val = segment.get("end")
        if end_val is None:
            end_val = segment.get("duration")
            if end_val is not None and segment.get("start") is not None:
                try:
                    end_val = float(segment["start"]) + float(end_val)
                except Exception:
                    end_val = None
        end = _format_timestamp(end_val if end_val is not None else segment.get("start"))
        lines.append(f"[{start} - {end}] {text}")
    return "\n".join(lines)


def _build_note_file_content(
    note: dict,
    raw_transcript: Optional[str],
    filename: str,
    segments: Optional[list[dict[str, Any]]] = None,
) -> str:
    title = note.get("title") or Path(filename).stem
    tags = note.get("tags") or []
    tag_line = ", ".join(f"#{tag}" for tag in tags) if tags else "—"
    links = note.get("links") or {}
    if links:
        link_lines = "\n".join(f"- {key}: {value}" for key, value in links.items())
    else:
        link_lines = "—"

    summary = (note.get("summary") or "").strip() or "—"
    raw_body = (raw_transcript or "").strip() or "—"
    timecoded_body = _build_timecode_text(segments or []) or "—"

    sections = [
        "=== Файл ===",
        f"Оригинальный файл: {filename}",
        "",
        "=== Метаданные ===",
        f"Note ID: {note.get('id', '—')}",
        f"Название: {title}",
        "",
        f"Создана: {_format_timestamp(note.get('created_at'))}",
        f"Обновлена: {_format_timestamp(note.get('updated_at'))}",
        f"Теги: {tag_line}",
        "Ссылки:",
        link_lines,
        "",
        "=== Summary ===",
        summary,
        "",
        "=== Транскрипция ===",
        raw_body,
        "",
        "=== Транскрипция с таймкодами ===",
        timecoded_body,
    ]
    return "\n".join(sections)


def _extract_note_title(note: dict) -> str:
    for key in ("title", "summary", "text"):
        value = (note.get(key) or "").strip()
        if value:
            return value
    fallback = note.get("id")
    return f"note_{fallback}" if fallback is not None else "note"


def _build_note_filename(note: dict) -> str:
    raw = _extract_note_title(note)
    normalized = _FILENAME_FORBIDDEN_RE.sub(" ", raw).strip()
    normalized = re.sub(r"\s+", "_", normalized, flags=re.UNICODE).strip("_")
    if not normalized:
        normalized = f"note_{note.get('id', 'result')}"
    if len(normalized) > 80:
        normalized = normalized[:80].rstrip("_-.") or normalized[:80]
    return normalized


def _build_note_delivery_caption(note: dict, filename: str) -> str:
    return RESULT_CAPTION_MARKDOWN


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


def _build_referral_link(referral_code: str) -> str:
    """Собрать корректный диплинк, учитывая кастомный TELEGRAM_REFERRAL_URL."""
    parsed = urlparse(TELEGRAM_REFERRAL_URL)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("utm_source", "telegram")
    params.setdefault("utm_medium", "bot")
    params.setdefault("utm_campaign", "referral")
    params["start"] = f"ref_{referral_code}"

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower().endswith("t.me")
        and path_segments
    ):
        bot_segment = path_segments[0]
        base_path = f"/{bot_segment}"
        params.pop("startapp", None)
        return urlunparse(parsed._replace(path=base_path, query=urlencode(params)))

    return urlunparse(parsed._replace(query=urlencode(params)))


async def _send_referral_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target_message = update.message
    if not target_message:
        return

    user = update.effective_user
    if not user:
        await target_message.reply_text(
            "⚠️ Не удалось определить пользователя для реферальной программы.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    db = SessionLocal()
    try:
        user_service = UserService(db)
        referral_service = ReferralService(db)
        db_user = user_service.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        referral_code = referral_service.create_or_get_referral_code(db_user)
        referral_link = _build_referral_link(referral_code)
        stats = referral_service.get_referral_stats_for_user(db_user)
    except Exception as exc:  # noqa: BLE001
        logger.error("Не удалось загрузить реферальную программу", exc_info=True, extra={"error": str(exc)})
        await target_message.reply_text(
            "❌ Не удалось загрузить реферальную программу. Попробуй позже.",
            reply_markup=_main_menu_keyboard(),
        )
        return
    finally:
        db.close()

    safe_code = html.escape(referral_code, quote=False)
    safe_link = html.escape(referral_link, quote=True)
    visits = stats.get("visits", 0)
    paid_count = stats.get("paid_count", 0)
    total_amount = stats.get("total_amount", 0.0) or 0.0
    balance = stats.get("balance", 0.0) or 0.0

    message = (
        "<b>🤝 Реферальная программа</b>\n\n"
        f"Твой код: <code>{safe_code}</code>\n"
        f"Ссылка: {safe_link}\n\n"
        "Статистика:\n"
        f"• Визитов: {visits}\n"
        f"• Оплачено: {paid_count}\n"
        f"• Сумма оплат: {total_amount:.0f} ₽\n"
        f"• Баланс: {balance:.0f} ₽"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 Открыть ссылку", url=referral_link)],
        ]
    )
    await target_message.reply_text(message, reply_markup=keyboard, parse_mode="HTML")


# ── Handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"🤖 Обработка /start от пользователя {update.message.from_user.id}")
    context.chat_data[CABINET_SUPPRESS_INLINE_FLAG] = True
    context.chat_data[CABINET_REPLY_MARKUP_KEY] = _main_menu_keyboard()
    await show_personal_cabinet(update, context)
    logger.info(f"✅ Отправлен личный кабинет пользователю {update.message.from_user.id}")
    return MENU_STATE


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

    # ── 3. Создать задачу на воркер через Core API ─────────────────────────────
    try:
        import httpx
        import os
        api_url = "http://core-api:8000"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{api_url}/api/v1/ingest/media",
                json={
                    "telegram_id": telegram_id,
                    "file_id": str(file_id),
                    "audio_path": str(dest_path),
                    "message_id": getattr(msg, "message_id", None)
                }
            )
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                raise Exception(data.get("error", "Unknown API error"))
            job_id = data["job_id"]
        logger.info("Job создан через API: id=%s", job_id)
    except Exception as exc:
        logger.exception("Не удалось создать job через API для %s", file_id)
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
            job_id=job_id,
            filename=filename,
            dest_path=dest_path,
            context=context,
        ),
        name=f"poll_job_{job_id}",
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
    segments_blob = result_blob.get("segments")
    segments: list[dict[str, Any]] = segments_blob if isinstance(segments_blob, list) else []
    note_owner_id = (job_row or {}).get("user_id")

    if note:
        file_content = _build_note_file_content(note, raw_transcript, filename, segments)
        temp_path = None
        try:
            normalized_title = _build_note_filename(note)
            rendered_content = file_content
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".txt",
                prefix=f"{normalized_title}_",
                delete=False,
            ) as tmp:
                tmp.write(rendered_content)
                temp_path = Path(tmp.name)

            with open(temp_path, "rb") as tmp_file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=tmp_file,
                    filename=f"{normalized_title}.txt",
                    caption=_build_note_delivery_caption(note, normalized_title),
                    parse_mode="Markdown",
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
    return NOTE_QA_STATE


async def handle_note_qa_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return NOTE_QA_STATE
    telegram_id = update.message.from_user.id if update.message.from_user else None
    state = _get_active_note_session(telegram_id)
    logger.debug(
        "QA message received telegram_id=%s state_exists=%s", telegram_id, bool(state)
    )
    if not state:
        return MENU_STATE
    active_note_id = state.get("note_id")
    session_id = state.get("session_id")
    if not active_note_id or not session_id:
        return MENU_STATE

    text = update.message.text.strip()
    if text == MAIN_MENU_BUTTON:
        _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        context.chat_data[CABINET_SUPPRESS_INLINE_FLAG] = True
        context.chat_data[CABINET_REPLY_MARKUP_KEY] = _main_menu_keyboard()
        await show_personal_cabinet(update, context)
        return MENU_STATE

    session_payload = fetch_note_qa_session_payload(session_id, history_limit=MAX_QA_HISTORY_MESSAGES)
    if not session_payload:
        await update.message.reply_text("⚠️ Контекст заметки недоступен. Попробуй отправить файл заново.", reply_markup=ReplyKeyboardRemove())
        _set_active_note_session(telegram_id=telegram_id, note_id=None, session_id=None)
        return MENU_STATE

    record_note_qa_message(session_id, "user", text)
    session_payload["messages"].append({"role": "user", "content": text})
    if len(session_payload["messages"]) > MAX_QA_HISTORY_MESSAGES:
        session_payload["messages"] = session_payload["messages"][-MAX_QA_HISTORY_MESSAGES :]

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await _run_note_agent(session_payload)
    except AgentLLMError as exc:
        await update.message.reply_text(f"⚠️ LLM сейчас недоступна: {exc}", reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True))
        return NOTE_QA_STATE

    record_note_qa_message(session_id, "assistant", answer)
    session_payload["messages"].append({"role": "assistant", "content": answer})
    if len(session_payload["messages"]) > MAX_QA_HISTORY_MESSAGES:
        session_payload["messages"] = session_payload["messages"][-MAX_QA_HISTORY_MESSAGES :]

    await update.message.reply_text(answer, reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True))
    return NOTE_QA_STATE


async def handle_note_search_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return NOTE_SEARCH_STATE
    telegram_id = update.message.from_user.id if update.message.from_user else None
    logger.debug("Search message from %s active=%s", telegram_id, _is_search_active(telegram_id))
    if not _is_search_active(telegram_id):
        return MENU_STATE

    text = update.message.text.strip()
    if text == MAIN_MENU_BUTTON:
        _set_search_active(telegram_id, False)
        context.chat_data[CABINET_SUPPRESS_INLINE_FLAG] = True
        context.chat_data[CABINET_REPLY_MARKUP_KEY] = _main_menu_keyboard()
        await show_personal_cabinet(update, context)
        return MENU_STATE

    if not telegram_id:
        await update.message.reply_text("⚠️ Не удалось определить пользователя для поиска.")
        return NOTE_SEARCH_STATE

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
        return NOTE_SEARCH_STATE

    await update.message.reply_text(
        result["response"],
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True),
    )
    return NOTE_SEARCH_STATE


async def handle_note_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    return NOTE_SEARCH_STATE


async def handle_menu_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder responses for menu buttons."""
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    logger.debug("Menu action received text=%r", text)
    if text == "💎 Подписка":
        await show_payment_plans(update, context)
        return MENU_STATE
    if text == "🐱 Личный кабинет":
        context.chat_data[CABINET_SUPPRESS_INLINE_FLAG] = True
        context.chat_data[CABINET_REPLY_MARKUP_KEY] = _main_menu_keyboard()
        await show_personal_cabinet(update, context)
        return MENU_STATE
    if text == "🎁 Реферальная программа":
        await _send_referral_info(update, context)
        return MENU_STATE
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

        if active_qa or active_search:
            await update.message.reply_text("🐱 Вернулся в главное меню.")
        context.chat_data[CABINET_SUPPRESS_INLINE_FLAG] = True
        context.chat_data[CABINET_REPLY_MARKUP_KEY] = _main_menu_keyboard()
        await show_personal_cabinet(update, context)
        return MENU_STATE

    response = MENU_RESPONSES.get(text)
    if response:
        await update.message.reply_text(
            response,
            reply_markup=_main_menu_keyboard(),
        )
    return MENU_STATE


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
MENU_STATE, NOTE_QA_STATE, NOTE_SEARCH_STATE = range(3)
