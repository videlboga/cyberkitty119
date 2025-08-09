#!/usr/bin/env python3

import os
import sys
import asyncio
import logging
import re
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, events, errors
from telethon.tl.types import Message, MessageMediaDocument, DocumentAttributeVideo

# Загружаем переменные окружения
load_dotenv()

# Получаем учетные данные API
API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
API_HASH = os.getenv('TELEGRAM_API_HASH', '')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
BOT_ID = os.getenv('BOT_ID', '')
SESSION_FILE = 'telethon_worker.session'

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
        logging.FileHandler("telethon_worker.log")
    ]
)
logger = logging.getLogger(__name__)

# Регулярные выражения для распознавания команд
VIDEO_DOWNLOAD_PATTERN = re.compile(r'#video_download_(\d+)_(\d+)')
FORWARD_DOWNLOAD_PATTERN = re.compile(r'#forward_download_(\d+)_(\d+)_(-?\d+)_(\d+)')

# Добавляем глобальные переменные в начало файла
async def main():
    """Основная функция для запуска Telethon worker'а."""
    global last_command_chat_id, last_command_message_id, last_command_time
    
    # Инициализация глобальных переменных для хранения последней команды
    last_command_chat_id = None
    last_command_message_id = None
    last_command_time = 0
    
    logger.info("Запуск Telethon worker'а...")
    
    # Проверяем, существует ли файл сессии
    session_file = Path(SESSION_FILE)
    if not session_file.exists():
        logger.error(f"Файл сессии {SESSION_FILE} не найден!")
        logger.error("Пожалуйста, запустите сначала скрипт telethon_auth.py для авторизации.")
        return
    
    # Создаем клиент Telegram с существующим файлом сессии
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    
    try:
        # Подключаемся к Telegram
        await client.connect()
        
        # Проверяем авторизацию
        if not await client.is_user_authorized():
            logger.error("Файл сессии существует, но пользователь не авторизован!")
            logger.error("Удалите файл сессии и запустите telethon_auth.py заново.")
            await client.disconnect()
            return
        
        # Получаем информацию о пользователе
        me = await client.get_me()
        logger.info(f"Telethon worker запущен от имени {me.first_name} {me.last_name} (@{me.username})")
        
        # Установка обработчика для новых сообщений
        client.add_event_handler(handle_new_message, events.NewMessage())
        
        logger.info(f"Жду видео-сообщения от бота с ID {BOT_ID}...")
        
        # Запускаем клиент и держим его активным
        await client.run_until_disconnected()
    
    except Exception as e:
        logger.error(f"Ошибка при запуске телетон-воркера: {e}")
    
    finally:
        # Отключаемся, если была ошибка
        if client and client.is_connected():
            await client.disconnect()

async def download_and_save_video(client, message, target_file):
    """Скачивает и сохраняет видео из сообщения Telegram."""
    try:
        logger.info(f"Начинаю скачивание видео в файл: {target_file}")
        
        # Создаем директорию, если она не существует
        target_file.parent.mkdir(exist_ok=True)
        
        # Скачиваем видео
        await client.download_media(message.media, file=str(target_file))
        
        # Проверяем, что файл существует и не пустой
        if target_file.exists() and target_file.stat().st_size > 0:
            logger.info(f"Видео успешно загружено: {target_file} (размер: {target_file.stat().st_size} байт)")
            return True
        else:
            logger.error(f"Файл пустой или не существует после загрузки: {target_file}")
            return False
    
    except Exception as e:
        logger.error(f"Ошибка при скачивании видео: {e}")
        return False

