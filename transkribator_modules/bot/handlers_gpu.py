"""
GPU Transcription Handler for Telegram Bot

This module can be integrated into transkribator_modules/bot/handlers.py
to add GPU transcription support.

Usage in main.py:
    from transkribator_modules.bot.handlers_gpu import handle_gpu_transcription
    application.add_handler(CommandHandler("transcribe_gpu", handle_gpu_transcription))
"""

import asyncio
import os
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import logger, VIDEOS_DIR
from transkribator_modules.db.database import log_telegram_event


# GPU Pipeline configuration
GPU_API_URL = os.getenv("GPU_API_URL", "http://localhost:8000/api/v1")
GPU_MEDIA_INCOMING = Path(os.getenv("GPU_MEDIA_DIR", ".")) / "media" / "incoming"
GPU_MEDIA_RESULTS = Path(os.getenv("GPU_MEDIA_DIR", ".")) / "media" / "results"


async def _download_telegram_file(context: ContextTypes.DEFAULT_TYPE, file_id: str, output_path: Path) -> bool:
    """Download file from Telegram and save locally."""
    try:
        logger.info(f"Downloading file {file_id} to {output_path}")
        file = await context.bot.get_file(file_id)
        await file.download_to_drive(str(output_path))
        logger.info(f"✓ File downloaded: {output_path} ({output_path.stat().st_size / 1024**2:.1f}MB)")
        return True
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        return False


