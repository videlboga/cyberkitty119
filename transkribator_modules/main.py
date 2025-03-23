#!/usr/bin/env python3

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)

from transkribator_modules.config import logger, BOT_TOKEN
from transkribator_modules.bot.commands import (
    start_command, help_command, status_command, raw_transcript_command
)
from transkribator_modules.bot.handlers import (
    button_callback, handle_message
)

def main() -> None:
    """Главная функция для запуска бота."""
    logger.info("Запуск бота...")
    
    # Инициализация бота
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("rawtranscript", raw_transcript_command))
    
    # Обработчик для всех типов сообщений
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    # Обработчик для кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 