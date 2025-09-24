"""Точка входа в бета-режим: дальнейшая маршрутизация сообщений."""

import asyncio
import datetime
from textwrap import wrap

from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from ..router import route_message
from .content_flow import show_processing_menu
from .command_flow import show_command_confirmation, handle_manual_form_message
from ..presets import get_presets
from ..content_processor import ContentProcessor
from transkribator_modules.db.database import SessionLocal, UserService
from transkribator_modules.db.models import NoteStatus
from transkribator_modules.google_api import GoogleCredentialService, ensure_tree, create_doc

_content_processor = ContentProcessor()


def _reply_target(update: Update):
    if update.message:
        return update.message
    if update.callback_query:
        return update.callback_query.message
    return None


async def _reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    target = _reply_target(update)
    if target:
        return await target.reply_text(text, **kwargs)
    user = update.effective_user
    if user:
        return await context.bot.send_message(chat_id=user.id, text=text, **kwargs)
    return None


async def process_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, source: str = 'message') -> None:
    user = update.effective_user
    if not text or not text.strip():
        await _reply(update, context, "Не нашёл текста в сообщении. Попробуй ещё раз.")
        return

    logger.info(
        "Beta routing text",
        extra={"user_id": user.id if user else None, "source": source, "length": len(text)},
    )

    transcript_link = None
    if source in {'audio', 'video', 'voice', 'media'}:
        transcript_link = await _send_transcript_preview(update, context, text)

    router_result = await route_message({"text": text, "metadata": {"user_id": user.id if user else None, "source": source}})

    context.user_data["beta"] = {
        "original_text": text,
        "router_payload": router_result.payload.model_dump(),
        "manual_type": None,
        "note_saved": None,
        "manual_form": None,
        "awaiting_prompt": False,
        "source": source,
        "transcript_doc": transcript_link,
    }

    if router_result.error and router_result.payload.mode == "content" and router_result.payload.content.type_hint == "other":
        logger.warning("Router вернулся с ошибкой", extra={"error": router_result.error})

    if router_result.mode == "command":
        await show_command_confirmation(update, context, router_result.payload.model_dump())
    else:
        await show_processing_menu(update, context, router_result)


async def handle_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сообщений в бета-режиме (пока заглушка)."""

    user = update.effective_user
    logger.info(
        "Обработка сообщения в бета-режиме",
        extra={"user_id": user.id if user else None, "has_message": bool(update.message)},
    )

    message = update.message
    if not message:
        logger.info("Нет текстового сообщения для бета-обработки")
        return

    beta_state = context.user_data.get('beta') or {}

    if beta_state.get('awaiting_prompt') and message.text:
        await _handle_free_prompt(update, context, beta_state, message.text)
        return

    manual_form_state = beta_state.get('manual_form')
    if manual_form_state and message.text:
        handled = await handle_manual_form_message(update, context, message.text)
        if handled:
            return

    text = message.text or message.caption
    await process_text(update, context, text or "", source='message')


async def _send_transcript_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> str | None:
    preview = (text or '').strip()
    if not preview:
        return None

    signature = '\n\n@CyberKitty19_bot'
    full_text = preview if preview.endswith(signature.strip()) else preview + signature

    limit = 3500
    if len(full_text) <= limit:
        await _reply(update, context, full_text)
        return None

    link = await _create_transcript_doc(update, full_text)
    if link:
        await _reply(update, context, f"📝 Полная транскрипция: {link}")
        snippet = preview[:limit].rstrip() + '…'
        await _reply(update, context, snippet)
        return link

    for chunk in wrap(full_text, width=limit):
        await _reply(update, context, chunk)
    return None


async def _create_transcript_doc(update: Update, text: str) -> str | None:
    user = update.effective_user
    if not user:
        return None

    db = SessionLocal()
    try:
        user_service = UserService(db)
        google_service = GoogleCredentialService(db)
        db_user = user_service.get_or_create_user(
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        try:
            credentials = google_service.get_credentials(db_user.id)
        except Exception as exc:
            logger.warning('Не удалось получить Google креды для транскрипта', extra={'error': str(exc)})
            return None
        if not credentials:
            return None

        try:
            tree = ensure_tree(credentials, user.username or str(user.id))
        except Exception as exc:
            logger.warning('ensure_tree для транскрипта не удался', extra={'error': str(exc)})
            return None

        folder_id = tree.get('Inbox') or tree.get('user')
        if not folder_id:
            return None

        title = f"Transcript {datetime.datetime.utcnow():%Y-%m-%d %H:%M}".strip()
        blocks = [block for block in text.split('\n\n') if block.strip()] or [text]
        try:
            doc = await asyncio.to_thread(create_doc, credentials, folder_id, title, blocks)
        except Exception as exc:
            logger.warning('Создание Google Doc для транскрипта не удалось', extra={'error': str(exc)})
            return None
        return doc.get('link')
    finally:
        db.close()


async def _handle_free_prompt(update, context, beta_state, prompt: str) -> None:
    user_id = update.effective_user.id
    text = beta_state.get('original_text')
    if not text:
        await _reply(update, context, "Заметка не найдена для обработки.")
        return

    type_hint = beta_state.get('manual_type') or beta_state.get('router_payload', {}).get('content', {}).get('type_hint', 'other')
    preset_id = beta_state.get('selected_preset')
    presets = {preset.id: preset for preset in get_presets(type_hint)}
    preset = presets.get(preset_id)

    if not preset:
        await _reply(update, context, "Пресет не найден, попробуй снова.")
        beta_state['awaiting_prompt'] = False
        beta_state['selected_preset'] = None
        return

    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=update.effective_user.id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name,
        )

        result = await _content_processor.process(
            user,
            text,
            type_hint,
            preset,
            NoteStatus.PROCESSED.value,
            custom_prompt=prompt,
        )

        note = result['note']
        await _reply(update, context, "✅ Заметка обработана по свободному промпту!")
        beta_state['note_saved'] = note.id
    except Exception as exc:
        logger.error("Свободный промпт не выполнен", extra={"error": str(exc)})
        await _reply(update, context, "Не удалось обработать запрос. Попробуй позже.")
    finally:
        beta_state['awaiting_prompt'] = False
        beta_state['selected_preset'] = None
        context.user_data['beta'] = beta_state
        db.close()
