#!/usr/bin/env python3

"""
Модуль Pyrogram воркера для скачивания больших видео из Telegram.
Воркер работает как отдельный сервис, прослушивающий заданный чат и обрабатывающий команды от основного бота.
"""

import os
import sys
import asyncio
import logging
import re
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatAdminRequired

from transkribator_modules.config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH, BOT_TOKEN,
    PYROGRAM_WORKER_CHAT_ID, VIDEOS_DIR, logger
)

# Проверка наличия API идентификатора и хеша
if not TELEGRAM_API_ID or TELEGRAM_API_ID == 0:
    logger.error("❌ TELEGRAM_API_ID не задан в .env файле!")
    sys.exit(1)

if not TELEGRAM_API_HASH:
    logger.error("❌ TELEGRAM_API_HASH не задан в .env файле!")
    sys.exit(1)

# Получаем ID бота из токена
BOT_ID = BOT_TOKEN.split(':')[0] if BOT_TOKEN else ''
SESSION_NAME = "cyberkitty19_pyro_worker_new"

# Регулярные выражения для распознавания команд
PYRO_DOWNLOAD_PATTERN = re.compile(r'#pyro_download_(\d+)_(\d+)')

# Создаем клиент Pyrogram
app = Client(SESSION_NAME, api_id=TELEGRAM_API_ID, api_hash=TELEGRAM_API_HASH)

async def download_and_save_video(message, target_file):
    """Скачивает и сохраняет видео из сообщения Telegram."""
    try:
        logger.info(f"Начинаю скачивание видео в файл: {target_file}")
        
        # Создаем директорию, если она не существует
        target_file.parent.mkdir(exist_ok=True)
        
        # Скачиваем видео
        await message.download(file_name=str(target_file))
        
        # Проверяем, что файл существует и не пустой
        if target_file.exists() and target_file.stat().st_size > 0:
            logger.info(f"✅ Видео успешно загружено: {target_file} (размер: {target_file.stat().st_size} байт)")
            return True
        else:
            logger.error(f"❌ Файл пустой или не существует после загрузки: {target_file}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при скачивании видео: {e}")
        return False

# Фильтр для сообщений от нашего бота
def from_our_bot(_, __, message):
    """Фильтр для сообщений от нашего бота."""
    if not message.from_user:
        return False
    
    # Проверяем только ID пользователя (ID бота из токена)
    bot_user_id = BOT_TOKEN.split(':')[0] if BOT_TOKEN else ''
    return str(message.from_user.id) == bot_user_id

# Регистрируем пользовательский фильтр
bot_filter = filters.create(from_our_bot)

@app.on_message(filters.chat(PYROGRAM_WORKER_CHAT_ID))
async def handle_all_messages(client, message):
    """Обрабатывает все сообщения в релейном чате для отладки."""
    try:
        sender = message.from_user
        sender_info = f"@{sender.username}" if sender and sender.username else f"ID:{sender.id}" if sender else "Unknown"
        message_text = message.text or message.caption or ""
        
        logger.info(f"📩 Получено сообщение в релейном чате от {sender_info}: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
        
        # Проверяем, от нашего ли бота сообщение
        bot_user_id = BOT_TOKEN.split(':')[0] if BOT_TOKEN else ''
        is_from_bot = sender and str(sender.id) == bot_user_id
        
        logger.info(f"🤖 Сообщение от бота: {is_from_bot} (ожидаемый ID: {bot_user_id}, фактический ID: {sender.id if sender else 'None'})")
        
        if is_from_bot:
            await handle_bot_messages(client, message)
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке сообщения: {e}")

@app.on_message(bot_filter & filters.chat(PYROGRAM_WORKER_CHAT_ID))
async def handle_bot_messages(client, message):
    """Обрабатывает сообщения от бота в релейном чате."""
    try:
        sender = message.from_user
        sender_info = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
        message_text = message.text or message.caption or ""
        
        logger.info(f"📩 Получено сообщение от {sender_info}: {message_text[:50]}{'...' if len(message_text) > 50 else ''}")
        
        # Проверяем наличие команды скачивания в тексте или подписи
        pyro_match = PYRO_DOWNLOAD_PATTERN.search(message_text)
        
        # Обработка команды скачивания видео
        if pyro_match:
            chat_id, message_id = pyro_match.groups()
            logger.info(f"🎬 Обнаружен запрос на скачивание видео: chat_id={chat_id}, message_id={message_id}")
            
            # Проверяем наличие видео в сообщении
            if message.video:
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                
                # Скачиваем видео
                success = await download_and_save_video(message, video_path)
                
                # Отправляем сообщение боту о результате
                if success:
                    await client.send_message(PYROGRAM_WORKER_CHAT_ID, f"#pyro_downloaded_{chat_id}_{message_id}")
                else:
                    await client.send_message(PYROGRAM_WORKER_CHAT_ID, f"#pyro_download_failed_{chat_id}_{message_id}")
            else:
                logger.warning(f"⚠️ Команда на скачивание получена, но в сообщении нет видео")
        else:
            logger.debug(f"ℹ️ Сообщение не содержит известной команды, игнорирую")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке сообщения: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def main():
    """Основная функция для запуска Pyrogram worker'а."""
    logger.info("🚀 Запуск Pyrogram worker'а...")
    
    # Настраиваем специальное логирование для этого модуля
    pyro_logger = logging.getLogger('pyro_worker')
    pyro_handler = logging.FileHandler("pyro_worker.log")
    pyro_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    pyro_logger.addHandler(pyro_handler)
    pyro_logger.setLevel(logging.INFO)
    
    async with app:
        me = await app.get_me()
        pyro_logger.info(f"✅ Pyrogram worker запущен от имени {me.first_name} {me.last_name or ''} (@{me.username or 'без юзернейма'})")
        pyro_logger.info(f"👀 Жду видео-сообщения от бота с ID {BOT_ID} в чате {PYROGRAM_WORKER_CHAT_ID}...")
        
        # Поддерживаем клиент активным
        await asyncio.Future()

if __name__ == "__main__":
    try:
        app.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Получено прерывание с клавиатуры. Завершаю работу...")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        sys.exit(1) 