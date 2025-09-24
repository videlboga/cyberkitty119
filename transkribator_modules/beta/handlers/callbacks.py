"""Обработчики callback-кнопок бета-режима."""

from datetime import timedelta
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import NoteStatus, Reminder

from .content_flow import _build_main_keyboard, TYPE_LABELS, compose_header
from .command_flow import handle_command_callback
from ..presets import get_presets, Preset
from ..content_processor import ContentProcessor
from .entrypoint import process_text
from transkribator_modules.utils.metrics import record_event

_processor = ContentProcessor()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""

    parts = data.split(":")
    action = parts[2] if len(parts) >= 3 else None

    logger.info("Beta callback", extra={"data": data, "user_id": update.effective_user.id})

    if data.startswith("beta:cmd:"):
        await handle_command_callback(update, context, parts[-1])
        return

    if data.startswith("beta:reminder:"):
        await _handle_reminder_callback(update, context, data)
        return

    if action == "now":
        await _show_preset_menu(update, context)
    elif action == "later":
        await _save_note(update, context, status=NoteStatus.BACKLOG.value, preset=None)
    elif action == "raw":
        await _save_note(update, context, status=NoteStatus.PROCESSED_RAW.value, preset=None)
    elif action == "type_menu":
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(title.capitalize(), callback_data=f"beta:type:{slug}")]
                for slug, title in TYPE_LABELS.items()
            ]
            + [[InlineKeyboardButton("↩ Назад", callback_data="beta:act:back")]]
        )
        await query.edit_message_reply_markup(reply_markup=keyboard)
    elif action == "back":
        await query.edit_message_reply_markup(reply_markup=_build_main_keyboard())
    elif action == "force_content":
        await query.answer("Отмечено. Используем контентный режим.")
        await query.edit_message_reply_markup(reply_markup=_build_main_keyboard())
    elif data.startswith("beta:preset:"):
        preset_id = data.split(":")[-1]
        await _handle_preset_choice(update, context, preset_id)
    elif data.startswith("beta:type:"):
        slug = data.split(":")[-1]
        if slug not in TYPE_LABELS:
            await query.answer("Неизвестный тип")
        else:
            beta_state = context.user_data.setdefault("beta", {})
            beta_state["manual_type"] = slug
            await query.answer(f"Тип выбран: {TYPE_LABELS[slug]}")
            header = compose_header(
                beta_state.get("router_payload", {}).get("content", {}).get("type_hint", "other"),
                beta_state.get("router_payload", {}).get("content", {}).get("type_confidence", 0.0) or 0.0,
                beta_state.get("manual_type"),
            )
            await query.edit_message_text(
                header,
                reply_markup=_build_main_keyboard(),
                parse_mode="Markdown",
            )
    else:
        await query.answer("Команда ещё не поддерживается", show_alert=False)


async def _show_preset_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    beta_state = context.user_data.setdefault("beta", {})
    type_hint = beta_state.get("manual_type") or beta_state.get("router_payload", {}).get("content", {}).get("type_hint", "other")
    presets = get_presets(type_hint)
    keyboard = [
        [InlineKeyboardButton(preset.title, callback_data=f"beta:preset:{preset.id}")]
        for preset in presets
    ]
    keyboard.append([InlineKeyboardButton("↩ Назад", callback_data="beta:act:back")])
    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))


async def _handle_preset_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, preset_id: str) -> None:
    query = update.callback_query
    beta_state = context.user_data.setdefault("beta", {})
    type_hint = beta_state.get("manual_type") or beta_state.get("router_payload", {}).get("content", {}).get("type_hint", "other")
    presets = {preset.id: preset for preset in get_presets(type_hint)}
    preset = presets.get(preset_id)
    if not preset:
        await query.answer("Пресет не найден", show_alert=True)
        return
    if preset.id.endswith('_free'):
        beta_state['awaiting_prompt'] = True
        beta_state['selected_preset'] = preset.id
        await query.answer("Напиши свой промпт текстом")
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("Введи запрос для ИИ обработки этой заметки.")
    else:
        await _save_note(update, context, status=NoteStatus.PROCESSED.value, preset=preset)


