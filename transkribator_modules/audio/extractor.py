import os
import asyncio
from pathlib import Path
from transkribator_modules.config import logger

async def extract_audio_from_video(video_path, audio_path):
    """Извлекает аудио из видео с использованием ffmpeg."""
    try:
        # Создаем директорию для аудио, если она не существует
        audio_path.parent.mkdir(exist_ok=True)
        
        logger.info(f"Извлечение аудио из видео: {video_path} в {audio_path}")
        
        # Используем asyncio для запуска ffmpeg
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
        
        logger.info(f"Запускаю ffmpeg: {' '.join(cmd)}")
        
        # Запускаем ffmpeg через asyncio
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            if audio_path.exists() and audio_path.stat().st_size > 0:
                logger.info(f"✅ Аудио успешно извлечено из видео, размер: {audio_path.stat().st_size} байт")
                return True
            else:
                logger.error("❌ Аудиофайл не создан или пустой")
                return False
        else:
            logger.error(f"❌ Ошибка ffmpeg: {stderr.decode()}")
            return False
    
    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении аудио из видео: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False 