from __future__ import annotations

from typing import Optional
from textwrap import wrap

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import NoteStatus
from transkribator_modules.search import IndexService
from transkribator_modules.google_api import GoogleCredentialService, ensure_tree, create_doc, upload_markdown
from transkribator_modules.beta.presets import get_preset_by_id
from transkribator_modules.beta.content_processor import ContentProcessor


_index = IndexService()
_content = ContentProcessor()


def _make_keyboard(note_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💾 Сохранить", callback_data=f"agent:save_raw:{note_id}"),
                InlineKeyboardButton("🕓 Отложить", callback_data=f"agent:backlog:{note_id}"),
            ]
        ]
    )


async def ingest_and_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, source: str = 'media') -> None:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)

        tg_user = update.effective_user
        user = user_service.get_or_create_user(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )

        note = note_service.create_note(
            user=user,
            text=text,
            source=source,
            status=NoteStatus.INGESTED.value,
        )

        link = None
        try:
            google = GoogleCredentialService(db)
            credentials = google.get_credentials(user.id)
            if credentials:
                tree = ensure_tree(credentials, user.username or str(user.telegram_id))
                target_folder = tree.get('Inbox')
                if target_folder:
                    title = f"Transcript {note.id}"
                    blocks = [blk for blk in wrap(text, width=4000)] or [text]
                    doc = create_doc(credentials, target_folder, title, blocks)
                    link = (doc or {}).get('link')
                    if link:
                        note_service.update_note_metadata(note, raw_link=link, links={'transcript_doc': link})
        except Exception as exc:  # noqa: BLE001
            logger.info("Transcript doc creation skipped", extra={"error": str(exc)})

        header = "Готово. "
        if link:
            header += f"Транскрипт: {link}\n"
        else:
            header += "Транскрипт готов.\n"
        header += "Что сделать?\nПримеры: «протокол», «разбей на задачи», «сделай пост», «сохрани в Meetings»."

        message = update.message or (update.callback_query.message if update.callback_query else None)
        if message:
            await message.reply_text(header, reply_markup=_make_keyboard(note.id))
        else:
            await context.bot.send_message(chat_id=user.telegram_id, text=header, reply_markup=_make_keyboard(note.id))

        context.user_data['agent_active_note_id'] = note.id
        context.user_data['agent_waiting_instruction'] = True
    finally:
        db.close()


async def handle_instruction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    note_id = context.user_data.get('agent_active_note_id')
    if not note_id:
        return

    text = (update.message.text or '').strip()
    if not text:
        return

    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        tg_user = update.effective_user
        user = user_service.get_or_create_user(telegram_id=tg_user.id)
        note = note_service.get_note(note_id)
        if not note or note.user_id != user.id:
            return

        preset = get_preset_by_id('summary.tldr.3')
        result = await _content.process(
            user,
            note.text,
            note.type_hint or 'other',
            preset,
            NoteStatus.DRAFT.value,
        )

        snippet = (result.get('rendered_output') or '').strip()
        if len(snippet) > 1200:
            snippet = snippet[:1197] + '…'
        version_label = (note.current_version or 0) + 1
        await update.message.reply_text(
            f"Черновик v{version_label} готов. Что правим или делаем дальше?\n\n{snippet}",
            reply_markup=_make_keyboard(note.id),
        )
        context.user_data['agent_waiting_instruction'] = True
    except Exception as exc:  # noqa: BLE001
        logger.error('Instruction handling failed', extra={'error': str(exc)})
        await update.message.reply_text('Не вышло, попробуем ещё раз или другим способом?')
    finally:
        db.close()


async def save_raw_and_index(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int) -> str:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        user = user_service.get_or_create_user(telegram_id=update.effective_user.id)
        note = note_service.get_note(note_id)
        if not note or note.user_id != user.id:
            return "❌ Заметка не найдена"

        drive_url = None
        try:
            google = GoogleCredentialService(db)
            credentials = google.get_credentials(user.id)
            if credentials:
                tree = ensure_tree(credentials, user.username or str(user.telegram_id))
                inbox = tree.get('Inbox')
                if inbox:
                    title = f"{note.type_hint or 'note'}_{note.id}.md"
                    content = (note.text or '').strip()
                    file = upload_markdown(credentials, inbox, title, content)
                    drive_url = (file or {}).get('webViewLink')
                    links = {'drive_url': drive_url}
                    if note.raw_link:
                        links['transcript_doc'] = note.raw_link
                    note_service.update_note_metadata(note, links=links)
        except Exception as exc:  # noqa: BLE001
            logger.info('Raw upload skipped', extra={'error': str(exc)})

        _index.add(note.id, user.id, note.text or '', summary=note.summary or '', type_hint=note.type_hint or 'other')
        note_service.update_status(note, NoteStatus.APPROVED.value)
        context.user_data.pop('agent_waiting_instruction', None)
        context.user_data.pop('agent_active_note_id', None)

        if drive_url:
            return f"Сохранил в Inbox. Index обновлён. Готово.\n{drive_url}"
        return "Сохранил. Index обновлён. Готово."
    finally:
        db.close()


async def backlog_note(update: Update, context: ContextTypes.DEFAULT_TYPE, note_id: int) -> str:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        user = user_service.get_or_create_user(telegram_id=update.effective_user.id)
        note = note_service.get_note(note_id)
        if not note or note.user_id != user.id:
            return "❌ Заметка не найдена"
        note_service.update_status(note, NoteStatus.BACKLOG.value)
        note_service.schedule_backlog_reminder(user, note)
        context.user_data.pop('agent_waiting_instruction', None)
        context.user_data.pop('agent_active_note_id', None)
        return "Отложил в бэклог. Напомню вечером."
    finally:
        db.close()
