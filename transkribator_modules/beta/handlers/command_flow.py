"""Command flow handlers for beta mode."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.utils.metrics import record_event
from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import Note
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

    await update.message.reply_text(
        build_confirmation_text(command_payload),
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


_NOTE_TYPES = {"meeting", "idea", "task", "media", "recipe", "journal", "any"}


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
            'prompt': 'Какое действие выполнить? (summary/protocol/bullets/tasks_split/save_drive/create_doc/update_index).',
            'parser': _parse_action,
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
}

MANUAL_FORM_INTRO = {
    'qa': 'Заполним форму для поиска. Можно ввести "отмена" чтобы выйти.',
    'filter': 'Настроим фильтр по заметкам. Все поля можно оставить пустыми, кроме типа.',
    'digest': 'Соберём дайджест за период. Нужны даты начала и конца.',
    'action': 'Выбери заметку и действие (summary/protocol/bullets/tasks_split/save_drive/create_doc/update_index). Ниже список последних заметок для ориентира.',
    'calendar': 'Выбери режим календаря: changes (просмотр событий) или timebox (создать блок). Ненужные поля оставляй пустыми.',
}

_CANCEL_KEYWORDS = {'отмена', 'cancel', '/cancel'}


async def _start_manual_form(update: Update, context: ContextTypes.DEFAULT_TYPE, command_payload: dict) -> None:
    intent = (command_payload.get('command') or {}).get('intent')
    steps = MANUAL_FORM_DEFINITIONS.get(intent or '')
    if not steps:
        await update.callback_query.message.reply_text(
            "К сожалению, пока нет ручной формы для этой команды."
        )
        return

    beta_state = context.user_data.setdefault('beta', {})
    original_args = dict((command_payload.get('command') or {}).get('args') or {})
    if intent == 'filter':
        original_args.setdefault('type', 'any')
        original_args.setdefault('k', 8)
    elif intent == 'qa':
        original_args.setdefault('k', 5)
    elif intent == 'action':
        # keep as is, but ensure keys exist for prompts if known
        pass

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


async def _prompt_manual_form_step(send_callable, form_state: dict) -> None:
    intent = form_state['intent']
    steps = MANUAL_FORM_DEFINITIONS[intent]
    step_index = form_state['step']
    if step_index >= len(steps):
        return
    step_def = steps[step_index]
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

    intent = form_state['intent']
    steps = MANUAL_FORM_DEFINITIONS[intent]
    step_index = form_state['step']
    if step_index >= len(steps):
        await update.message.reply_text('Форма уже заполнена. Начни заново, если нужно изменить данные.')
        return True

    step_def = steps[step_index]
    parser: ManualStepParser = step_def['parser']
    defaults = form_state.get('defaults') or {}
    default_value = defaults.get(step_def['field'])
    value, error = parser(message_text, default_value)
    if error:
        await update.message.reply_text(error)
        return True

    form_state['data'][step_def['field']] = value
    form_state['step'] = step_index + 1

    if form_state['step'] >= len(steps):
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

    if intent == 'action':
        note_id = data.get('note_id')
        action = data.get('action')
        if not note_id or not action:
            return None
        return {'command': {'intent': 'action', 'args': {'note_id': note_id, 'action': action}}}

    return None
