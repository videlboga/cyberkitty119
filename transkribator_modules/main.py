#!/usr/bin/env python3

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler
)

import os

from transkribator_modules.config import logger, BOT_TOKEN
from transkribator_modules.bot.commands import (
    start_command, help_command, status_command, raw_transcript_command,
    plans_command, stats_command, api_command, promo_codes_command
)
from transkribator_modules.bot.handlers import (
    button_callback, handle_message
)
from transkribator_modules.bot.callbacks import handle_callback_query
from transkribator_modules.bot.payments import (
    handle_pre_checkout_query, handle_successful_payment, show_payment_plans
)
from transkribator_modules.db.database import init_database

def main() -> None:
    """Главная функция для запуска бота."""
    logger.info("Запуск бота...")
    
    # Инициализируем базу данных
    try:
        init_database()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
    
    # Инициализация бота с поддержкой локального Bot API
    # Если переменная окружения TELEGRAM_API_URL задана, используем её в качестве base_url,
    # иначе обращаемся к стандартному https://api.telegram.org
    builder = ApplicationBuilder().token(BOT_TOKEN).read_timeout(300).connect_timeout(300)

    telegram_api_url = os.getenv("TELEGRAM_API_URL")
    if telegram_api_url:
        logger.info(f"Используем пользовательский TELEGRAM_API_URL: {telegram_api_url}")
        # При использовании локального Bot API (поднят с флагом --local)
        # обязательно указываем base_file_url и включаем local_mode,
        # чтобы библиотека не пыталась скачивать файлы через HTTP, а
        # пользовалась локальными путями (см. wiki PTB "Local Bot API Server").
        builder = (
            builder
            .base_url(telegram_api_url)
            .base_file_url(telegram_api_url.replace('/bot', '/file/bot'))
            .local_mode(True)
        )

    application = builder.build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("rawtranscript", raw_transcript_command))
    
    # Новые команды для монетизации
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("api", api_command))
    application.add_handler(CommandHandler("buy", show_payment_plans))  # Команда для покупки
    application.add_handler(CommandHandler("promo", promo_codes_command))  # Команда для промокодов
    
    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # Обработчик для всех типов сообщений
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    # Обработчики для кнопок (новый обработчик имеет приоритет)
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 