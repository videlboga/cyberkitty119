#!/usr/bin/env python3

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from telethon.sync import TelegramClient

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Получаем учетные данные API
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
TELEGRAM_PHONE_NUMBER = os.getenv('TELEGRAM_PHONE_NUMBER', '')
SESSION_FILE = 'telethon_worker.session'

def authorize_telethon():
    """Функция для авторизации клиента Telethon."""
    logger.info("Запуск процесса авторизации Telethon клиента...")
    
    # Создаем клиент Telegram
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    
    # Подключаемся к Telegram
    client.connect()
    
    # Проверяем авторизацию
    if client.is_user_authorized():
        logger.info("Пользователь уже авторизован!")
        client.disconnect()
        return True
    
    # Процесс авторизации
    logger.info("Запрашиваем код авторизации...")
    client.send_code_request(TELEGRAM_PHONE_NUMBER)
    
    # Запрашиваем код у пользователя
    code = input('Введите код авторизации, отправленный на ваш телефон: ')
    
    try:
        # Авторизуемся
        client.sign_in(TELEGRAM_PHONE_NUMBER, code)
        logger.info("Авторизация успешна!")
        
        # Получаем информацию о пользователе
        me = client.get_me()
        logger.info(f"Вы авторизованы как {me.first_name} {me.last_name} (@{me.username})")
        
        client.disconnect()
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при авторизации: {e}")
        client.disconnect()
        return False

if __name__ == "__main__":
    # Запускаем процесс авторизации
    if authorize_telethon():
        logger.info(f"Файл сессии {SESSION_FILE} успешно создан")
        logger.info("Теперь вы можете запустить бота и телетон-воркер")
    else:
        logger.error("Не удалось авторизоваться. Пожалуйста, попробуйте снова.") 