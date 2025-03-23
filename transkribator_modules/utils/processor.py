import asyncio
from pathlib import Path
from transkribator_modules.config import (
    logger, user_transcriptions, AUDIO_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH
)
from transkribator_modules.audio.extractor import extract_audio_from_video
from transkribator_modules.transcribe.transcriber import (
    transcribe_audio, format_transcript_with_llm
)

async def process_video_file(video_path, chat_id, message_id, context, status_message=None):
    """Обрабатывает видео из файла, извлекает аудио и выполняет транскрибацию.
    Эта версия не требует объекта Update и может быть использована напрямую с файлами."""
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    try:
        # Пути к файлам
        audio_path = AUDIO_DIR / f"telegram_video_{message_id}.wav"
        
        # Проверяем наличие видео
        if not video_path.exists():
            if status_message:
                await status_message.edit_text(
                    "Мяу! Видеофайл не найден. Возможно, возникла ошибка при скачивании. *грустно машет хвостом*"
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Мяу! Видеофайл не найден. Возможно, возникла ошибка при скачивании. *грустно машет хвостом*"
                )
            return
        
        # Создаем статусное сообщение, если его еще нет
        if not status_message:
            status_message = await context.bot.send_message(
                chat_id=chat_id,
                text="Мур-мур! Начинаю обработку видео... *сосредоточенно смотрит на экран*"
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
        user_transcriptions[chat_id] = {
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
            
            # Отправляем файл с транскрипцией
            with open(transcript_path, "rb") as file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    filename=f"Транскрипция видео {message_id}.txt",
                    caption="Вот транскрипция вашего видео! *выгибает спину от гордости*"
                )
        else:
            # Если транскрипция не слишком длинная, отправляем текстом
            await status_message.edit_text(
                f"Готово! Вот транскрипция вашего видео:\n\n{formatted_transcript}\n\n@CyberKitty19_bot"
            )
        
        # Добавляем кнопки для получения саммари и сырой транскрипции
        keyboard = [
            [
                InlineKeyboardButton("📝 Подробное саммари", callback_data=f"detailed_summary_{message_id}"),
                InlineKeyboardButton("📋 Краткое саммари", callback_data=f"brief_summary_{message_id}")
            ],
            [InlineKeyboardButton("🔍 Показать сырую транскрипцию", callback_data=f"raw_{message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="Вы можете получить саммари или необработанную версию транскрипции, нажав на кнопки ниже:",
            reply_markup=reply_markup
        )
        
        logger.info(f"Транскрипция видео успешно завершена, файлы: {transcript_path}, {raw_transcript_path}")
        return transcript_path, raw_transcript_path
        
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        if status_message:
            await status_message.edit_text(
                f"Произошла ошибка при обработке видео: {e}. *виновато опускает уши*"
            )
        return None, None

async def process_video(chat_id, message_id, update, context):
    """Обрабатывает видео, извлекает аудио и выполняет транскрибацию."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    user_id = update.effective_user.id
    
    try:
        # Пути к файлам
        from transkribator_modules.config import VIDEOS_DIR
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
                f"Готово! Вот транскрипция видео:\n\n{formatted_transcript}\n\n@CyberKitty19_bot"
            )
        
        # Добавляем кнопки для получения саммари и исходной транскрипции
        keyboard = [
            [
                InlineKeyboardButton("📝 Подробное саммари", callback_data=f"detailed_summary_{message_id}"),
                InlineKeyboardButton("📋 Краткое саммари", callback_data=f"brief_summary_{message_id}")
            ],
            [InlineKeyboardButton("🔍 Показать сырую транскрипцию", callback_data=f"raw_{message_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Вы можете получить саммари или необработанную версию транскрипции, нажав на кнопки ниже:",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        await update.message.reply_text(
            f"Произошла ошибка при обработке видео: {str(e)} *испуганно прячется*"
        ) 