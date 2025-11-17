#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import logging
import telebot
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('broadcast.log')
    ]
)
logger = logging.getLogger('broadcast')

# Загрузка переменных окружения
logger.info("Загрузка переменных окружения...")
load_dotenv()

# Получение API-ключа Telegram
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_TOKEN не найден в файле .env")
    sys.exit(1)

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Текст сообщения для рассылки
broadcast_text = "Мяу! Я снова здесь. Давайте видосы, я помогу их разобрать!"

# Путь к файлу с ID пользователей
USERS_FILE = 'user_ids.txt'

def get_user_ids():
    """Получает список ID пользователей из файла."""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                user_ids = [line.strip() for line in f if line.strip()]
            return user_ids
        else:
            logger.warning(f"Файл с ID пользователей не найден: {USERS_FILE}")
            return []
    except Exception as e:
        logger.error(f"Ошибка при чтении файла пользователей: {e}")
        return []

def send_broadcast_message():
    """Отправляет сообщение всем пользователям."""
    user_ids = get_user_ids()
    
    if not user_ids:
        logger.warning("Список пользователей пуст. Рассылка не может быть выполнена.")
        return False
    
    success_count = 0
    failed_count = 0
    
    logger.info(f"Начинаю рассылку {len(user_ids)} пользователям...")
    
    for user_id in user_ids:
        try:
            user_id = int(user_id)
            bot.send_message(user_id, broadcast_text)
            success_count += 1
            logger.info(f"Сообщение успешно отправлено пользователю {user_id}")
        except Exception as e:
            failed_count += 1
            logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
    
    logger.info(f"Рассылка завершена. Успешно: {success_count}, ошибок: {failed_count}")
    return True

if __name__ == '__main__':
    try:
        logger.info("Запуск рассылки...")
        send_broadcast_message()
        logger.info("Скрипт рассылки завершил работу")
    except Exception as e:
        logger.error(f"Произошла непредвиденная ошибка: {e}") 