"""Command flow handlers for beta mode."""

from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.utils.metrics import record_event
from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import Note, NoteStatus
from ..command_processor import execute_command


CONFIRM_KEYBOARD = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("Да", callback_data="beta:cmd:yes"),
            InlineKeyboardButton("Нет", callback_data="beta:cmd:no"),
        ],
        [InlineKeyboardButton("Изменить…", callback_data="beta:cmd:edit")],
    ]
)


def build_confirmation_text(command_payload: dict) -> str:
    command = command_payload.get("command", {}) if command_payload else {}
    intent = command.get("intent") or "command"
    args = command.get("args") or {}
    query = args.get("query") or ""
    action = args.get("action") or ""

    parts: list[str] = [f"Похоже, это команда: *{intent}*. "]
    if query:
        parts.append(f"Запрос: `{query}`. ")
    if action:
        parts.append(f"Действие: `{action}`. ")
    parts.append("Выполнить?")
    return "".join(parts)


async def show_command_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    command_payload: dict,
) -> None:
    logger.info(
        "Показываем подтверждение команды",
        extra={"user_id": update.effective_user.id if update.effective_user else None},
    )
    context.user_data.setdefault("beta", {})["command_payload"] = command_payload

    message = update.message or (update.callback_query.message if update.callback_query else None)
    text = build_confirmation_text(command_payload)

    if message:
        await message.reply_text(text, reply_markup=CONFIRM_KEYBOARD, parse_mode="Markdown")
    else:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=text,
            reply_markup=CONFIRM_KEYBOARD,
            parse_mode="Markdown",
        )


async def handle_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    query = update.callback_query
    beta_state = context.user_data.setdefault("beta", {})
    command_payload = beta_state.get("command_payload")

    if not command_payload:
        await query.answer("Команда не найдена", show_alert=True)
        return

    if action == "yes":
        command = (command_payload.get("command") or {})
        args = command.get("args") or {}
        intent = command.get("intent") or ""
        if intent == "calendar":
            mode_value = (args.get("mode") or "").strip().lower()
            need_mode = mode_value not in {"changes", "timebox"}
            need_start = False
            if not need_mode and mode_value == "timebox" and not (args.get("start_at") or "").strip():
                need_start = True
            if need_mode or need_start:
                beta_state["calendar_pending"] = {
                    "command_payload": command_payload,
                    "need_mode": need_mode,
                    "need_start_at": False if need_mode else need_start,
                }
                beta_state["command_payload"] = command_payload
                await query.answer("Нужно уточнить детали")
                await query.edit_message_reply_markup(reply_markup=None)
                hint = _calendar_missing_args(args)
                if hint:
                    await query.message.reply_text(hint)
                elif need_start:
                    await query.message.reply_text(
                        "Напиши дату и время встречи, например \"завтра в 15:30\"."
                    )
                return
        result_text = await execute_command(update.effective_user, command_payload)
        await query.answer("Команда выполняется")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(result_text, parse_mode="Markdown")
        record_event('beta_command_executed', user_id=update.effective_user.id, command=command_payload)
    elif action in {"no", "edit"}:
        await query.answer("Открываю ручную форму")
        await _start_manual_form(update, context, command_payload)
    else:
        await query.answer("Неизвестное действие", show_alert=True)


# ------------------------- manual form support ------------------------- #

ManualStepParser = Callable[[str, Any], tuple[Any | None, str | None]]


_NOTE_TYPES = {"meeting", "idea", "task", "media", "recipe", "journal", "any", "other"}


def _calendar_missing_args(args: dict) -> str | None:
    """Поиск недостающих данных для календарной команды."""

    mode_raw = (args.get("mode") or "").strip().lower()
    if not mode_raw:
        return "Уточни, что сделать с календарём: показать события (`changes`) или создать таймбокс (`timebox`)."
    if mode_raw not in {"changes", "timebox"}:
        return "Календарь понимает только режимы changes (показать) или timebox (создать событие)."

    if mode_raw == "timebox":
        start_at = (args.get("start_at") or "").strip()
        if not start_at:
            return "Нужно указать дату и время начала события (например, 2025-09-29 14:30)."

    return None