async def _save_note(update: Update, context: ContextTypes.DEFAULT_TYPE, status: str, preset: Optional[Preset]) -> None:
    query = update.callback_query
    beta_state = context.user_data.get("beta") or {}

    if beta_state.get("note_saved"):
        await query.answer("Заметка уже сохранена")
        return

    text = beta_state.get("original_text")
    router_payload = beta_state.get("router_payload") or {}
    if not text:
        await query.answer("Не нашёл текст заметки", show_alert=True)
        return

    await query.answer("Обрабатываю…")

    content_info = router_payload.get("content", {})
    type_hint = beta_state.get("manual_type") or content_info.get("type_hint") or "other"
    type_conf = content_info.get("type_confidence") or 0.0

    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        result = await _processor.process(
            user,
            text,
            type_hint,
            preset,
            status,
        )

        note = result['note']

        transcript_doc = beta_state.get('transcript_doc')
        if transcript_doc:
            note_service.update_note_metadata(note, links={'transcript_doc': transcript_doc})

        if status == NoteStatus.BACKLOG.value:
            note_service.schedule_backlog_reminder(user, note)

        beta_state["note_saved"] = note.id
        context.user_data["beta"] = beta_state
    except Exception as exc:
        logger.exception("Не удалось обработать заметку", extra={"error": str(exc)})
        await query.answer("Ошибка при обработке заметки", show_alert=True)
        return
    finally:
        db.close()

    status_text = {
        NoteStatus.PROCESSED.value: "обработана",
        NoteStatus.BACKLOG.value: "отложена в бэклог",
        NoteStatus.PROCESSED_RAW.value: "сохранена как сырой транскрипт",
    }.get(status, status)

    await query.edit_message_reply_markup(reply_markup=None)
    drive_info = result.get('drive') or {}
    raw_info = result.get('raw_drive') or {}
    errors = result.get('errors') or []
    transcript_doc = beta_state.get('transcript_doc')
    message = f"✅ Заметка {status_text}."
    if drive_info.get('webViewLink'):
        message += f" \nDrive: {drive_info['webViewLink']}"
    if raw_info.get('webViewLink') and raw_info.get('webViewLink') != drive_info.get('webViewLink'):
        message += f"\nRaw: {raw_info['webViewLink']}"
    elif raw_info.get('webViewLink') and not drive_info.get('webViewLink'):
        message += f" \nRaw: {raw_info['webViewLink']}"
    if transcript_doc:
        message += f"\nDoc: {transcript_doc}"
    if errors:
        if 'google_config_missing' in errors:
            message += "\n⚠️ Подключи Google Drive в личном кабинете, чтобы сохранять заметки в Drive."
        elif 'google_auth_required' in errors:
            message += "\n⚠️ Нужна авторизация Google Drive в личном кабинете."
        elif 'google_credentials_error' in errors:
            message += "\n⚠️ Не удалось получить доступ к Google. Попробуй переподключить Google Drive."
        elif 'google_drive_tree_failed' in errors:
            message += "\n⚠️ Не удалось открыть папки Google Drive. Попробуй позже."
        elif 'google_raw_upload_failed' in errors:
            message += "\n⚠️ Сырой файл не сохранился в Google Drive."
        elif 'google_inbox_missing' in errors:
            message += "\n⚠️ Папка Inbox в Google Drive недоступна."
        else:
            message += "\n⚠️ Google сервисы недоступны, файл сохранён локально. Попробуй позже."
    await query.message.reply_text(message)
    if 'beta' in context.user_data:
        context.user_data['beta']['transcript_doc'] = None

    record_event(
        'beta_note_saved',
        user_id=update.effective_user.id,
        status=status,
        has_drive=bool(drive_info.get('webViewLink')),
        errors=errors,
    )


async def _handle_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    action = data.split(":")[-1]
    beta_state = context.user_data.setdefault("beta", {})

    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        if action == "accept":
            backlog_notes = note_service.list_backlog(user, limit=1)
            if backlog_notes:
                note = backlog_notes[0]
                await query.answer("Погнали! Беру первую заметку из бэклога.")
                await process_text(update, context, note.text, source='backlog')
                return
            await query.answer("Бэклог пуст.")
        elif action == "tomorrow":
            reminders = (
                db.query(Reminder)
                .filter(Reminder.user_id == user.id, Reminder.sent_at.is_(None))
                .all()
            )
            for reminder in reminders:
                reminder.fire_ts += timedelta(days=1)
            db.commit()
            await query.answer("Напомню завтра.")
            await _reply(update, context, "Напомню завтра — как будешь готов, пиши! 😊")
        elif action == "snooze_week":
            reminders = (
                db.query(Reminder)
                .filter(Reminder.user_id == user.id, Reminder.sent_at.is_(None))
                .all()
            )
            for reminder in reminders:
                reminder.fire_ts += timedelta(days=7)
            db.commit()
            await query.answer("Напоминания отключены на неделю.")
            await _reply(update, context, "Окей, напоминания отключил на неделю. Возвращайся, когда будет удобно!")
        else:
            await query.answer("Неизвестное действие.")
    finally:
        db.close()
