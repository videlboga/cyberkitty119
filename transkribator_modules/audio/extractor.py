import os
import asyncio
import subprocess
from pathlib import Path
from transkribator_modules.config import logger

async def extract_audio_from_video(video_path: Path, audio_path: Path) -> bool:
    """
    Извлекает аудио из видео файла с помощью ffmpeg.
    
    Args:
        video_path: Путь к видео файлу
        audio_path: Путь для сохранения аудио файла
        
    Returns:
        bool: True если успешно, False если ошибка
    """
    try:
        # Создаем директорию для аудио, если не существует
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🎵 Извлекаю аудио из {video_path.name}")
        
        # FFmpeg команда для извлечения аудио
        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # Audio codec
            '-ar', '44100',  # Sample rate
            '-ac', '2',  # Audio channels
            '-y',  # Overwrite output file
            str(audio_path)
        ]
        
        # Запускаем ffmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            if audio_path.exists() and audio_path.stat().st_size > 0:
                file_size_mb = audio_path.stat().st_size / (1024 * 1024)
                logger.info(f"✅ Аудио извлечено успешно: {file_size_mb:.1f} МБ")
                return True
            else:
                logger.error("❌ Аудио файл не создан или пустой")
                return False
        else:
            error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
            logger.error(f"❌ Ошибка ffmpeg: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении аудио: {e}")
        return False

async def compress_audio_for_api(input_path: Path, output_path: Path = None) -> Path:
    """
    Сжимает аудио файл для отправки в API (MP3 формат, низкий битрейт).
    
    Args:
        input_path: Путь к исходному аудио файлу
        output_path: Путь для сжатого файла (опционально)
        
    Returns:
        Path: Путь к сжатому файлу
    """
    try:
        if output_path is None:
            output_path = input_path.parent / f"{input_path.stem}_compressed.mp3"
            
        logger.info(f"🗜️ Сжимаю аудио: {input_path.name}")
        
        cmd = [
            'ffmpeg',
            '-i', str(input_path),
            '-codec:a', 'mp3',
            '-b:a', '64k',  # Low bitrate for API
            '-y',
            str(output_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and output_path.exists():
            original_size = input_path.stat().st_size / (1024 * 1024)
            compressed_size = output_path.stat().st_size / (1024 * 1024)
            compression_ratio = (1 - compressed_size / original_size) * 100
            
            logger.info(f"✅ Аудио сжато: {original_size:.1f}МБ → {compressed_size:.1f}МБ (-{compression_ratio:.1f}%)")
            return output_path
        else:
            logger.error("❌ Ошибка при сжатии аудио")
            return input_path
            
    except Exception as e:
        logger.error(f"❌ Ошибка при сжатии аудио: {e}")
        return input_path

def get_audio_duration(file_path: Path) -> float:
    """
    Получает длительность аудио файла в секундах.
    
    Args:
        file_path: Путь к аудио файлу
        
    Returns:
        float: Длительность в секундах
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            str(file_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            duration = float(result.stdout.strip())
            logger.info(f"📏 Длительность аудио: {duration:.1f} секунд")
            return duration
        else:
            logger.error(f"❌ Ошибка при определении длительности: {result.stderr}")
            return 0.0
            
    except Exception as e:
        logger.error(f"❌ Ошибка при получении длительности аудио: {e}")
        return 0.0 