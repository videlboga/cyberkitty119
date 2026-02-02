#!/usr/bin/env python3

import os
import socket
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, PreCheckoutQueryHandler,
    ApplicationHandlerStop,
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
    start_command,
    help_command,
    status_command,
    plans_command,
    stats_command,
    api_command,
    promo_codes_command,
    backlog_command,
    timezone_command,
)
from transkribator_modules.bot.handlers import (
    handle_message
)
from transkribator_modules.bot.callbacks import handle_callback_query
from transkribator_modules.bot.update_dedupe import should_process, should_process_message
from transkribator_modules.bot.payments import (
    handle_pre_checkout_query, handle_successful_payment, show_payment_plans
)
from transkribator_modules.db.database import init_database, engine
from sqlalchemy import text
from transkribator_modules.beta.reminders import schedule_jobs
from transkribator_modules.beta.drive_sync import schedule_drive_sync_jobs

def _acquire_singleton_lock() -> bool:
    """Acquire a cross-process singleton lock via PostgreSQL advisory lock.

    Returns True if the lock is acquired (this instance is the only consumer),
    False otherwise. For non-PostgreSQL backends, returns True.
    """
    try:
        backend = engine.url.get_backend_name()
    except Exception:
        backend = "unknown"

    if backend != "postgresql":
        # SQLite or others – no-op
        return True

    # Stable lock key. Allow override via env.
    key_env = os.getenv("BOT_SINGLETON_LOCK_KEY")
    try:
        key = int(key_env) if key_env else 1190119
    except Exception:
        key = 1190119

    try:
        with engine.connect() as conn:
            acquired = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar()
            conn.commit()
            return bool(acquired)
    except Exception as exc:
        logger.warning("Не удалось получить advisory lock", extra={"error": str(exc)})
        return True  # fail-open to avoid total outage


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

    # Instance identity for tracing duplicate consumers
    instance_id = f"{socket.gethostname()}:{os.getpid()}"

    # Ensure single polling consumer across processes/hosts
    if not _acquire_singleton_lock():
        logger.error("Другой экземпляр уже потребляет апдейты (advisory lock). Завершаем.", extra={"instance": instance_id})
        return

    if FEATURE_BETA_MODE:
        schedule_jobs(application)
        schedule_drive_sync_jobs(application)

    # Пред‑хук идемпотентности временно отключён полностью, чтобы исключить влияние на медиа

    # Специальный обработчик для медиа (явные фильтры), чтобы гарантировать маршрутизацию
    # Формируем фильтры для медиа без небезопасных фолбэков на filters.ALL
    media_core = (
        filters.PHOTO
        | filters.VOICE
        | filters.AUDIO
        | filters.VIDEO
        | filters.Document.ALL
    )
    # Добавим VIDEO_NOTE, только если он существует в текущей версии PTB
    if hasattr(filters, "VIDEO_NOTE"):
        media_core = media_core | getattr(filters, "VIDEO_NOTE")
    media_filters = media_core & ~filters.COMMAND
    application.add_handler(MessageHandler(media_filters, handle_message), group=0)

    # Обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("backlog", backlog_command))
    application.add_handler(CommandHandler("timezone", timezone_command))
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
    
    # Обработчик для всех типов сообщений, исключая уже обработанные медиа
    general_filters = (filters.ALL & ~filters.COMMAND) & ~media_filters
    application.add_handler(MessageHandler(general_filters, handle_message))
    
    # Обработчики для кнопок (оставляем только общий)
    application.add_handler(CallbackQueryHandler(handle_callback_query))

    # Запуск бота
    logger.info("Бот запущен и слушает сообщения...", extra={"instance": instance_id})
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main() 
