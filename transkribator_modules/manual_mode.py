"""Лёгкий ручной режим без агентного планировщика.

Позволяет включать состояния по кнопкам/меню:
- загрузка медиа (подсказка, без перехвата пайплайна);
- поиск по заметкам;
- выбор активной заметки;
- чат по выбранной заметке (LLM получает контекст заметки + локальную историю диалога).

Основная идея — минимальные побочные эффекты и управление состоянием через context.user_data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import dateparser
except ImportError:  # pragma: no cover - optional dependency for richer parsing
    dateparser = None

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from core_api.domains.agent.core.llm import call_agent_llm_with_retry, AgentLLMError
from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note
from transkribator_modules.search import IndexService

MANUAL_STATE_KEY = "manual_mode"
MAX_HISTORY_LEN = 10
MAX_CONTEXT_LEN = 4000
VECTOR_CHAT_MODE = "vector_chat"
VECTOR_CONTEXT_COUNT = int(os.getenv("VECTOR_CONTEXT_COUNT", "5"))

_DATE_RANGE_REGEX = re.compile(r"с\s+([^,;.]+?)\s+(?:по|до)\s+([^,;.]+)", re.IGNORECASE)
_DATEPARSER_SETTINGS = {"PREFER_DATES_FROM": "past"}
_SIMPLE_DATE_FORMATS = ["%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"]
_RELATIVE_KEYWORDS = ("последн", "прошл", "за последний", "за последние", "вчера", "сегодня")
_RELATIVE_UNIT_VARIANTS: List[Tuple[List[str], timedelta]] = [
    (["час", "часа", "часов"], timedelta(hours=1)),
    (["день", "дня", "дней", "сутки", "суток"], timedelta(days=1)),
    (["неделя", "недели", "недель", "неделю"], timedelta(weeks=1)),
    (["месяц", "месяца", "месяцев", "месяцу", "месяцем"], timedelta(days=30)),
    (["год", "года", "лет", "году", "годом"], timedelta(days=365)),
]


def _drop_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _format_iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


def _parse_date_with_stdlib(raw: str) -> Optional[datetime]:
    cleaned = raw.strip()
    if not cleaned:
        return None
    for fmt in _SIMPLE_DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _parse_date_token(raw: str, base: datetime) -> Optional[datetime]:
    if dateparser:
        parsed = dateparser.parse(raw, settings={**_DATEPARSER_SETTINGS, "RELATIVE_BASE": base})
    else:
        parsed = _parse_date_with_stdlib(raw)
    if not parsed:
        return None
    return _drop_timezone(parsed)


def _extract_explicit_date_range(text: str, base: datetime) -> Tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    match = _DATE_RANGE_REGEX.search(text)
    if not match:
        return None, None, None

    start_token = match.group(1).strip()
    end_token = match.group(2).strip()
    start_dt = _parse_date_token(start_token, base)
    end_dt = _parse_date_token(end_token, base)
    if not start_dt or not end_dt:
        return None, None, None

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    return start_dt, end_dt, f"explicit:{start_token}:{end_token}"


def _extract_relative_date_range(text: str, base: datetime) -> Tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    lower = text.lower()
    if not any(keyword in lower for keyword in _RELATIVE_KEYWORDS):
        return None, None, None

    if "вчера" in lower:
        start = base - timedelta(days=1)
        return start, base, "relative:yesterday"
    if "сегодня" in lower and "вчера" not in lower:
        return base.replace(hour=0, minute=0, second=0, microsecond=0), base, "relative:today"

    for words, delta in _RELATIVE_UNIT_VARIANTS:
        for word in words:
            if word not in lower:
                continue
            digits_match = re.search(rf"(\d+)\s*{re.escape(word)}", lower)
            count = int(digits_match.group(1)) if digits_match else 1
            start = base - delta * count
            return start, base, f"relative:{count}*{word}"

    return None, None, None


def _extract_date_filters(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    now = datetime.utcnow()
    explicit_start, explicit_end, explicit_reason = _extract_explicit_date_range(text, now)
    if explicit_start and explicit_end:
        return _format_iso(explicit_start), _format_iso(explicit_end), explicit_reason

    relative_start, relative_end, relative_reason = _extract_relative_date_range(text, now)
    if relative_start and relative_end:
        return _format_iso(relative_start), _format_iso(relative_end), relative_reason

    return None, None, None


def _ensure_state(user_data: dict[str, Any]) -> dict[str, Any]:
    state = user_data.get(MANUAL_STATE_KEY)
    if not state:
        state = {"mode": None, "note_id": None, "history": []}
        user_data[MANUAL_STATE_KEY] = state
    return state


def _reset_state(user_data: dict[str, Any], *, keep_note: bool = False) -> None:
    state = _ensure_state(user_data)
    note_id = state.get("note_id") if keep_note else None
    state.clear()
    state.update({"mode": None, "note_id": note_id, "history": []})


def reset_on_new_file(user_data: dict[str, Any]) -> None:
    """Сбрасывает ручной режим при поступлении нового файла/ссылки."""
    _reset_state(user_data, keep_note=False)


def _main_menu(note_id: Optional[int] = None) -> InlineKeyboardMarkup:
    label_note = f"🗒 Активная #{note_id}" if note_id else "🗒 Выбрать заметку"
    rows = [
        [InlineKeyboardButton("📥 Загрузка медиа", callback_data="manual:upload")],
        [InlineKeyboardButton("🔎 Поиск", callback_data="manual:search")],
        [InlineKeyboardButton(label_note, callback_data="manual:list")],
        [InlineKeyboardButton("💬 Чат по заметке", callback_data="manual:chat")],
        [InlineKeyboardButton("↩️ Сброс", callback_data="manual:reset")],
    ]
    return InlineKeyboardMarkup(rows)


async def manual_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда /manual — открыть главное меню ручного режима."""
    _reset_state(context.user_data)
    keyboard = _main_menu()
    await _reply(update, context, "Ручной режим: выбери действие.", reply_markup=keyboard)


