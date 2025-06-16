"""
CyberKitty Transkribator - Интегрированные обработчики
Объединяет новую логику Bot API Server с существующей монетизацией
"""

import asyncio
import os
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger, user_transcriptions, VIDEOS_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH,
    USE_LOCAL_BOT_API, LOCAL_BOT_API_URL
)
from transkribator_modules.utils.processor import process_video, process_video_file

# Импорт нового загрузчика файлов
from transkribator_modules.utils.large_file_downloader import download_large_file

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки в сообщениях."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("raw_"):
        try:
            message_id = query.data.split("_")[1]
            raw_transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}_raw.txt"
            
            if not raw_transcript_path.exists():
                await query.message.reply_text(
                    "Не могу найти сырую транскрипцию для этого видео. *растерянно смотрит*"
                )
                return
                
            with open(raw_transcript_path, "r", encoding="utf-8") as f:
                raw_transcript = f.read()
                
            if len(raw_transcript) > MAX_MESSAGE_LENGTH:
                # Если транскрипция слишком длинная, отправляем файлом
                with open(raw_transcript_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=f,
                        filename=f"raw_transcript_{message_id}.txt",
                        caption="Вот необработанная транскрипция этого видео! *деловито машет хвостом*"
                    )
            else:
                # Иначе отправляем текстом
                await query.message.reply_text(
                    f"Вот необработанная транскрипция для этого видео:\n\n{raw_transcript}\n\n"
                    f"@CyberKitty19_bot"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки raw transcript: {e}")
            await query.message.reply_text(
                "Произошла ошибка при получении сырой транскрипции. *смущенно прячет мордочку*"
            )
    
    elif query.data.startswith("detailed_summary_") or query.data.startswith("brief_summary_"):
        try:
            # Получаем id сообщения
            message_id = query.data.split("_")[-1]
            
            # Определяем тип саммари
            summary_type = "подробное" if query.data.startswith("detailed_") else "краткое"
            
            # Отправляем сообщение о начале генерации
            status_message = await query.message.reply_text(
                f"Генерирую {summary_type} саммари для этого видео... *сосредоточенно обдумывает содержание*"
            )
            
            # Загружаем транскрипцию
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}.txt"
            
            if not transcript_path.exists():
                await status_message.edit_text(
                    "Не могу найти транскрипцию для этого видео. *растерянно смотрит*"
                )
                return
                
            with open(transcript_path, "r", encoding="utf-8") as f:
                transcript = f.read()
            
            # Импортируем функции генерации саммари
            from transkribator_modules.transcribe.transcriber import generate_detailed_summary, generate_brief_summary
            
            # Генерируем саммари в зависимости от типа
            if query.data.startswith("detailed_summary_"):
                summary = await generate_detailed_summary(transcript)
            else:
                summary = await generate_brief_summary(transcript)
                
            if not summary:
                await status_message.edit_text(
                    f"Не удалось создать {summary_type} саммари. *виновато опускает уши*"
                )
                return
            
            # Сохраняем саммари в файл
            summary_filename = f"telegram_video_{message_id}_{summary_type}_summary.txt"
            summary_path = TRANSCRIPTIONS_DIR / summary_filename
            
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            
            # Отправляем результат
            if len(summary) > MAX_MESSAGE_LENGTH:
                # Если саммари слишком длинное, отправляем файлом
                with open(summary_path, "rb") as f:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=f,
                        filename=summary_filename,
                        caption=f"Вот {summary_type} саммари этого видео! *гордо поднимает хвост*"
                    )
            else:
                # Иначе отправляем текстом
                await status_message.edit_text(
                    f"{summary}\n\n@CyberKitty19_bot"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при генерации саммари: {e}")
            await query.message.reply_text(
                "Произошла ошибка при генерации саммари. *смущенно прячет мордочку*"
            ) 