def _infer_calendar_mode(text: str) -> str | None:
    text_low = (text or "").strip().lower()
    if not text_low:
        return None
    if text_low in {"timebox", "таймбокс"}:
        return "timebox"
    if text_low in {"changes", "change"}:
        return "changes"
    if any(keyword in text_low for keyword in ("созд", "добав", "заплан", "назнач", "встреч")):
        return "timebox"
    if any(keyword in text_low for keyword in ("покаж", "список", "что", "вывед")):
        return "changes"
    return None


def _infer_calendar_start_at(text: str) -> str | None:
    if not text:
        return None

    text_low = text.lower()
    now = datetime.utcnow().replace(second=0, microsecond=0)

    # относительные конструкции "через N ..."
    relative_match = re.search(r"через\s+(\d+)\s*(минут[ау]?|час(?:а|ов)?|день|дня|дней)", text_low)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2)
        if unit.startswith("минут"):
            candidate = now + timedelta(minutes=amount)
        elif unit.startswith("час"):
            candidate = now + timedelta(hours=amount)
        else:
            candidate = now + timedelta(days=amount)
        return candidate.strftime("%Y-%m-%d %H:%M")

    base = None
    if "послезавтра" in text_low:
        base = now + timedelta(days=2)
    elif "завтра" in text_low:
        base = now + timedelta(days=1)
    elif "сегодня" in text_low:
        base = now

    # явное время HH[:MM]
    time_match = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\b", text_low)
    hour = None
    minute = 0
    if time_match:
        hour = int(time_match.group(1))
        if hour > 23:
            hour = hour % 24
        if time_match.group(2):
            minute = int(time_match.group(2))

    # слова "утром/вечером/ночью/днём"
    if hour is None:
        if "утром" in text_low or "утра" in text_low:
            hour = 9
        elif "днём" in text_low or "днем" in text_low:
            hour = 12
        elif "вечером" in text_low or "вечера" in text_low:
            hour = 18
        elif "ночью" in text_low or "ночь" in text_low:
            hour = 22

    if base is None and hour is None:
        return None

    if base is None:
        base = now
    if hour is None:
        return None

    candidate = base.replace(hour=hour, minute=minute)
    return candidate.strftime("%Y-%m-%d %H:%M")


async def handle_calendar_clarification(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message_text: str,
) -> bool:
    beta_state = context.user_data.setdefault("beta", {})
    pending = beta_state.get("calendar_pending")
    if not pending:
        return False

    message = update.message
    if not message:
        return False

    command_payload = pending.get("command_payload")
    if not command_payload:
        beta_state.pop("calendar_pending", None)
        return False

    command = command_payload.setdefault("command", {})
    args = command.setdefault("args", {})

    text = (message_text or "").strip()
    if not text:
        await message.reply_text("Напиши, какие действия выполнить с календарём.")
        return True

    if pending.get("need_mode", False):
        detected_mode = _infer_calendar_mode(text)
        if detected_mode:
            args["mode"] = detected_mode
            pending["need_mode"] = False
        else:
            await message.reply_text(
                "Не понял режим. Напиши, нужно показать события (`changes`) или создать встречу (`timebox`)."
            )
            return True

    mode = (args.get("mode") or "").strip().lower()

    if mode == "timebox" and not (args.get("start_at") or "").strip():
        start_at = _infer_calendar_start_at(text)
        if start_at:
            args["start_at"] = start_at
            pending["need_start_at"] = False
        else:
            pending["need_start_at"] = True
    else:
        pending["need_start_at"] = False

    if pending.get("need_mode"):
        hint = _calendar_missing_args(args) or "Укажи режим: changes или timebox."
        await message.reply_text(hint)
        return True

    if pending.get("need_start_at"):
        await message.reply_text("Напиши дату и время встречи, например, \"завтра в 15:00\".")
        return True

    beta_state.pop("calendar_pending", None)
    beta_state["command_payload"] = command_payload

    result_text = await execute_command(update.effective_user, command_payload)
    await message.reply_text(result_text, parse_mode="Markdown")
    record_event('beta_command_executed', user_id=update.effective_user.id, command=command_payload)
    return True