async def _call_gpu_api(file_path: Path, language: str = "ru") -> Optional[dict]:
    """Call GPU transcription API."""
    try:
        url = urljoin(GPU_API_URL, "/transcribe-gpu")
        payload = {
            "file_path": str(file_path),
            "language": language
        }
        
        logger.info(f"Calling GPU API: {url}")
        logger.info(f"Payload: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(f"✓ GPU API response: {result['status']}")
                    return result
                else:
                    error_text = await resp.text()
                    logger.error(f"GPU API error {resp.status}: {error_text}")
                    return None
    
    except Exception as e:
        logger.error(f"Failed to call GPU API: {e}")
        return None


def _format_result_for_user(api_result: dict) -> tuple[str, Optional[str]]:
    """Format API result for user display."""
    
    if api_result["status"] != "success":
        return f"❌ Ошибка транскрибации: {api_result.get('error', 'Unknown error')}", None
    
    # Read the result file
    result_file = api_result.get("result_file")
    report_file = api_result.get("report_file")
    
    text_lines = [
        f"✅ Транскрибация завершена!\n",
        f"⏱️  Время обработки: {api_result['total_time']:.1f}s",
        f"  • Подготовка аудио: {api_result['preparation_time']:.1f}s",
        f"  • GPU транскрибация: {api_result['transcription_time']:.1f}s",
        f"📊 Статистика:",
        f"  • Сегментов: {api_result['segments']}",
        f"  • Продолжительность: {int(api_result['audio_duration'] / 60)}:{int(api_result['audio_duration'] % 60):02d}",
    ]
    
    formatted = "\n".join(text_lines)
    return formatted, report_file


async def handle_gpu_transcription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle /transcribe_gpu command - GPU-accelerated transcription.
    
    Usage:
        /transcribe_gpu <reply to media file>
    """
    
    if not update.message:
        await update.effective_chat.send_message("❌ Неверное использование команды")
        return
    
    # Check if command is a reply to media
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📎 Используй команду как ответ на файл видео/аудио:\n\n"
            "1. Отправь видео/аудио файл\n"
            "2. Ответь на него: /transcribe_gpu\n\n"
            "⚡ GPU транскрибация работает быстрее:\n"
            "• 21 минута аудио = ~60 секунд"
        )
        return
    
    reply_msg = update.message.reply_to_message
    
    # Extract file from message
    file_id = None
    file_name = None
    
    if reply_msg.video:
        file_id = reply_msg.video.file_id
        file_name = f"video_{reply_msg.video.file_id[:16]}.mp4"
    elif reply_msg.audio:
        file_id = reply_msg.audio.file_id
        file_name = f"audio_{reply_msg.audio.file_id[:16]}.mp3"
    elif reply_msg.document:
        file_id = reply_msg.document.file_id
        file_name = reply_msg.document.file_name
    elif reply_msg.voice:
        file_id = reply_msg.voice.file_id
        file_name = f"voice_{reply_msg.voice.file_id[:16]}.ogg"
    else:
        await update.message.reply_text(
            "❌ Поддерживаемые форматы: видео (MP4, WebM), аудио (MP3, WAV, FLAC), голосовые сообщения"
        )
        return
    
    if not file_id or not file_name:
        await update.message.reply_text("❌ Не удалось получить информацию о файле")
        return
    
    # Create media directories if needed
    GPU_MEDIA_INCOMING.mkdir(parents=True, exist_ok=True)
    GPU_MEDIA_RESULTS.mkdir(parents=True, exist_ok=True)
    
    # Download file
    status_msg = await update.message.reply_text(
        "⏳ Загружаю файл...\n"
        "(это может занять несколько минут)"
    )
    
    file_path = GPU_MEDIA_INCOMING / file_name
    if not await _download_telegram_file(context, file_id, file_path):
        await status_msg.edit_text("❌ Ошибка загрузки файла")
        log_telegram_event(
            update.effective_user.id,
            "gpu_transcribe_error",
            {"error": "download_failed", "file_id": file_id}
        )
        return
    
    # Update status
    await status_msg.edit_text(
        "⏳ Начинаю транскрибацию на GPU...\n"
        "(для 21 минут аудио это займет ~60 секунд)"
    )
    
    # Call GPU API
    api_result = await _call_gpu_api(file_path, language="ru")
    
    if not api_result:
        await status_msg.edit_text(
            "❌ Ошибка: GPU сервис недоступен\n"
            "Попробуй позже или используй обычную транскрибацию"
        )
        log_telegram_event(
            update.effective_user.id,
            "gpu_transcribe_error",
            {"error": "api_unavailable"}
        )
        return
    
    # Format result
    user_message, report_file_path = _format_result_for_user(api_result)
    
    # Send result
    await status_msg.edit_text(user_message)
    
    # Send report file if available
    if report_file_path and Path(report_file_path).exists():
        try:
            with open(report_file_path, "rb") as f:
                await update.effective_chat.send_document(
                    document=f,
                    filename=Path(report_file_path).name,
                    caption="📄 Детальный отчет транскрибации"
                )
        except Exception as e:
            logger.warning(f"Failed to send report file: {e}")
    
    # Clean up
    try:
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Cleaned up: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up file: {e}")
    
    # Log event
    log_telegram_event(
        update.effective_user.id,
        "gpu_transcribe_complete",
        {
            "job_id": api_result.get("job_id"),
            "total_time": api_result.get("total_time"),
            "file_name": file_name,
            "segments": api_result.get("segments")
        }
    )


async def handle_gpu_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check GPU pipeline status."""
    
    try:
        url = urljoin(GPU_API_URL, "/pipeline-status")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    status = await resp.json()
                    
                    if status["gpu"]["available"]:
                        text = (
                            "✅ GPU доступна\n\n"
                            f"🖥️  {status['gpu']['name']}\n"
                            f"💾 Память: {status['gpu']['memory']['free_gb']:.1f}GB свободной "
                            f"({status['gpu']['memory']['used_percent']:.1f}% используется)\n\n"
                            f"⚡ Производительность:\n"
                            f"• Один файл: {status['performance']['single_file_time']}\n"
                            f"• Макс параллельно: {status['performance']['parallel_capacity']}\n"
                            f"• Пропускная способность: {status['performance']['throughput']}"
                        )
                    else:
                        text = "❌ GPU недоступна"
                    
                    await update.message.reply_text(text)
                else:
                    await update.message.reply_text("❌ Ошибка получения статуса GPU")
    
    except Exception as e:
        logger.error(f"Failed to get GPU status: {e}")
        await update.message.reply_text("❌ Ошибка: GPU сервис недоступен")


# Export for use in main.py
__all__ = [
    "handle_gpu_transcription",
    "handle_gpu_status",
]