async def manual_vector_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запускает чат, который ищет по векторному индексу заметок."""
    _reset_state(context.user_data)
    state = _ensure_state(context.user_data)
    state["mode"] = VECTOR_CHAT_MODE
    state["history"] = []
    await _reply(
        update,
        context,
        "🔎 Напиши вопрос — я подберу релевантные заметки через векторный поиск и отвечу по контексту.",
    )


async def manual_handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()
    data = (query.data if query else "") if hasattr(query, "data") else ""
    state = _ensure_state(context.user_data)

    if data == "manual:menu":
        await _reply(update, context, "Меню ручного режима:", reply_markup=_main_menu(state.get("note_id")))
        return

    if data == "manual:reset":
        _reset_state(context.user_data)
        await _reply(update, context, "Сбросил состояние. Выбери действие заново.", reply_markup=_main_menu())
        return

    if data == "manual:upload":
        _reset_state(context.user_data, keep_note=True)
        await _reply(
            update,
            context,
            "📥 Отправь аудио/видео/voice/документ — обработаем штатным пайплайном."
            " Для текстового запроса вернись в меню.",
            reply_markup=_main_menu(state.get("note_id")),
        )
        return

    if data == "manual:search":
        _reset_state(context.user_data, keep_note=True)
        state["mode"] = "await_search_query"
        await _reply(update, context, "🔎 Введи текст для поиска по заметкам.")
        return

    if data == "manual:list":
        await _list_recent_notes(update, context, state)
        return

    if data.startswith("manual:select:"):
        try:
            note_id = int(data.split(":", 2)[2])
        except Exception:
            await _reply(update, context, "Не удалось распознать заметку.")
            return
        state["note_id"] = note_id
        state["mode"] = "chat"
        state["history"] = []
        await _reply(
            update,
            context,
            f"🗒 Заметка #{note_id} выбрана. Пиши сообщения — отвечу с учётом текста заметки.",
            reply_markup=_main_menu(note_id),
        )
        return

    if data == "manual:chat":
        if not state.get("note_id"):
            await _reply(update, context, "Сначала выбери заметку (поиск или список).", reply_markup=_main_menu())
            return
        state["mode"] = "chat"
        await _reply(update, context, "💬 Чат активирован. Пиши вопрос по выбранной заметке.")
        return


async def manual_handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Перехватывает сообщения в ручном режиме. Возвращает True если сообщение обработано."""
    if not update.message or not update.effective_user:
        return False
    text = (update.message.text or update.message.caption or "").strip()
    if not text:
        return False

    state = _ensure_state(context.user_data)
    mode = state.get("mode")
    if mode not in {"await_search_query", "chat", VECTOR_CHAT_MODE} and not (state.get("note_id") and mode == "chat"):
        return False

    if mode == VECTOR_CHAT_MODE:
        await _handle_vector_chat(update, context, text, state)
        return True

    if mode == "await_search_query":
        await _handle_search_query(update, context, text, state)
        return True

    if mode == "chat" and state.get("note_id"):
        await _handle_chat(update, context, text, state)
        return True

    return False