def _parse_text(value: str, default: Any, required: bool = True) -> tuple[str | None, str | None]:
    candidate = (value or "").strip()
    if candidate:
        return candidate, None
    if default not in (None, ""):
        return default, None
    if required:
        return None, "Нужно ввести значение."
    return None, None


def _parse_int(value: str, default: int) -> tuple[int | None, str | None]:
    candidate = (value or "").strip()
    if not candidate:
        return default, None
    try:
        number = int(candidate)
        if number <= 0:
            raise ValueError
        return number, None
    except ValueError:
        return None, "Нужно ввести положительное число."


def _parse_tags(value: str, default: Any) -> tuple[list[str], str | None]:
    candidate = (value or "").strip()
    if not candidate:
        return list(default or []), None
    lowered = candidate.lower()
    if lowered in {'none', 'нет', '-', 'без тегов'}:
        return [], None
    tags = [tag.strip() for tag in candidate.split(',') if tag.strip()]
    return tags, None


def _parse_date(value: str, default: Any, required: bool = False) -> tuple[str | None, str | None]:
    candidate = (value or "").strip()
    if not candidate:
        if default:
            return default, None
        if required:
            return None, "Введите дату в формате ГГГГ-ММ-ДД."
        return None, None

    for variant in (candidate, f"{candidate}T00:00:00", f"{candidate} 00:00"):
        try:
            dt = datetime.fromisoformat(variant)
            return dt.isoformat(), None
        except ValueError:
            continue
    return None, "Не удалось распознать дату. Используй формат ГГГГ-ММ-ДД."


def _parse_optional_text(value: str, default: Any = None) -> tuple[str | None, str | None]:
    candidate = (value or "").strip()
    if candidate:
        return candidate, None
    if default not in (None, ""):
        return default, None
    return None, None


def _parse_optional_int(value: str, default: Any = None) -> tuple[int | None, str | None]:
    candidate = (value or "").strip()
    if not candidate:
        if default in (None, ""):
            return None, None
        try:
            return int(default), None
        except Exception:
            return None, None
    try:
        number = int(candidate)
        if number <= 0:
            raise ValueError
        return number, None
    except ValueError:
        return None, "Нужно указать положительное число или оставить поле пустым."


def _parse_calendar_mode(value: str, default: str = 'changes') -> tuple[str | None, str | None]:
    candidate = (value or "").strip().lower()
    if not candidate:
        candidate = (default or 'changes').strip().lower()
    if candidate in {'changes', 'timebox'}:
        return candidate, None
    return None, "Доступны варианты changes или timebox."


def _parse_action(value: str, default: Any) -> tuple[str | None, str | None]:
    allowed = {
        "summary",
        "protocol",
        "bullets",
        "tasks_split",
        "post",
        "quotes",
        "timed_outline",
        "task_from_note",
        "free_prompt",
        "retag",
        "move",
        "save_drive",
        "create_doc",
        "update_index",
    }
    candidate = (value or "").strip().lower()
    if not candidate:
        candidate = (default or "").strip().lower()
    if candidate in allowed:
        return candidate, None
    return None, f"Доступные действия: {', '.join(sorted(allowed))}."


def _parse_note_type(value: str, default: Any) -> tuple[str | None, str | None]:
    candidate = (value or "").strip().lower()
    if not candidate:
        candidate = (default or "").strip().lower()
    if candidate in _NOTE_TYPES:
        return candidate, None
    return None, f"Неверный тип. Доступно: {', '.join(sorted(_NOTE_TYPES))}."


