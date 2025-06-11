#!/usr/bin/env python3
"""
CyberKitty Transkribator - Telegram Bot API Server Version
Telegram бот для транскрипции видео и аудио файлов с поддержкой больших файлов.
"""

import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from transkribator_modules.config import (
    BOT_TOKEN, USE_LOCAL_BOT_API, LOCAL_BOT_API_URL, logger
)
from transkribator_modules.bot.handlers import (
    start_command, help_command, status_command,
    handle_document, handle_audio, handle_video
)

def create_application() -> Application:
    """Создает и настраивает Telegram Application."""
    
    # Создаем Application Builder
    builder = Application.builder().token(BOT_TOKEN)
    
    # Если используется локальный Bot API Server
    if USE_LOCAL_BOT_API:
        logger.info(f"🚀 Настройка локального Bot API Server: {LOCAL_BOT_API_URL}")
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot")
        builder = builder.base_file_url(f"{LOCAL_BOT_API_URL}/file/bot")
    
    # Создаем приложение
    application = builder.build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    
    # Регистрируем обработчики файлов
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    logger.info("✅ Все обработчики зарегистрированы")
    return application

async def main():
    """Главная функция для запуска бота."""
    logger.info("🚀 Запуск CyberKitty Transkribator (Telegram Bot API Server)")
    
    try:
        # Создаем приложение
        application = create_application()
        
        # Запускаем бота
        logger.info("🤖 Бот запускается...")
        await application.run_polling(
            drop_pending_updates=True,
            allowed_updates=['message', 'callback_query']
        )
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        raise

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        exit(1) 