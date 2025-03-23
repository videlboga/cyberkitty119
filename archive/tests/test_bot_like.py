#!/usr/bin/env python3

import asyncio
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

async def extract_audio_from_video(video_path, audio_path):
    """Извлекает аудио из видео с использованием ffmpeg."""
    try:
        # Создаем директорию для аудио, если она не существует
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        logger.info(f"Извлечение аудио из видео: {video_path} в {audio_path}")
        
        # Тест 1: Используем asyncio.create_subprocess_exec
        logger.info("Тест 1: Запускаю ffmpeg через asyncio.create_subprocess_exec")
        
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y',
            str(audio_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"❌ Ошибка при извлечении аудио, код возврата: {process.returncode}")
            logger.error(f"Stderr: {stderr.decode()}")
            return False
        
        # Проверяем, что файл создался и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"✅ Аудио успешно извлечено из видео, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error("❌ Аудио файл не создан или пустой")
            return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении аудио из видео: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def simulate_bot_handler():
    """Симулирует обработчик сообщений бота."""
    logger.info("Симуляция работы бота...")
    
    # Проверим, существует ли видео файл
    video_path = 'videos/telegram_video_3736.mp4'
    audio_path = 'audio/test_bot_like.wav'
    
    if not os.path.exists(video_path):
        logger.error(f"Видеофайл не найден: {video_path}")
        return
    
    logger.info("Запускаю обработку видео...")
    
    # Имитируем обработку сообщения ботом
    await asyncio.sleep(1)  # Имитация какой-то другой работы
    
    # Извлекаем аудио из видео
    audio_extracted = await extract_audio_from_video(video_path, audio_path)
    
    if audio_extracted:
        logger.info("Аудио успешно извлечено, продолжаем обработку...")
        # Имитация дальнейшей обработки...
        await asyncio.sleep(1)
    else:
        logger.error("Не удалось извлечь аудио из видео")
    
    logger.info("Обработка завершена")

async def main():
    """Главная функция."""
    await simulate_bot_handler()

if __name__ == "__main__":
    asyncio.run(main()) 