def _parse_optional_note_type(value: str, default: Any) -> tuple[str | None, str | None]:
    candidate = (value or "").strip().lower()
    if not candidate:
        if default in (None, ""):
            return None, None
        candidate = str(default).strip().lower()
    if not candidate:
        return None, None
    if candidate in _NOTE_TYPES:
        return candidate, None
    return None, f"Неверный тип. Доступно: {', '.join(sorted(_NOTE_TYPES))}."


def _parse_required_int(value: str, default: Any) -> tuple[int | None, str | None]:
    candidate = (value or "").strip()
    if not candidate and default not in (None, ""):
        candidate = str(default)
    if not candidate:
        return None, "Нужно указать число."
    try:
        number = int(candidate)
        if number <= 0:
            raise ValueError
        return number, None
    except ValueError:
        return None, "Нужно указать положительный номер заметки."


def _parse_note_status(value: str, default: Any) -> tuple[str | None, str | None]:
    candidate = (value or "").strip().lower()
    if not candidate:
        if default not in (None, ""):
            return default, None
        return None, None

    mapping = {
        'processed': NoteStatus.PROCESSED.value,
        'done': NoteStatus.PROCESSED.value,
        'ready': NoteStatus.PROCESSED.value,
        'backlog': NoteStatus.BACKLOG.value,
        'later': NoteStatus.BACKLOG.value,
        'raw': NoteStatus.PROCESSED_RAW.value,
    }
    value_mapped = mapping.get(candidate)
    if not value_mapped:
        return None, "Доступно: processed, backlog, raw (или оставь пусто)."
    return value_mapped, None


_HELP_ACTIONS = {
    '1': 'save_note',
    'сохранить': 'save_note',
    'сохранить как заметку': 'save_note',
    'save': 'save_note',
    'save_note': 'save_note',
    '2': 'show_presets',
    'пресеты': 'show_presets',
    'открыть меню пресетов': 'show_presets',
    'presets': 'show_presets',
    'show_presets': 'show_presets',
}


def _parse_help_choice(value: str, default: Any = None) -> tuple[str | None, str | None]:
    candidate = (value or "").strip().lower()
    if not candidate and default not in (None, ""):
        candidate = str(default).strip().lower()
    if not candidate:
        return None, "Выбери действие: 1 — сохранить как заметку, 2 — открыть меню пресетов."
    normalized = _HELP_ACTIONS.get(candidate)
    if not normalized:
        return None, "Ответь числом 1 или 2, либо фразой из вариантов."
    return normalized, None


def _requires_action(*actions: str):
    required = {action.lower() for action in actions if action}

    def _predicate(form_state: dict) -> bool:
        data = form_state.get('data') or {}
        defaults = form_state.get('defaults') or {}
        current = (data.get('action') or defaults.get('action') or '').strip().lower()
        return current in required

    return _predicate


