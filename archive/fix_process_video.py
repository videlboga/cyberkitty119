import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Предположим, что эти функции и константы были определены ранее
from log import logger
VIDEOS_DIR = Path("/path/to/videos")
AUDIO_DIR = Path("/path/to/audio")
TRANSCRIPTIONS_DIR = Path("/path/to/transcriptions")
MAX_MESSAGE_LENGTH = 4096
user_transcriptions = {}

async def process_video(chat_id, message_id, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает видео, извлекает аудио и выполняет транскрибацию."""
    user_id = update.effective_user.id
    
    try:
        # Пути к файлам
        video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
        audio_path = AUDIO_DIR / f"telegram_video_{message_id}.wav"
        
        # Проверяем наличие видео
        if not video_path.exists():
            await update.message.reply_text(
                "Мяу! Видеофайл не найден. Возможно, возникла ошибка при скачивании. *грустно машет хвостом*"
            )
            return
        
        # Отправляем сообщение о начале обработки
        status_message = await update.message.reply_text(
            "Мур-мур! Начинаю обработку видео... *сосредоточенно смотрит на экран*"
        )
        
        # Извлекаем аудио из видео
        await status_message.edit_text(
            "Извлечение аудио из видео... *нетерпеливо перебирает лапками*"
        )
        
        audio_extracted = await extract_audio_from_video(video_path, audio_path)
        if not audio_extracted:
            await status_message.edit_text(
                "Не удалось извлечь аудио из видео. *грустно вздыхает*"
            )
            return
        
        # Транскрибируем аудио
        await status_message.edit_text(
            "Аудио извлечено! Теперь транскрибирую... *возбужденно виляет хвостом*"
        )
        
        raw_transcript = await transcribe_audio(audio_path)
        if not raw_transcript:
            await status_message.edit_text(
                "Не удалось выполнить транскрипцию аудио. *расстроенно мяукает*"
            )
            return
        
        # Форматируем транскрипцию
        await status_message.edit_text(
            "Транскрипция получена! Привожу текст в читаемый вид... *деловито стучит по клавиатуре*"
        )
        
        formatted_transcript = await format_transcript_with_llm(raw_transcript)
        
        # Создаем файлы с транскрипциями
        transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}.txt"
        raw_transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}_raw.txt"
        
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(formatted_transcript)
        
        with open(raw_transcript_path, "w", encoding="utf-8") as f:
            f.write(raw_transcript)
        
        # Сохраняем транскрипции для пользователя
        user_transcriptions[user_id] = {
            'raw': raw_transcript,
            'formatted': formatted_transcript,
            'path': str(transcript_path),
            'raw_path': str(raw_transcript_path),
            'timestamp': asyncio.get_event_loop().time()
        }
        
        # Отправляем результаты пользователю
        if len(formatted_transcript) > MAX_MESSAGE_LENGTH:
            # Если транскрипция слишком длинная, отправляем файлом
            await status_message.edit_text(
                "Готово! Транскрипция получилась длинной, отправляю файлом... *довольно мурлычет*"
            )
            
            with open(transcript_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=f"transcript_{message_id}.txt",
                    caption="Вот ваша транскрипция! *гордо поднимает хвост*"
                )
        else:
            # Иначе отправляем текстом
            await status_message.edit_text(
                f"Готово! Вот транскрипция видео:\n\n{formatted_transcript}\n\n"
                f"*довольно мурлычет*"
            )
            
        # Добавляем кнопку для получения исходной транскрипции
        keyboard = [
            [InlineKeyboardButton("Показать сырую транскрипцию", callback_data=f"raw_{message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Вы можете получить необработанную версию транскрипции, нажав на кнопку ниже:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        await update.message.reply_text(
            f"Произошла ошибка при обработке видео: {str(e)} *испуганно прячется*"
        ) 