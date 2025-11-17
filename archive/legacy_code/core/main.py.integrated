#!/usr/bin/env python3
"""
CyberKitty Transkribator - Telegram Bot API Server Version
Telegram бот для транскрипции видео и аудио файлов с поддержкой больших файлов.
Интегрированная версия с монетизацией.
"""

import asyncio
import signal
import sys
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, PreCheckoutQueryHandler
)
from telegram.request import HTTPXRequest
from transkribator_modules.config import (
    BOT_TOKEN, USE_LOCAL_BOT_API, LOCAL_BOT_API_URL, logger
)

# Импорты команд
from transkribator_modules.bot.commands import (
    start_command, help_command, status_command, raw_transcript_command,
    plans_command, stats_command, api_command, promo_codes_command
)

# Импорты обработчиков
from transkribator_modules.bot.handlers import (
    button_callback, handle_message, handle_document, handle_audio, handle_video
)

# Импорты для монетизации
from transkribator_modules.bot.callbacks import handle_callback_query
from transkribator_modules.bot.payments import (
    handle_pre_checkout_query, handle_successful_payment, show_payment_plans
)

# Импорт базы данных
from transkribator_modules.db.database import init_database

def create_application() -> Application:
    """Создает и настраивает Telegram Application."""
    
    # Инициализируем базу данных
    try:
        init_database()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка при инициализации базы данных: {e}")
    
    # Создаем HTTP request с увеличенными таймаутами для больших файлов
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=1800,  # 30 минут для чтения
        write_timeout=1800,  # 30 минут для записи
        connect_timeout=60,  # 1 минута для подключения
        pool_timeout=60      # 1 минута для получения соединения из пула
    )
    
    # Создаем Application Builder
    builder = Application.builder().token(BOT_TOKEN).request(request)
    
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
    application.add_handler(CommandHandler("rawtranscript", raw_transcript_command))
    
    # Команды для монетизации
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("api", api_command))
    application.add_handler(CommandHandler("buy", show_payment_plans))
    application.add_handler(CommandHandler("promo", promo_codes_command))
    
    # Обработчики платежей
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # Регистрируем обработчики файлов
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    
    # Обработчик для всех типов сообщений (должен быть последним)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    
    # Обработчики для кнопок
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    logger.info("✅ Все обработчики зарегистрированы")
    return application

async def main():
    """Главная асинхронная функция для запуска бота."""
    logger.info("🚀 Запуск CyberKitty Transkribator (Telegram Bot API Server)")
    
    # Создаем приложение
    application = create_application()
    
    # Настраиваем обработку сигналов для graceful shutdown
    stop_signals = (signal.SIGTERM, signal.SIGINT)
    for sig in stop_signals:
        signal.signal(sig, lambda s, f: asyncio.create_task(shutdown(application)))
    
    try:
        # Инициализируем приложение
        await application.initialize()
        
        # Запускаем бота
        logger.info("🤖 Бот запускается...")
        await application.start()
        
        # Начинаем polling
        await application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
        logger.info("✅ Бот успешно запущен и работает")
        
        # Ждем завершения
        while True:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        raise
    finally:
        await shutdown(application)

async def shutdown(application: Application):
    """Корректное завершение работы бота."""
    logger.info("🛑 Начинается завершение работы бота...")
    
    try:
        # Останавливаем updater
        if application.updater and application.updater.running:
            await application.updater.stop()
            logger.info("✅ Updater остановлен")
        
        # Останавливаем приложение
        if application.running:
            await application.stop()
            logger.info("✅ Приложение остановлено")
        
        # Завершаем приложение
        await application.shutdown()
        logger.info("✅ Ресурсы освобождены")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при завершении работы: {e}")
    
    # Выходим из программы
    logger.info("👋 Бот успешно завершил работу")
    sys.exit(0)

def run_bot():
    """Запуск бота с правильным управлением event loop."""
    try:
        # Проверяем, есть ли уже запущенный event loop
        try:
            loop = asyncio.get_running_loop()
            logger.warning("⚠️ Обнаружен запущенный event loop, создаем новый")
            # Если есть запущенный loop, создаем новый в отдельном потоке
            import threading
            
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(main())
                new_loop.close()
            
            thread = threading.Thread(target=run_in_thread)
            thread.start()
            thread.join()
            
        except RuntimeError:
            # Нет запущенного loop, можем запускать обычным способом
            asyncio.run(main())
            
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    run_bot() 