#!/usr/bin/env python3

import sys
import os
import subprocess
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("audio_extractor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def extract_audio(video_path, audio_path):
    """Извлекает аудио из видео с использованием ffmpeg."""
    try:
        # Проверка наличия файла
        if not os.path.exists(video_path):
            logger.error(f"Видеофайл не найден: {video_path}")
            return False
            
        # Создание директории для аудио, если не существует
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        logger.info(f"Извлечение аудио из {video_path} в {audio_path}")
        
        # Формируем команду bash с nice и nohup
        cmd_str = f'nice -n 19 ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "{audio_path}"'
        logger.info(f"Запускаю команду: {cmd_str}")
        
        # Запускаем через os.system напрямую
        return_code = os.system(cmd_str)
        
        if return_code != 0:
            logger.error(f"Ошибка ffmpeg, код возврата: {return_code}")
            return False
            
        # Проверяем, что файл создан и не пустой
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"Аудио успешно извлечено: {audio_path}, размер: {os.path.getsize(audio_path)} байт")
            return True
        else:
            logger.error(f"Аудиофайл не создан или пустой: {audio_path}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при извлечении аудио: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    # Проверяем аргументы командной строки
    if len(sys.argv) != 3:
        print(f"Использование: {sys.argv[0]} <путь_к_видео> <путь_к_аудио>")
        sys.exit(1)
        
    video_path = sys.argv[1]
    audio_path = sys.argv[2]
    
    success = extract_audio(video_path, audio_path)
    sys.exit(0 if success else 1) 