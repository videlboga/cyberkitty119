import os
import asyncio
from pathlib import Path
from transkribator_modules.config import logger

async def extract_audio_from_video(video_path, audio_path):
    """Извлекает аудио из видео с использованием ffmpeg в фоновом режиме."""
    try:
        # Создаем директорию для аудио, если она не существует
        audio_path.parent.mkdir(exist_ok=True)
        
        logger.info(f"Извлечение аудио из видео: {video_path} в {audio_path}")
        
        # Используем ffmpeg в фоновом режиме
        logger.info("Запускаю ffmpeg в фоновом режиме")
        
        # Формируем команду для запуска в фоне
        cmd = f'ffmpeg -i "{str(video_path)}" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "{str(audio_path)}" </dev/null >/dev/null 2>&1 &'
        
        # Запускаем ffmpeg в фоне
        os.system(cmd)
        
        # Ждем некоторое время, чтобы процесс запустился
        await asyncio.sleep(0.5)
        
        # Ждем некоторое разумное время для завершения процесса
        max_wait_time = 60  # максимальное время ожидания в секундах
        check_interval = 0.5  # интервал проверки в секундах
        
        elapsed_time = 0
        while elapsed_time < max_wait_time:
            if audio_path.exists() and audio_path.stat().st_size > 0:
                # Файл создан и не пустой
                logger.info(f"✅ Аудио успешно извлечено из видео, размер: {audio_path.stat().st_size} байт")
                return True
            
            await asyncio.sleep(check_interval)
            elapsed_time += check_interval
            
            if elapsed_time % 5 == 0:
                logger.debug(f"Ожидание создания файла: {elapsed_time} секунд...")
        
        # Если мы здесь, значит время ожидания истекло
        logger.error(f"❌ Время ожидания создания аудиофайла истекло ({max_wait_time} секунд)")
        return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении аудио из видео: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False 