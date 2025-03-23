#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
import re
from pathlib import Path
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ChatAdminRequired

# Загружаем переменные окружения
load_dotenv()

# Получаем учетные данные API
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_ID = os.getenv('BOT_ID', '')
TELETHON_WORKER_CHAT_ID = int(os.getenv('TELETHON_WORKER_CHAT_ID', '0'))
SESSION_NAME = 'pyro_worker'

# Пути для файлов
BASE_DIR = Path(__file__).resolve().parent
VIDEOS_DIR = BASE_DIR / "videos"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTIONS_DIR = BASE_DIR / "transcriptions"

# Создаем директории, если они не существуют
VIDEOS_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("pyro_worker.log")
    ]
)
logger = logging.getLogger(__name__)

# Регулярные выражения для распознавания команд
VIDEO_DOWNLOAD_PATTERN = re.compile(r'#video_download_(\d+)_(\d+)')
FORWARD_DOWNLOAD_PATTERN = re.compile(r'#forward_download_(\d+)_(\d+)_(-?\d+)_(\d+)')

# Создаем клиент Pyrogram
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

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
    
    return message.from_user.username == BOT_ID or str(message.from_user.id) == BOT_TOKEN.split(':')[0]

# Регистрируем пользовательский фильтр
bot_filter = filters.create(from_our_bot)

@app.on_message(bot_filter & filters.chat(TELETHON_WORKER_CHAT_ID))
async def handle_bot_messages(client, message):
    """Обрабатывает сообщения от бота в релейном чате."""
    try:
        sender = message.from_user
        sender_info = f"@{sender.username}" if sender.username else f"ID:{sender.id}"
        message_text = message.text or message.caption or ""
        
        logger.info(f"📩 Получено сообщение от {sender_info}: {message_text[:50]}{'...' if len(message_text) > 50 else ''}")
        
        # Проверяем наличие команды скачивания в тексте или подписи
        video_match = VIDEO_DOWNLOAD_PATTERN.search(message_text)
        forward_match = FORWARD_DOWNLOAD_PATTERN.search(message_text)
        
        # Обработка команды скачивания видео
        if video_match:
            chat_id, message_id = video_match.groups()
            logger.info(f"🎬 Обнаружен запрос на скачивание видео: chat_id={chat_id}, message_id={message_id}")
            
            # Проверяем наличие видео в сообщении
            if message.video:
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                
                # Скачиваем видео
                success = await download_and_save_video(message, video_path)
                
                # Отправляем сообщение боту о результате
                if success:
                    await client.send_message(BOT_ID, f"#video_downloaded_{chat_id}_{message_id}")
                else:
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}")
            else:
                logger.warning(f"⚠️ Команда на скачивание получена, но в сообщении нет видео")
        
        # Обработка команды скачивания из пересланного сообщения
        elif forward_match:
            chat_id, message_id, source_chat_id, source_message_id = forward_match.groups()
            logger.info(f"🔄 Обнаружен запрос на скачивание видео из другого чата: "
                      f"chat_id={chat_id}, message_id={message_id}, "
                      f"source_chat_id={source_chat_id}, source_message_id={source_message_id}")
            
            try:
                # Получаем сообщение из указанного чата
                source_chat_id = int(source_chat_id)
                source_message_id = int(source_message_id)
                
                # Путь для сохранения видео
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                
                try:
                    # Получаем сообщение из исходного чата
                    source_message = await client.get_messages(source_chat_id, message_ids=source_message_id)
                    
                    if source_message and source_message.video:
                        # Скачиваем видео
                        success = await download_and_save_video(source_message, video_path)
                        
                        # Отправляем сообщение боту о результате
                        if success:
                            await client.send_message(BOT_ID, f"#video_downloaded_{chat_id}_{message_id}")
                        else:
                            await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}")
                    else:
                        logger.error(f"❌ Исходное сообщение не содержит видео: {source_chat_id}, {source_message_id}")
                        await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_no_media")
                
                except FloodWait as e:
                    logger.error(f"⏱️ Flood wait error: {e}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_flood_wait_{e.x}")
                
                except ChatAdminRequired:
                    logger.error(f"🔒 Нет прав доступа к чату: {source_chat_id}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_no_access")
            
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке запроса на пересылку: {e}")
                await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_error")
    
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке сообщения: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def main():
    """Основная функция для запуска Pyrogram worker'а."""
    logger.info("🚀 Запуск Pyrogram worker'а...")
    
    async with app:
        me = await app.get_me()
        logger.info(f"✅ Pyrogram worker запущен от имени {me.first_name} {me.last_name or ''} (@{me.username or 'без юзернейма'})")
        logger.info(f"👀 Жду видео-сообщения от бота с ID {BOT_ID} в чате {TELETHON_WORKER_CHAT_ID}...")
        
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