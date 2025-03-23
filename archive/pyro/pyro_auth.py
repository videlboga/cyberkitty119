#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
from pyrogram import Client

# Загружаем переменные окружения
load_dotenv()

# Получаем учетные данные API из .env
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
SESSION_NAME = 'pyro_worker'

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция для авторизации Pyrogram клиента."""
    logger.info("🚀 Запуск процесса авторизации для Pyrogram...")
    
    if not API_ID or API_ID == 0 or not API_HASH:
        logger.error("❌ API_ID или API_HASH не найдены в .env файле!")
        logger.info("ℹ️ Убедитесь, что в файле .env есть строки:")
        logger.info("TELEGRAM_API_ID=your_api_id")
        logger.info("TELEGRAM_API_HASH=your_api_hash")
        sys.exit(1)
    
    # Создаем Pyrogram клиент
    app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)
    
    # Запускаем авторизацию
    async with app:
        me = await app.get_me()
        logger.info(f"✅ Авторизация успешна! Вы вошли как {me.first_name} {me.last_name or ''} (@{me.username or 'без юзернейма'})")
        logger.info(f"☎️ Номер телефона: {me.phone_number}")
        logger.info(f"🆔 ID пользователя: {me.id}")
        
        # Проверяем, есть ли файл сессии
        session_file = Path(f"{SESSION_NAME}.session")
        if session_file.exists():
            logger.info(f"📁 Файл сессии создан: {session_file.absolute()}")
            logger.info("ℹ️ Теперь вы можете запустить pyro_worker.py")
        else:
            logger.error(f"❌ Не удалось найти файл сессии: {session_file.absolute()}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Процесс авторизации прерван пользователем.")
    except Exception as e:
        logger.error(f"💥 Ошибка при авторизации: {e}")
        sys.exit(1) 