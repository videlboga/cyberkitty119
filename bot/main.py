#!/usr/bin/env python3
"""
CyberKitty Transkribator Bot — чистый перезапуск.

Логика:
1. /start — приветствие
2. Файл (аудио / видео / voice / document) → скачать через локальный Bot API
   → положить в media/incoming/ → поставить задачу на воркер (ProcessingJob)
3. Polling прогресса из БД → редактировать одно «живое» сообщение
4. Готово → отправить файл с транскрипцией
"""

import logging
import os
import sys
from pathlib import Path

# Корень проекта → чтобы импортировались transkribator_modules и transcribe_client
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from bot.config import (
    BOT_TOKEN,
    LOCAL_BOT_API_URL,
    LOCAL_BOT_FILE_API_URL,
    USE_LOCAL_BOT_API,
    MEDIA_INCOMING_DIR,
    logger,
)
from bot.handlers import (
    handle_media_file,
    handle_menu_action,
    handle_note_qa_callback,
    handle_note_qa_message,
    handle_start,
)

# ─────────────────────────────────────────────────────────────────────────────


def build_app() -> Application:
    """Собрать Application с настроенным HTTP-транспортом."""
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=1800,
        write_timeout=1800,
        connect_timeout=60,
        pool_timeout=60,
    )
    builder = ApplicationBuilder().token(BOT_TOKEN).request(request)

    if USE_LOCAL_BOT_API:
        logger.info("Используется локальный Bot API Server: %s", LOCAL_BOT_API_URL)
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot")
        builder = builder.base_file_url(f"{LOCAL_BOT_FILE_API_URL}/file/bot")

    return builder.build()


def register_handlers(app: Application) -> None:
    """Регистрировать обработчики."""

    # Команды
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_start))

    # Медиа: аудио, видео, голосовые, видеосообщения, документы
    media_filter = (
        filters.AUDIO
        | filters.VOICE
        | filters.VIDEO
        | filters.Document.ALL
    )
    if hasattr(filters, "VIDEO_NOTE"):
        media_filter = media_filter | getattr(filters, "VIDEO_NOTE")
    media_filter = media_filter & ~filters.COMMAND

    app.add_handler(MessageHandler(media_filter, handle_media_file))

    # Чат с заметкой
    app.add_handler(CallbackQueryHandler(handle_note_qa_callback, pattern=r"^noteqa:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_note_qa_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_action, block=False))


def main() -> None:
    logger.info("Запускаю бот...")
    MEDIA_INCOMING_DIR.mkdir(parents=True, exist_ok=True)

    app = build_app()
    register_handlers(app)

    logger.info("🤖 Бот инициализирован. Запускаю polling...")
    logger.info(f"📲 Используем токен: {BOT_TOKEN[:10]}...")
    logger.info(f"📡 Локальный API: {USE_LOCAL_BOT_API}")
    logger.info(f"📋 Обработчики зарегистрированы: {len(app.handlers)}")
    
    # Включим DEBUG логирование для telegram
    logging.getLogger("telegram").setLevel(logging.DEBUG)
    logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
