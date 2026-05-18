#!/usr/bin/env python3
"""
Тестовый бот с использованием локального telegram-bot-api сервера.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(message)s",
)
logger = logging.getLogger("test_bot_local")

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        BOT_TOKEN = os.environ["BOT_TOKEN"]
    except Exception as e:
        logger.error(f"Не могу загрузить BOT_TOKEN: {e}")
        sys.exit(1)

logger.info(f"✓ BOT_TOKEN загружен: {BOT_TOKEN[:10]}...")

# Используем локальный telegram-bot-api сервер
LOCAL_BOT_API_URL = os.getenv("LOCAL_BOT_API_URL", "http://localhost:8081")
logger.info(f"📡 Используем локальный API: {LOCAL_BOT_API_URL}")


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик /start"""
    user = update.message.from_user
    logger.info(f"👤 /start от {user.id} ({user.first_name})")
    
    text = f"Привет, {user.first_name}! 👋\n\nЭто тестовый бот с локальным API.\nПопробуй отправить текст."
    await update.message.reply_text(text)
    logger.info(f"✅ Ответ отправлен {user.id}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик текстовых сообщений"""
    user = update.message.from_user
    text = update.message.text
    logger.info(f"💬 Текст от {user.id}: {text[:50]}")
    
    reply = f"Ты написал: {text}\n\nЯ получил твое сообщение! ✓"
    await update.message.reply_text(reply)
    logger.info(f"✅ Ответ отправлен {user.id}")


async def post_init(app: Application) -> None:
    """Вызывается после инициализации"""
    logger.info("🚀 Бот инициализирован!")
    try:
        me = await app.bot.get_me()
        logger.info(f"✓ getMe успешно: {me.first_name} ({me.username})")
    except Exception as e:
        logger.error(f"❌ getMe ошибка: {e}")


async def on_error(update: object, context) -> None:
    """Обработчик ошибок"""
    logger.error(f"❌ Ошибка: {context.error}", exc_info=context.error)


def main() -> None:
    logger.info("=" * 60)
    logger.info("🤖 ЗАПУСК БОТА С ЛОКАЛЬНЫМ API")
    logger.info("=" * 60)
    
    # Создаём приложение с локальным API
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=120,
        write_timeout=120,
        connect_timeout=30,
        pool_timeout=30,
    )
    
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .base_url(f"{LOCAL_BOT_API_URL}/bot")
        .base_file_url(f"{LOCAL_BOT_API_URL}/file/bot")
        .post_init(post_init)
        .build()
    )
    
    # Обработчики
    logger.info("📝 Регистрирую обработчики...")
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    
    logger.info("✓ Обработчики зарегистрированы")
    logger.info("🔄 Запускаю polling...")
    logger.info("=" * 60)
    logger.info("Жду сообщений от пользователей...")
    logger.info("=" * 60)
    
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
