import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger, user_transcriptions, VIDEOS_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH,
    TELETHON_WORKER_CHAT_ID, PYROGRAM_WORKER_ENABLED, PYROGRAM_WORKER_CHAT_ID
)
from transkribator_modules.utils.processor import process_video, process_video_file

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
                    f"*деловито кивает*"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при обработке кнопки raw transcript: {e}")
            await query.message.reply_text(
                "Произошла ошибка при получении сырой транскрипции. *смущенно прячет мордочку*"
            )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для всех типов сообщений."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Логируем сообщение
    logger.info(f"Получено сообщение от пользователя {user_id}")
    
    # Проверяем сообщения от воркера (уведомления о скачивании)
    if update.message.text and ("#video_downloaded_" in update.message.text or "#pyro_downloaded_" in update.message.text):
        try:
            # Извлекаем chat_id и message_id из сообщения
            parts = update.message.text.split('_')
            if len(parts) >= 4:
                original_chat_id = int(parts[2])
                original_message_id = int(parts[3])
                
                logger.info(f"Получено уведомление о скачивании видео: chat_id={original_chat_id}, message_id={original_message_id}")
                
                # Проверяем наличие видео
                video_path = VIDEOS_DIR / f"telegram_video_{original_message_id}.mp4"
                
                if video_path.exists() and video_path.stat().st_size > 0:
                    logger.info(f"Видео найдено: {video_path}, начинаю обработку")
                    
                    # Отправляем пользователю уведомление о начале обработки
                    status_message = await context.bot.send_message(
                        chat_id=original_chat_id,
                        text="Видео успешно скачано! Начинаю обработку... *радостно мурчит*"
                    )
                    
                    # Обрабатываем видео
                    try:
                        await process_video_file(video_path, original_chat_id, original_message_id, context, status_message=status_message)
                    except Exception as process_error:
                        logger.error(f"Ошибка при обработке видео: {process_error}")
                        # Отправляем сообщение об ошибке
                        await context.bot.send_message(
                            chat_id=original_chat_id,
                            text=f"Произошла ошибка при обработке видео: {process_error}. *виновато опускает уши*"
                        )
                else:
                    logger.error(f"Видео не найдено или пустое: {video_path}")
                    await context.bot.send_message(
                        chat_id=original_chat_id,
                        text="Не удалось найти скачанное видео. *растерянно оглядывается*"
                    )
        except Exception as e:
            logger.error(f"Ошибка при обработке уведомления от воркера: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Проверяем наличие видео в сообщении
    elif update.message.video:
        logger.info(f"Получено видео от пользователя {user_id}")
        
        # Отправляем сообщение о начале загрузки
        status_message = await update.message.reply_text(
            "Мяу! Вижу видео! Скачиваю его... *возбужденно виляет хвостом*"
        )
        
        video = update.message.video
        
        try:
            # Пытаемся скачать видео напрямую
            video_file = await context.bot.get_file(video.file_id)
            
            # Создаем директорию, если не существует
            video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
            video_path.parent.mkdir(exist_ok=True)
            
            # Скачиваем видео
            await video_file.download_to_drive(custom_path=video_path)
            
            # Проверяем, что файл существует и не пустой
            if video_path.exists() and video_path.stat().st_size > 0:
                logger.info(f"Видео успешно загружено: {video_path} (размер: {video_path.stat().st_size} байт)")
                
                # Обновляем статус
                await status_message.edit_text(
                    "Видео успешно загружено! Начинаю обработку... *радостно мурчит*"
                )
                
                # Обрабатываем видео
                await process_video(chat_id, message_id, update, context)
            else:
                logger.error(f"Ошибка при скачивании видео: файл не существует или пустой")
                await status_message.edit_text(
                    "Не удалось скачать видео. Пожалуйста, попробуйте снова. *печально опускает ушки*"
                )
                
        except Exception as e:
            logger.error(f"Ошибка при скачивании видео: {e}")
            
            # Проверяем, является ли ошибка "File is too big"
            if "File is too big" in str(e):
                worker_available = False
                
                # Сначала проверяем доступность Pyro воркера
                if PYROGRAM_WORKER_ENABLED and PYROGRAM_WORKER_CHAT_ID != 0:
                    logger.info(f"Файл слишком большой для прямой загрузки, использую Pyrogram воркер")
                    
                    # Обновляем статус
                    await status_message.edit_text(
                        "Видео слишком большое для прямой загрузки. Использую Pyrogram воркер... *сосредоточенно стучит по клавиатуре*"
                    )
                    
                    try:
                        # Формируем команду
                        command_text = f"#pyro_download_{chat_id}_{message_id}"
                        logger.info(f"Отправляю команду в Pyro релейный чат: {command_text}, chat_id={PYROGRAM_WORKER_CHAT_ID}")
                        
                        # Отправляем видео с командой в релейный чат
                        await context.bot.copy_message(
                            chat_id=PYROGRAM_WORKER_CHAT_ID,
                            from_chat_id=chat_id,
                            message_id=message_id,
                            caption=command_text  # Устанавливаем текст команды как подпись к видео
                        )
                        
                        # Обновляем статус
                        await status_message.edit_text(
                            "Запрос на скачивание отправлен! Ожидаю ответа... *нетерпеливо постукивает лапкой*"
                        )
                        worker_available = True
                        
                    except Exception as pyro_error:
                        logger.error(f"Ошибка при отправке запроса Pyro воркеру: {pyro_error}")
                        # Не обновляем статус, так как может быть доступен Telethon воркер
                
                # Пробуем использовать Telethon воркер, если Pyro недоступен или произошла ошибка
                if not worker_available and TELETHON_WORKER_CHAT_ID != 0:
                    logger.info(f"Файл слишком большой для прямой загрузки, использую Telethon воркер")
                    
                    # Обновляем статус
                    await status_message.edit_text(
                        "Видео слишком большое для прямой загрузки. Использую Telethon воркер... *сосредоточенно стучит по клавиатуре*"
                    )
                    
                    try:
                        # Формируем команду
                        command_text = f"#video_download_{chat_id}_{message_id}"
                        logger.info(f"Отправляю команду в релейный чат: {command_text}, chat_id={TELETHON_WORKER_CHAT_ID}")
                        
                        # Отправляем видео с командой в релейный чат
                        await context.bot.copy_message(
                            chat_id=TELETHON_WORKER_CHAT_ID,
                            from_chat_id=chat_id,
                            message_id=message_id,
                            caption=command_text  # Устанавливаем текст команды как подпись к видео
                        )
                        
                        # Обновляем статус
                        await status_message.edit_text(
                            "Запрос на скачивание отправлен! Ожидаю ответа... *нетерпеливо постукивает лапкой*"
                        )
                        worker_available = True
                        
                    except Exception as telethon_error:
                        logger.error(f"Ошибка при отправке запроса Telethon воркеру: {telethon_error}")
                        await status_message.edit_text(
                            f"Произошла ошибка при обработке видео через Telethon релейный чат: {str(telethon_error)} *смущенно прячет мордочку*"
                        )
                
                # Если ни один воркер не доступен
                if not worker_available:
                    await status_message.edit_text(
                        "К сожалению, видео слишком большое для прямой загрузки, а ни один воркер не настроен. *печально вздыхает*"
                    )
            else:
                await status_message.edit_text(
                    f"Произошла ошибка при скачивании видео: {str(e)} *испуганно прячется*"
                )
    
    # В минимальном режиме просто отвечаем текстом
    else:
        await update.message.reply_text(
            "Мяу! *игриво смотрит* Отправь мне видео, и я создам текстовую расшифровку! *виляет хвостиком*"
        ) 