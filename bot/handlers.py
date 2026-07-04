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
    LabeledPrice,
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
from bot.core_api_client import (
    CoreAPIError,
    activate_promo_code,
    enqueue_media_job,
    fetch_profile,
    fetch_referral_info,
    search_memory as core_search_memory,
    get_payment_plans,
    create_payment_invoice,
    confirm_payment_success,
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
from core_api.domains.agent.core.llm import (
    AgentLLMError,
    call_agent_llm_with_retry,
)
from transkribator_modules.config import TELEGRAM_REFERRAL_URL

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
CABINET_SUPPRESS_INLINE_FLAG = "cabinet_suppress_inline"
CABINET_REPLY_MARKUP_KEY = "cabinet_reply_markup"
MENU_RESPONSES = {
    "⚙️ Настройки": "Настройки в разработке. Если нужно что-то сменить (например формат выхлопа) — напиши и помогу вручную.",
    "❓ Помощь": "Просто отправь файл — и я расскажу, что происходит. Если что-то пойдет не так, можно написать сюда же и я помогу разобраться.",
}


async def _search_memory_via_core(telegram_id: int, query: str) -> str:
    return await core_search_memory(telegram_id, query)


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


async def show_payment_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.effective_message
    if not target:
        return
        
    try:
        data = await get_payment_plans()
        descriptions = data.get("descriptions", {})
        stars_prices = data.get("stars", {})
        
        text = "💳 <b>Тарифы CyberKitty</b>\n\n"
        keyboard = []
        for plan_id, plan_info in descriptions.items():
            text += f"⭐️ <b>{plan_info.get('title', plan_id.title())}</b>\n"
            text += f"<i>{plan_info.get('description', '')}</i>\n"
            for feature in plan_info.get("features", []):
                text += f"• {feature}\n"
            text += "\n"
            
            stars_price = stars_prices.get(plan_id)
            if stars_price and stars_price > 0:
                keyboard.append([
                    InlineKeyboardButton(f"Купить {plan_info.get('title')} за {stars_price} ⭐️", callback_data=f"buy_plan_{plan_id}_stars")
                ])
                
        text += "🤖 Оплата в Telegram Stars доступна прямо здесь."
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else _main_menu_keyboard()
    except Exception as e:
        logger.error(f"Failed to fetch plans: {e}")
        text = "💳 <b>Тарифы CyberKitty</b>\n\nНе удалось загрузить списки тарифов. Пожалуйста, попробуйте позже."
        reply_markup = _main_menu_keyboard()

    if update.callback_query:
        await update.callback_query.answer()
        await target.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await target.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

def _format_usage_line(used: float, limit: float | None) -> str:
    if not limit or limit <= 0:
        return f"{used:.1f} мин · без лимита"
    return f"{used:.1f} / {limit:.1f} мин"


def _format_profile_message(data: dict) -> str:
    plan_name = data.get("plan_display_name") or data.get("current_plan", "Free")
    plan_status = data.get("plan_status_text") or ""
    minutes_used = float(data.get("minutes_used_this_month", 0.0) or 0.0)
    minutes_limit_raw = data.get("minutes_limit")
    try:
        minutes_limit = float(minutes_limit_raw)
        if minutes_limit <= 0:
            minutes_limit = None
    except (TypeError, ValueError):
        minutes_limit = None
    generations_used = int(data.get("generations_used_this_month", 0) or 0)
    generations_limit_raw = data.get("generations_limit")
    try:
        generations_limit = int(generations_limit_raw)
        if generations_limit <= 0:
            generations_limit = None
    except (TypeError, ValueError):
        generations_limit = None
    total_minutes = float(data.get("total_minutes_transcribed", 0.0) or 0.0)
    transcriptions_count = int(data.get("transcriptions_count", 0) or 0)
    usage_line = _format_usage_line(minutes_used, minutes_limit)
    if generations_limit:
        gen_line = f"{generations_used} / {generations_limit} генераций"
    else:
        gen_line = f"{generations_used} генераций · без лимита"

    lines = [
        "🐱 <b>Личный кабинет</b>",
        f"Тариф: <b>{plan_name}</b> {plan_status}",
        "",
        "⏱ <b>Минут в этом месяце</b>",
        usage_line,
        "",
        "📊 <b>Общая статистика</b>",
        f"• Всего файлов: {transcriptions_count}",
        f"• Всего минут: {total_minutes:.1f}",
    ]
    return "\n".join(lines)


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

    try:
        data = await fetch_referral_info(
            telegram_id=user.id,
            username=user.username or "",
            first_name=user.first_name or "",
            last_name=user.last_name or "",
        )
        referral_code = data.get("referral_code", "")
        referral_link = _build_referral_link(referral_code)
        visits = data.get("visits", 0)
        paid_count = data.get("paid_count", 0)
        total_amount = float(data.get("total_amount", 0.0) or 0.0)
        balance = float(data.get("balance", 0.0) or 0.0)
    except CoreAPIError as exc:
        await target_message.reply_text(
            f"❌ Не удалось загрузить реферальную программу: {exc}",
            reply_markup=_main_menu_keyboard(),
        )
        return

    safe_code = html.escape(referral_code, quote=False)
    safe_link = html.escape(referral_link, quote=True)

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


async def show_personal_cabinet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user:
        return
    try:
        profile = await fetch_profile(
            telegram_id=user.id,
            first_name=user.first_name or "",
            last_name=user.last_name or "",
        )
    except CoreAPIError as exc:
        await message.reply_text(f"❌ Не удалось загрузить профиль: {exc}")
        return
    await message.reply_text(
        _format_profile_message(profile),
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_personal_cabinet(update, context)


async def personal_cabinet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_personal_cabinet(update, context)


async def promo_codes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    user = update.effective_user
    if not user:
        await message.reply_text("⚠️ Не удалось определить пользователя.")
        return
    args = context.args if context.args else []
    if not args:
        await message.reply_text("Использование: /promo <код>", reply_markup=_main_menu_keyboard())
        return
    code = args[0].strip()
    if not code:
        await message.reply_text("Укажи код после команды: /promo CODE", reply_markup=_main_menu_keyboard())
        return
    try:
        result = await activate_promo_code(user.id, code)
    except CoreAPIError as exc:
        await message.reply_text(f"❌ Не удалось активировать промокод: {exc}", reply_markup=_main_menu_keyboard())
        return
    if result.get("success"):
        bonus = result.get("bonus")
        expires = result.get("expires")
        text = "✅ Промокод активирован!"
        if bonus:
            text += f"\nБонус: {bonus}"
        if expires:
            text += f"\nДействует до: {expires}"
    else:
        text = f"⚠️ {result.get('error', 'Не удалось активировать промокод.')}"
    await message.reply_text(text, reply_markup=_main_menu_keyboard())


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
        
    data = query.data
    telegram_id = query.from_user.id
    
    if data == "show_payment_plans":
        await show_payment_plans(update, context)
        return
        
    if data.startswith("buy_plan_"):
        await query.answer()
        try:
            parts = data.replace("buy_plan_", "").split("_")
            plan_id = parts[0]
            currency = parts[1] if len(parts) > 1 else "stars"
            
            invoice_data = await create_payment_invoice(telegram_id, plan_id, currency)
            title = invoice_data.get("title", f"Тариф {plan_id.title()}")
            payload = invoice_data.get("invoice_payload", f"plan_{plan_id}")
            
            plans_data = await get_payment_plans()
            stars_price = plans_data.get("stars", {}).get(plan_id, 0)
            
            if currency == "stars" and stars_price > 0:
                await context.bot.send_invoice(
                    chat_id=telegram_id,
                    title=title,
                    description=f"Оплата тарифа {title}",
                    payload=payload,
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice("Оплата подписки", stars_price)],
                )
            else:
                await query.message.reply_text("❌ Оплата в данной валюте пока не поддерживается.")
        except Exception as e:
            logger.error(f"Error initiating payment: {e}")
            await query.message.reply_text("⚠️ Ошибка при создании счета на оплату.")
        return
        
    await query.answer("Действие недоступно", show_alert=False)


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
    if not msg or not msg.from_user:
        logger.debug("handle_media_file: update.message or from_user is None, skipping (likely channel post)")
        return
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
        job_id = await enqueue_media_job(
            telegram_id=telegram_id,
            file_id=str(file_id),
            audio_path=str(dest_path),
            message_id=getattr(msg, "message_id", None),
        )
        logger.info("Job создан через Core API: id=%s", job_id)
    except CoreAPIError as exc:
        logger.exception("Не удалось создать job через API для %s", file_id)
        await status_msg.edit_text(f"❌ Не удалось поставить задачу: {exc}")
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
    
    # NEW CALL TO BACKEND
    from bot.core_api_client import set_active_note
    try:
        await set_active_note(telegram_id, note_id, local_artifact=True)
    except Exception as e:
        logger.error(f"Failed to set active note: {e}")
        await query.edit_message_text("⚠️ Ошибка: не удалось включить чат с заметкой.")
        return

    _set_active_note_session(telegram_id=telegram_id, note_id=note_id, session_id="dummy")

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


    from bot.core_api_client import chat_with_agent
    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        answer = await chat_with_agent(
            telegram_id=telegram_id, 
            text=text, 
            name=update.message.from_user.first_name, 
            username=update.message.from_user.username
        )
    except Exception as exc:
        logger.error(f"Error querying agent: {exc}")
        await update.message.reply_text(f"⚠️ Ошибка: {exc}", reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True))
        return NOTE_QA_STATE

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

    await update.message.chat.send_action(ChatAction.TYPING)
    try:
        response_text = await _search_memory_via_core(telegram_id, text)
    except CoreAPIError as exc:
        await update.message.reply_text(
            f"⚠️ Не удалось выполнить поиск: {exc}",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True),
        )
        return NOTE_SEARCH_STATE
    except Exception:
        logger.exception("Unexpected memory search failure for %s", telegram_id)
        await update.message.reply_text(
            "⚠️ Что-то пошло не так при поиске. Попробуйте чуть позже.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton(MAIN_MENU_BUTTON)]], resize_keyboard=True),
        )
        return NOTE_SEARCH_STATE

    await update.message.reply_text(
        response_text,
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

async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payment = update.message.successful_payment
    telegram_id = update.message.from_user.id
    payload = payment.invoice_payload
    plan_id = payload.replace("plan_", "")
    
    try:
        await confirm_payment_success(
            telegram_id=telegram_id,
            plan_id=plan_id,
            amount=payment.total_amount,
            currency=payment.currency,
            payment_id=payment.telegram_payment_charge_id
        )
        await update.message.reply_text(f"🎉 Спасибо за оплату! Ваш тариф активирован.")
    except Exception as e:
        logger.error(f"Payment success sync failed: {e}")
        await update.message.reply_text("Платеж прошёл успешно, но у нас возникла небольшая техническая заминка. Поддержка уже уведомлена!")

MENU_STATE, NOTE_QA_STATE, NOTE_SEARCH_STATE = range(3)