async def _handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, state: dict[str, Any]) -> None:
    state["mode"] = None
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=getattr(update.effective_user, "username", None),
            first_name=getattr(update.effective_user, "first_name", None),
            last_name=getattr(update.effective_user, "last_name", None),
        )
        index = IndexService()
        results = index.search(user.id, query, k=VECTOR_CONTEXT_COUNT)
        if asyncio.iscoroutine(results):
            results = await results
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual search failed", extra={"error": str(exc)})
        await _reply(update, context, "Не удалось выполнить поиск. Попробуй позже.")
        db.close()
        return
    db.close()

    if not results:
        await _reply(update, context, "Ничего не нашлось.", reply_markup=_main_menu(state.get("note_id")))
        return

    lines = []
    buttons = []
    seen = set()
    for item in results:
        note = item.get("note", {})
        note_id = note.get("id")
        if not note_id or note_id in seen:
            continue
        seen.add(note_id)
        summary = _shorten((note.get("summary") or note.get("text") or "").strip(), 120)
        lines.append(f"#{note_id}: {summary}")
        buttons.append([InlineKeyboardButton(f"Открыть #{note_id}", callback_data=f"manual:select:{note_id}")])

    await _reply(
        update,
        context,
        "Результаты поиска:\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
    )


async def _handle_vector_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str, state: dict[str, Any]) -> None:
    """Обрабатывает вопрос, используя векторный индекс заметок как контекст."""
    state["mode"] = VECTOR_CHAT_MODE
    db = SessionLocal()
    answer = None
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=getattr(update.effective_user, "username", None),
            first_name=getattr(update.effective_user, "first_name", None),
            last_name=getattr(update.effective_user, "last_name", None),
        )
        index = IndexService()
        date_from, date_to, date_reason = _extract_date_filters(query)
        if date_reason:
            logger.info(
                "vector chat date filter",
                extra={
                    "user_id": user.id,
                    "date_from": date_from,
                    "date_to": date_to,
                    "reason": date_reason,
                },
            )
        results = index.search(
            user.id,
            query,
            k=VECTOR_CONTEXT_COUNT,
            date_from=date_from,
            date_to=date_to,
        )
        if asyncio.iscoroutine(results):
            results = await results
        if not results:
            await _reply(
                update,
                context,
                "Ничего не нашлось по запросу. Попробуй переформулировать.",
            )
            return

        contexts = []
        for idx, item in enumerate(results[: VECTOR_CONTEXT_COUNT], start=1):
            note = item.get("note", {})
            note_id = note.get("id")
            chunk = (item.get("chunk") or "").strip()
            summary = (note.get("summary") or "").strip()
            chunk_line = chunk.replace("\n", " ")
            summary_line = summary.replace("\n", " ")
            if note_id:
                prefix = f"Заметка {idx} (ID {note_id})"
            else:
                prefix = f"Заметка {idx}"
            if summary_line:
                contexts.append(f"{prefix} summary: {summary_line}")
            if chunk_line:
                contexts.append(f"{prefix} chunk: {chunk_line}")
            ts_iso = note.get("ts")
            if ts_iso:
                contexts.append(f"{prefix} date: {ts_iso}")
            tags = note.get("tags") or []
            if tags:
                contexts.append(f"{prefix} tags: {', '.join(tags)}")
            groups = note.get("groups") or []
            if groups:
                contexts.append(f"{prefix} groups: {', '.join(groups)}")

        logger.info(
            "vector chat context assembled for user %s query %s contexts %s",
            user.id,
            query,
            contexts,
        )

        system_prompt = (
            "Ты — эксперт CyberKitty. Отвечай на вопросы, опираясь только на предоставленные фрагменты из заметок. "
            "Не добавляй номера источников или списки ссылки вида [1], [2]."
        )
        user_prompt = (
            f"Контекст:\n" + "\n".join(contexts) + "\n\n"
            f"Вопрос пользователя: {query}\n\n"
            "Дай короткий, понятный ответ по-русски."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        logger.info(
            "vector chat prompts for user %s:\nSYSTEM: %s\nUSER: %s",
            user.id,
            system_prompt,
            user_prompt[:1200] + ("…" if len(user_prompt) > 1200 else ""),
        )
        answer = await call_agent_llm_with_retry(messages, timeout=25, retries=1)
    except AgentLLMError as exc:
        logger.warning("vector chat LLM call failed", extra={"error": str(exc)})
        answer = "Не удалось получить ответ от ИИ‑модуля. Попробуй позже."
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector chat failed", extra={"error": str(exc)})
        answer = "Ошибка поиска по заметкам. Попробуй повторить чуть позже."
    finally:
        db.close()

    if answer:
        answer = re.sub(r"\s*\[\d+\]\s*$", "", answer).strip()

    if not answer:
        answer = "Не удалось сформировать ответ. Попробуй переформулировать вопрос."

    history = state.setdefault("history", [])
    history.append({"q": query, "a": answer})
    if len(history) > MAX_HISTORY_LEN:
        history.pop(0)

    await _reply(update, context, answer)

    logger.info(
        "vector chat answer for user %s: %s",
        user.id,
        answer[:600].replace("\n", " "),
    )


async def _handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str, state: dict[str, Any]) -> None:
    note_id = state.get("note_id")
    if not note_id:
        await _reply(update, context, "Сначала выбери заметку.", reply_markup=_main_menu())
        return

    db = SessionLocal()
    note: Optional[Note] = None
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=getattr(update.effective_user, "username", None),
            first_name=getattr(update.effective_user, "first_name", None),
            last_name=getattr(update.effective_user, "last_name", None),
        )
        note = NoteService(db).get_note(note_id)
        if not note or note.user_id != user.id:
            await _reply(update, context, "Заметка не найдена или принадлежит другому пользователю.")
            return
    finally:
        db.close()

    try:
        reply_text = await _llm_for_note(note, user_text, state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual chat failed", extra={"error": str(exc)})
        await _reply(update, context, "LLM сейчас недоступна. Попробуй ещё раз позже.")
        return

    await _reply(update, context, reply_text, reply_markup=_main_menu(note_id))


async def _list_recent_notes(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=getattr(update.effective_user, "username", None),
            first_name=getattr(update.effective_user, "first_name", None),
            last_name=getattr(update.effective_user, "last_name", None),
        )
        note_service = NoteService(db)
        notes: List[Note] = (
            note_service.db.query(Note)
            .filter(Note.user_id == user.id)
            .order_by(Note.id.desc())
            .limit(5)
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("manual list notes failed", extra={"error": str(exc)})
        await _reply(update, context, "Не удалось получить список заметок.")
        db.close()
        return
    finally:
        db.close()

    if not notes:
        await _reply(update, context, "Нет заметок. Сначала создай или загрузь медиа.", reply_markup=_main_menu())
        return

    buttons = []
    lines = []
    for note in notes:
        title = _shorten(note.summary or note.text or "(пусто)", 120)
        lines.append(f"#{note.id}: {title}")
        buttons.append([InlineKeyboardButton(f"Выбрать #{note.id}", callback_data=f"manual:select:{note.id}")])

    await _reply(
        update,
        context,
        "Недавние заметки:\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _llm_for_note(note: Note, user_text: str, state: dict[str, Any]) -> str:
    history: List[Dict[str, str]] = state.get("history") or []
    context_block = _shorten((note.summary or "") + "\n" + (note.text or ""), MAX_CONTEXT_LEN)
    system_prompt = (
        "Ты помощник, отвечающий по одной выбранной заметке. "
        "Используй только текст заметки и историю диалога. "
        "Не выдумывай факты и отвечай кратко."
    )
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Контекст заметки #{note.id}:\n{context_block}"},
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        raw = await call_agent_llm_with_retry(messages, timeout=25, retries=1)
    except AgentLLMError as exc:
        logger.warning("LLM call failed", extra={"note_id": note.id, "error": str(exc)})
        raise

    reply = (raw or "").strip() or "Готово."

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply})
    if len(history) > MAX_HISTORY_LEN:
        # keep last entries
        history[:] = history[-MAX_HISTORY_LEN:]
    state["history"] = history
    return reply


def _shorten(text: Optional[str], limit: int) -> str:
    if not text:
        return ""
    snippet = " ".join(str(text).split())
    if len(snippet) <= limit:
        return snippet
    return snippet[: limit - 1] + "…"


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    if getattr(update, "message", None):
        return await update.message.reply_text(text, **kwargs)
    if getattr(update, "callback_query", None):
        return await update.callback_query.message.reply_text(text, **kwargs)
    if update.effective_user:
        return await context.bot.send_message(chat_id=update.effective_user.id, text=text, **kwargs)
    return None
