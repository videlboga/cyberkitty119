#!/usr/bin/env python3

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler,
    ConversationHandler, ChatJoinRequestHandler
)

import os

from transkribator_modules.config import logger, BOT_TOKEN, TELEGRAM_API_URL
from transkribator_modules.bot.commands import (
    start_command
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
    
    # Инициализация бота
    builder = ApplicationBuilder().token(BOT_TOKEN).read_timeout(300).connect_timeout(300)
    
    # Если указан локальный API URL, используем его
    if TELEGRAM_API_URL:
        builder = builder.base_url(TELEGRAM_API_URL)
        logger.info(f"🚀 Использую локальный Telegram Bot API: {TELEGRAM_API_URL}")
    else:
        logger.info("🚀 Использую официальный Telegram Bot API")

    application = builder.build()

    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    
    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # Обработчики для запроса контакта/email перед оплатой ЮKassa
    # ВРЕМЕННО ОТКЛЮЧЕНО для отладки
    # conv_handler = ConversationHandler(
    #     entry_points=[CallbackQueryHandler(ask_contact_or_email_wrapper, pattern=r'^pay_yukassa_')],
    #     states={
    #         ASK_CONTACT: [MessageHandler(filters.CONTACT, handle_contact)],
    #         ASK_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email)]
    #     },
    #     fallbacks=[CallbackQueryHandler(handle_payment_callback)]
    # )
    # application.add_handler(conv_handler)
    
    # Обработчик «тяжёлых» сообщений (видео/аудио) перенесён в отдельную группу, 
    # чтобы команды вроде /start отвечали моментально и не стояли в очереди
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message), group=1)
    
    # Обработчики для групповых чатов
    application.add_handler(ChatJoinRequestHandler(handle_chat_join_request))
    # application.add_handler(MessageHandler(filters.StatusUpdate.MY_CHAT_MEMBER, handle_my_chat_member))
    
    # Обработчики для кнопок
    application.add_handler(CallbackQueryHandler(handle_callback_query))  # Основной обработчик
    application.add_handler(CallbackQueryHandler(button_callback))  # Резервный обработчик

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...")
    
    # Запускаем основной бот
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 