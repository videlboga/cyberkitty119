#!/usr/bin/env python3

"""
Скрипт для авторизации Pyrogram клиента, который будет использоваться
для скачивания больших видео из Telegram.
"""

import os
import logging
from pyrogram import Client
from dotenv import load_dotenv
from transkribator_modules.config import logger

# Загружаем переменные окружения
load_dotenv()

# Имя сессии
SESSION_NAME = 'pyro_worker'

# API ID и hash для Telegram API
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')

def main():
    """Основная функция для авторизации Pyrogram клиента."""
    logger.info("🚀 Запуск процесса авторизации для Pyrogram...")
    
    if not API_ID or not API_HASH:
        logger.error("❌ Не указаны TELEGRAM_API_ID или TELEGRAM_API_HASH в .env")
        print("Ошибка: Не указаны TELEGRAM_API_ID или TELEGRAM_API_HASH в .env")
        print("Получите их на https://my.telegram.org/apps и добавьте в .env файл:")
        print("TELEGRAM_API_ID=ваш_api_id")
        print("TELEGRAM_API_HASH=ваш_api_hash")
        return
    
    # Создаем Pyrogram клиент
    app = Client(
        SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    # Запускаем клиент для авторизации
    with app:
        me = app.get_me()
        logger.info(f"✅ Авторизация успешна! Вы вошли как {me.first_name} {me.last_name or ''} (@{me.username or 'без юзернейма'})")
        print(f"Авторизация успешна! Вы вошли как {me.first_name} {me.last_name or ''} (@{me.username or 'без юзернейма'})")
        print("Сессия сохранена в файле", f"{SESSION_NAME}.session")
        logger.info("ℹ️ Теперь вы можете запустить рабочий скрипт pyro_worker.py")

if __name__ == "__main__":
    main() 