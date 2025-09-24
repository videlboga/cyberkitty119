#!/usr/bin/env python3

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler
)
from telegram.request import HTTPXRequest

from transkribator_modules.config import (
    logger,
    BOT_TOKEN,
    USE_LOCAL_BOT_API,
    LOCAL_BOT_API_URL,
    FEATURE_BETA_MODE,
)
from transkribator_modules.bot.commands import (
    start_command, help_command, status_command,
    plans_command, stats_command, api_command, promo_codes_command
)
from transkribator_modules.bot.handlers import (
    handle_message
)
from transkribator_modules.bot.callbacks import handle_callback_query
from transkribator_modules.bot.payments import (
    handle_pre_checkout_query, handle_successful_payment, show_payment_plans
)
from transkribator_modules.db.database import init_database
from transkribator_modules.beta.reminders import schedule_jobs

def main() -> None:
    """Главная функция для запуска бота."""
    logger.info("Запуск бота...")
    
    # Инициализируем базу данных
    try:
        init_database()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
    
    # Создаем HTTP request с увеличенными таймаутами для больших файлов
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=1800,  # 30 минут для чтения
        write_timeout=1800,  # 30 минут для записи
        connect_timeout=60,  # 1 минута для подключения
        pool_timeout=60      # 1 минута для получения соединения из пула
    )
    
    # Инициализация бота с поддержкой Bot API Server
    builder = ApplicationBuilder().token(BOT_TOKEN).request(request)
    
    # Если используется локальный Bot API Server
    if USE_LOCAL_BOT_API:
        logger.info(f"🚀 Настройка локального Bot API Server: {LOCAL_BOT_API_URL}")
        builder = builder.base_url(f"{LOCAL_BOT_API_URL}/bot")
        builder = builder.base_file_url(f"{LOCAL_BOT_API_URL}/file/bot")
    
    application = builder.build()

    if FEATURE_BETA_MODE:
        schedule_jobs(application)

    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    # Убрали сырой вывод по кнопке/команде
    
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
    
    # Обработчики для кнопок (оставляем только общий)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 
