#!/usr/bin/env python3

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler,
    ConversationHandler, ChatJoinRequestHandler
)

import os

from transkribator_modules.config import logger, BOT_TOKEN
from transkribator_modules.bot.commands import (
    start_command, help_command, status_command, raw_transcript_command,
    plans_command, stats_command, api_command, promo_codes_command, broadcast_command
)
from transkribator_modules.bot.handlers import (
    button_callback, handle_message, handle_chat_join_request, handle_my_chat_member
)
from transkribator_modules.bot.callbacks import handle_callback_query
from transkribator_modules.bot.payments import (
    handle_pre_checkout_query, handle_successful_payment, show_payment_plans,
    handle_payment_callback, ask_contact_or_email_wrapper, handle_contact, handle_email,
    ASK_CONTACT, ASK_EMAIL
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
    application.add_handler(CommandHandler("broadcast", broadcast_command))  # Админ-рассылка
    
    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # Обработчики для запроса контакта/email перед оплатой ЮKassa
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_contact_or_email_wrapper, pattern=r'^pay_yukassa_')],
        states={
            ASK_CONTACT: [MessageHandler(filters.CONTACT, handle_contact)],
            ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)]
        },
        fallbacks=[CallbackQueryHandler(handle_payment_callback)]
    )
    application.add_handler(conv_handler)
    
    # Обработчик «тяжёлых» сообщений (видео/аудио) перенесён в отдельную группу, 
    # чтобы команды вроде /start отвечали моментально и не стояли в очереди
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message), group=1)
    
    # Обработчики для групповых чатов
    application.add_handler(ChatJoinRequestHandler(handle_chat_join_request))
    
    # Обработчики для кнопок (новый обработчик имеет приоритет)
    application.add_handler(CallbackQueryHandler(handle_payment_callback))  # Платежные callback'ы
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 