async def handle_new_message(event):
    """Обрабатывает новые сообщения от бота."""
    message = event.message
    client = event.client
    
    try:
        # Логируем полученное сообщение
        sender = await message.get_sender()
        sender_id = sender.id if hasattr(sender, 'id') else "Unknown ID"
        sender_username = sender.username if hasattr(sender, 'username') else "No username"
        message_text = message.text or message.caption or "No text"
        
        logger.info(f"Получено сообщение ({message.id}) от {sender_username or sender_id}: {message_text[:50]}{'...' if len(message_text) > 50 else ''}")
        
        # Получаем ID нашего бота из Telegram API
        try:
            bot_info = await client.get_entity(BOT_ID)
            bot_id = bot_info.id
            logger.info(f"ID нашего бота {BOT_ID}: {bot_id}")
        except Exception as e:
            logger.error(f"Не удалось получить информацию о боте: {e}")
            bot_id = None
            
        # Проверяем, что сообщение от нашего бота (по username или по ID)
        is_from_our_bot = (hasattr(sender, 'username') and sender.username == BOT_ID) or (bot_id and sender_id == bot_id)
        
        if not is_from_our_bot:
            logger.info(f"Пропускаю сообщение не от бота: {sender_username or sender_id}")
            return
            
        logger.info(f"👉 Получено сообщение от нашего бота: {message_text}")
        
        # Переменные для хранения параметров последней команды
        global last_command_chat_id, last_command_message_id, last_command_time
        current_time = asyncio.get_event_loop().time()
        
        # Проверяем текст и подпись сообщения
        message_text = message.text or message.caption or ""
        
        # Обработка сообщения с командой скачивания видео (в тексте или подписи)
        if message_text and VIDEO_DOWNLOAD_PATTERN.search(message_text):
            match = VIDEO_DOWNLOAD_PATTERN.search(message_text)
            chat_id, message_id = match.groups()
            logger.info(f"👍 Обнаружен запрос на скачивание видео: chat_id={chat_id}, message_id={message_id}")
            
            # Сохраняем параметры команды для возможной обработки следующего сообщения с видео
            last_command_chat_id = chat_id
            last_command_message_id = message_id
            last_command_time = current_time
            
            # Проверяем наличие видео в сообщении
            if message.media and (isinstance(message.media, MessageMediaDocument) and 
                            hasattr(message.media.document, 'attributes') and 
                            any(isinstance(attr, DocumentAttributeVideo) for attr in message.media.document.attributes)):
                
                # Путь для сохранения видео
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                
                # Скачиваем видео
                logger.info(f"🎬 Начинаю скачивание видео для message_id={message_id}")
                success = await download_and_save_video(client, message, video_path)
                
                # Отправляем сообщение боту о результате
                if success:
                    logger.info(f"✅ Видео успешно скачано: {video_path}")
                    await client.send_message(BOT_ID, f"#video_downloaded_{chat_id}_{message_id}")
                else:
                    logger.error(f"❌ Не удалось скачать видео для message_id={message_id}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}")
            else:
                logger.warning(f"⚠️ Команда на скачивание получена, но в сообщении нет видео: {message_id}")
                
        # Обработка сообщения с видео без текстовой команды (маловероятно с новым подходом, но оставим на всякий случай)
        elif message.media and (isinstance(message.media, MessageMediaDocument) and 
                hasattr(message.media.document, 'attributes') and 
                any(isinstance(attr, DocumentAttributeVideo) for attr in message.media.document.attributes)):
            
            logger.info(f"📹 Получено видео без явной команды в тексте")
            
            # Проверяем, может быть команда в подписи
            caption = message.caption or ""
            if caption and VIDEO_DOWNLOAD_PATTERN.search(caption):
                match = VIDEO_DOWNLOAD_PATTERN.search(caption)
                chat_id, message_id = match.groups()
                logger.info(f"📝 Найдена команда в подписи: chat_id={chat_id}, message_id={message_id}")
                
                # Путь для сохранения видео
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                
                # Скачиваем видео
                logger.info(f"🎬 Начинаю скачивание видео из сообщения с подписью для message_id={message_id}")
                success = await download_and_save_video(client, message, video_path)
                
                # Отправляем сообщение боту о результате
                if success:
                    logger.info(f"✅ Видео успешно скачано: {video_path}")
                    await client.send_message(BOT_ID, f"#video_downloaded_{chat_id}_{message_id}")
                else:
                    logger.error(f"❌ Не удалось скачать видео для message_id={message_id}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}")
            # Проверяем, было ли недавно получено сообщение с командой (для обратной совместимости)
            elif last_command_chat_id and last_command_message_id and (current_time - last_command_time < 5):
                logger.info(f"⏱️ Получено видео после команды. Использую сохраненные параметры: chat_id={last_command_chat_id}, message_id={last_command_message_id}")
                
                # Путь для сохранения видео
                video_path = VIDEOS_DIR / f"telegram_video_{last_command_message_id}.mp4"
                
                # Скачиваем видео
                success = await download_and_save_video(client, message, video_path)
                
                # Отправляем сообщение боту о результате
                if success:
                    logger.info(f"✅ Видео успешно скачано: {video_path}")
                    await client.send_message(BOT_ID, f"#video_downloaded_{last_command_chat_id}_{last_command_message_id}")
                    # Сбрасываем параметры последней команды после успешной обработки
                    last_command_chat_id = None
                    last_command_message_id = None
                else:
                    logger.error(f"❌ Не удалось скачать видео для message_id={last_command_message_id}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{last_command_chat_id}_{last_command_message_id}")
            else:
                logger.warning(f"⚠️ Получено видео без команды и без предыдущих параметров. Пропускаю.")
                
        # Обработка команды на скачивание видео из пересланного сообщения
        elif message_text:
            match = FORWARD_DOWNLOAD_PATTERN.search(message_text)
            
            if match:
                chat_id, message_id, source_chat_id, source_message_id = match.groups()
                logger.info(f"Обнаружен запрос на скачивание видео из другого чата: "
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
                        source_message = await client.get_messages(source_chat_id, ids=source_message_id)
                        
                        if source_message and source_message.media:
                            # Скачиваем видео
                            success = await download_and_save_video(client, source_message, video_path)
                            
                            # Отправляем сообщение боту о результате
                            if success:
                                await client.send_message(BOT_ID, f"#video_downloaded_{chat_id}_{message_id}")
                            else:
                                await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}")
                        else:
                            logger.error(f"Исходное сообщение не содержит медиа: {source_chat_id}, {source_message_id}")
                            await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_no_media")
                    
                    except errors.FloodWaitError as e:
                        logger.error(f"Flood wait error: {e}")
                        await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_flood_wait_{e.seconds}")
                    
                    except errors.ChatAdminRequiredError:
                        logger.error(f"Нет прав доступа к чату: {source_chat_id}")
                        await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_no_access")
                
                except Exception as e:
                    logger.error(f"Ошибка при обработке запроса на пересылку: {e}")
                    await client.send_message(BOT_ID, f"#video_download_failed_{chat_id}_{message_id}_error")
    
    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    # Запускаем основную функцию
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получено прерывание с клавиатуры. Завершаю работу...")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1) 