MANUAL_FORM_DEFINITIONS = {
    'qa': [
        {
            'field': 'query',
            'prompt': 'Что ищем? Напиши текст вопроса.',
            'parser': lambda value, default=None: _parse_text(value, default, required=True),
        },
        {
            'field': 'k',
            'prompt': 'Сколько результатов показать? (по умолчанию 5)',
            'parser': lambda value, default=5: _parse_int(value, default or 5),
        },
    ],
    'filter': [
        {
            'field': 'type',
            'prompt': 'Тип заметок (meeting/idea/task/media/recipe/journal/any).',
            'parser': _parse_note_type,
        },
        {
            'field': 'tags',
            'prompt': 'Теги через запятую (оставь пусто, если не нужны).',
            'parser': _parse_tags,
        },
        {
            'field': 'time_from',
            'prompt': 'Дата с (ГГГГ-ММ-ДД, оставь пусто если не нужно).',
            'parser': lambda value, default=None: _parse_date(value, default, required=False),
        },
        {
            'field': 'time_to',
            'prompt': 'Дата по (ГГГГ-ММ-ДД, оставь пусто если не нужно).',
            'parser': lambda value, default=None: _parse_date(value, default, required=False),
        },
        {
            'field': 'k',
            'prompt': 'Сколько заметок вернуть? (по умолчанию 8)',
            'parser': lambda value, default=8: _parse_int(value, default or 8),
        },
    ],
    'digest': [
        {
            'field': 'time_from',
            'prompt': 'Начальная дата периода (ГГГГ-ММ-ДД).',
            'parser': lambda value, default=None: _parse_date(value, default, required=True),
        },
        {
            'field': 'time_to',
            'prompt': 'Конечная дата периода (ГГГГ-ММ-ДД).',
            'parser': lambda value, default=None: _parse_date(value, default, required=True),
        },
    ],
    'action': [
        {
            'field': 'note_id',
            'prompt': 'Укажи ID заметки (число).',
            'parser': _parse_required_int,
        },
        {
            'field': 'action',
            'prompt': (
                'Какое действие выполнить? '
                '(summary/protocol/bullets/tasks_split/post/quotes/timed_outline/'
                'task_from_note/free_prompt/retag/move/save_drive/create_doc/update_index).'
            ),
            'parser': _parse_action,
        },
        {
            'field': 'preset_id',
            'prompt': 'ID пресета (оставь пусто для выбора по умолчанию).',
            'parser': _parse_optional_text,
            'condition': _requires_action('post', 'quotes', 'timed_outline', 'task_from_note'),
        },
        {
            'field': 'prompt',
            'prompt': 'Текст запроса для свободного промпта.',
            'parser': lambda value, default=None: _parse_text(value, default, required=True),
            'condition': _requires_action('free_prompt'),
        },
        {
            'field': 'target_type',
            'prompt': 'Новый тип заметки (meeting/idea/task/media/recipe/journal/any, оставь пусто чтобы не менять).',
            'parser': _parse_optional_note_type,
            'condition': _requires_action('move'),
        },
        {
            'field': 'target_status',
            'prompt': 'Новый статус (processed/backlog/raw, оставь пусто чтобы не менять).',
            'parser': _parse_note_status,
            'condition': _requires_action('move'),
        },
        {
            'field': 'new_tags',
            'prompt': 'Новый список тегов через запятую (оставь пусто, чтобы оставить текущие).',
            'parser': _parse_tags,
            'condition': _requires_action('retag'),
        },
        {
            'field': 'remove_tags',
            'prompt': 'Какие теги убрать? (опционально, через запятую).',
            'parser': _parse_tags,
            'condition': _requires_action('retag'),
        },
        {
            'field': 'task_due',
            'prompt': 'Дедлайн/дата для новой задачи (опционально).',
            'parser': lambda value, default=None: _parse_optional_text(value, default),
            'condition': _requires_action('task_from_note'),
        },
    ],
    'calendar': [
        {
            'field': 'mode',
            'prompt': 'Режим календаря (changes/timebox). Оставь пусто для changes.',
            'parser': lambda value, default='changes': _parse_calendar_mode(value, default or 'changes'),
        },
        {
            'field': 'time_from',
            'prompt': 'Начало периода (ГГГГ-ММ-ДД или ISO, опционально).',
            'parser': lambda value, default=None: _parse_date(value, default, required=False),
        },
        {
            'field': 'time_to',
            'prompt': 'Конец периода (ГГГГ-ММ-ДД или ISO, опционально).',
            'parser': lambda value, default=None: _parse_date(value, default, required=False),
        },
        {
            'field': 'k',
            'prompt': 'Сколько событий показать? (по умолчанию 10).',
            'parser': lambda value, default=10: _parse_int(value, default or 10),
        },
        {
            'field': 'start_at',
            'prompt': 'Начало таймбокса (ГГГГ-ММ-ДД HH:MM, опционально).',
            'parser': lambda value, default=None: _parse_optional_text(value, default),
        },
        {
            'field': 'duration_minutes',
            'prompt': 'Длительность таймбокса в минутах (по умолчанию 60).',
            'parser': lambda value, default=60: _parse_int(value, default or 60),
        },
        {
            'field': 'title',
            'prompt': 'Заголовок события (опционально).',
            'parser': lambda value, default=None: _parse_optional_text(value, default),
        },
        {
            'field': 'description',
            'prompt': 'Описание события (опционально).',
            'parser': lambda value, default=None: _parse_optional_text(value, default),
        },
        {
            'field': 'note_id',
            'prompt': 'ID заметки для привязки (опционально).',
            'parser': _parse_optional_int,
        },
    ],
    'help': [
        {
            'field': 'help_action',
            'prompt': 'Чем помочь? 1 — сохранить как заметку, 2 — открыть меню пресетов.',
            'parser': _parse_help_choice,
        },
    ],
}

MANUAL_FORM_INTRO = {
    'qa': 'Заполним форму для поиска. Можно ввести "отмена" чтобы выйти.',
    'filter': 'Настроим фильтр по заметкам. Все поля можно оставить пустыми, кроме типа.',
    'digest': 'Соберём дайджест за период. Нужны даты начала и конца.',
    'action': (
        'Выбери заметку и действие (summary/protocol/bullets/tasks_split/post/quotes/timed_outline/'
        'task_from_note/free_prompt/retag/move/save_drive/create_doc/update_index). '
        'Ниже список последних заметок для ориентира.'
    ),
    'calendar': 'Выбери режим календаря: changes (просмотр событий) или timebox (создать блок). Ненужные поля оставляй пустыми.',
    'help': 'Выбери, что сделать: сохранить заметку или открыть меню пресетов.',
}

_CANCEL_KEYWORDS = {'отмена', 'cancel', '/cancel'}


async def _start_manual_form(update: Update, context: ContextTypes.DEFAULT_TYPE, command_payload: dict) -> None:
    intent = (command_payload.get('command') or {}).get('intent')
    steps = MANUAL_FORM_DEFINITIONS.get(intent or '')
    if not steps:
        context.user_data.setdefault('beta', {})['manual_form'] = None
        await update.callback_query.message.reply_text(
            "Пока нет ручной формы для этой команды. Попробуй сохранить заметку или открыть меню пресетов."
        )
        return

    beta_state = context.user_data.setdefault('beta', {})
    original_args = dict((command_payload.get('command') or {}).get('args') or {})
    if intent == 'filter':
        original_args.setdefault('type', 'any')
        original_args.setdefault('k', 8)
    elif intent == 'qa':
        original_args.setdefault('k', 5)
    elif intent == 'help':
        original_args.setdefault('action', 'save_note')

    form_state = {
        'intent': intent,
        'step': 0,
        'data': {},
        'defaults': original_args,
        'command_payload': command_payload,
    }

    beta_state['manual_form'] = form_state

    intro = MANUAL_FORM_INTRO.get(intent)
    if intro:
        await update.callback_query.message.reply_text(intro)

    if intent == 'action':
        hints = _build_recent_notes_hint(update.effective_user.id)
        if hints:
            await update.callback_query.message.reply_text(hints, parse_mode='Markdown')

    await _prompt_manual_form_step(update.callback_query.message.reply_text, form_state)


def _build_recent_notes_hint(user_id: int, limit: int = 5) -> str | None:
    with SessionLocal() as session:
        notes = (
            session.query(Note)
            .filter(Note.user_id == user_id)
            .order_by(Note.ts.desc())
            .limit(limit)
            .all()
        )
        if not notes:
            return None
        lines = ["Последние заметки:"]
        for note in notes:
            preview = (note.summary or note.text or '').strip()
            if len(preview) > 70:
                preview = preview[:67] + '…'
            lines.append(f"• ID {note.id} — {note.type_hint or 'other'} — {preview}")
        return "\n".join(lines)


def _resolve_form_step(form_state: dict) -> dict | None:
    intent = form_state['intent']
    steps = MANUAL_FORM_DEFINITIONS[intent]
    while form_state['step'] < len(steps):
        step_def = steps[form_state['step']]
        condition = step_def.get('condition')
        if condition and not condition(form_state):
            form_state['step'] += 1
            continue
        return step_def
    return None


async def _prompt_manual_form_step(send_callable, form_state: dict) -> None:
    step_def = _resolve_form_step(form_state)
    if not step_def:
        return
    prompt = step_def['prompt']
    defaults = form_state.get('defaults') or {}
    default_value = defaults.get(step_def['field'])
    if default_value not in (None, '', [], {}):
        prompt += f"\nТекущее значение: {default_value}. Оставь пусто, чтобы оставить без изменений."
    await send_callable(prompt)


async def handle_manual_form_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    beta_state = context.user_data.setdefault('beta', {})
    form_state = beta_state.get('manual_form')
    if not isinstance(form_state, dict):
        return False

    message_text = (text or '').strip()
    if message_text.lower() in _CANCEL_KEYWORDS:
        beta_state['manual_form'] = None
        await update.message.reply_text('Ок, отменяем ручную форму.')
        return True

    step_def = _resolve_form_step(form_state)
    if not step_def:
        await update.message.reply_text('Форма уже заполнена. Начни заново, если нужно изменить данные.')
        return True

    parser: ManualStepParser = step_def['parser']
    defaults = form_state.get('defaults') or {}
    default_value = defaults.get(step_def['field'])
    provided_map = form_state.setdefault('_provided', {})
    provided_map[step_def['field']] = bool(message_text)

    value, error = parser(message_text, default_value)
    if error:
        await update.message.reply_text(error)
        return True

    form_state['data'][step_def['field']] = value
    form_state['step'] += 1

    next_step = _resolve_form_step(form_state)
    if not next_step:
        payload = _build_manual_command(form_state)
        if not payload:
            beta_state['manual_form'] = None
            await update.message.reply_text('Не удалось собрать команду. Попробуй ещё раз.')
            return True

        beta_state['manual_form'] = None
        beta_state['command_payload'] = payload
        result_text = await execute_command(update.effective_user, payload)
        await update.message.reply_text(result_text, parse_mode='Markdown')
        record_event('beta_command_executed_manual', user_id=update.effective_user.id, command=payload)
        return True

    await _prompt_manual_form_step(update.message.reply_text, form_state)
    return True


def _build_manual_command(form_state: dict) -> dict | None:
    intent = form_state['intent']
    data = form_state.get('data') or {}

    if intent == 'qa':
        query = data.get('query')
        if not query:
            return None
        return {'command': {'intent': 'qa', 'args': {'query': query, 'k': data.get('k', 5)}}}

    if intent == 'filter':
        args = {
            'type': data.get('type', 'any'),
            'tags': data.get('tags', []),
            'k': data.get('k', 8),
        }
        time_from = data.get('time_from')
        time_to = data.get('time_to')
        if time_from or time_to:
            args['time_range'] = {'from': time_from, 'to': time_to}
        return {'command': {'intent': 'filter', 'args': args}}

    if intent == 'digest':
        if not data.get('time_from') or not data.get('time_to'):
            return None
        args = {'time_range': {'from': data['time_from'], 'to': data['time_to']}}
        return {'command': {'intent': 'digest', 'args': args}}

    if intent == 'help':
        choice = data.get('help_action')
        if not choice:
            return None
        return {'command': {'intent': 'help', 'args': {'action': choice}}}

    if intent == 'action':
        note_id = data.get('note_id')
        action = data.get('action')
        if not note_id or not action:
            return None
        provided_flags = form_state.get('_provided', {})
        args = {'note_id': note_id, 'action': action}
        if data.get('preset_id'):
            args['preset_id'] = data['preset_id']
        if data.get('prompt'):
            args['prompt'] = data['prompt']
        if data.get('target_type'):
            args['target_type'] = data['target_type']
        if data.get('target_status'):
            args['target_status'] = data['target_status']
        if provided_flags.get('new_tags'):
            args['new_tags'] = data.get('new_tags') or []
        if data.get('remove_tags') and provided_flags.get('remove_tags'):
            args['remove_tags'] = data['remove_tags']
        if data.get('task_due'):
            args['task_due'] = data['task_due']
        return {'command': {'intent': 'action', 'args': args}}

    return None
