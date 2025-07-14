import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
import re
from urllib.parse import urlparse

from transkribator_modules.config import (
    logger, user_transcriptions, VIDEOS_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH, AUDIO_DIR
)
from transkribator_modules.utils.processor import process_video, process_video_file, process_audio_file, process_video_file_silent, process_audio_file_silent
from transkribator_modules.utils.downloader import download_media

# --- Обработчики для групповых чатов ---

async def handle_chat_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает запрос на добавление бота в чат."""
    chat_join_request = update.chat_join_request
    chat = chat_join_request.chat
    user = chat_join_request.from_user
    
    logger.info(f"Запрос на добавление бота в чат {chat.id} ({chat.title}) от пользователя {user.id}")
    
    # Автоматически принимаем запрос
    try:
        await context.bot.approve_chat_join_request(
            chat_id=chat.id,
            user_id=user.id
        )
        logger.info(f"Бот добавлен в чат {chat.id}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении бота в чат {chat.id}: {e}")

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает изменения статуса бота в чате."""
    # Проверяем, есть ли информация о статусе бота
    if hasattr(update, 'my_chat_member') and update.my_chat_member:
        chat_member = update.my_chat_member
        chat = chat_member.chat
        new_status = chat_member.new_chat_member.status
        old_status = chat_member.old_chat_member.status
        
        logger.info(f"Статус бота в чате {chat.id} изменился: {old_status} -> {new_status}")
        
        # Если бота добавили в группу
        if new_status in ['member', 'administrator'] and old_status in ['left', 'kicked']:
            await send_welcome_message(chat, context)
        
        # Если бота удалили из группы
        elif new_status in ['left', 'kicked']:
            logger.info(f"Бот удален из чата {chat.id} ({chat.title})")
    
    # Если это обычное сообщение, просто пропускаем
    return

async def send_welcome_message(chat, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение при добавлении бота в чат."""
    try:
        welcome_text = (
            f"🐱 Мяу! Привет, {chat.title}! Я CyberKitty — бот для транскрипции аудио и видео.\n\n"
            "**Что я умею:**\n"
            "• Транскрибировать видео и аудио файлы\n"
            "• Обрабатывать голосовые сообщения\n"
            "• Создавать краткие саммари\n"
            "• Работать с ссылками на YouTube\n\n"
            "**Как использовать:**\n"
            "Просто отправьте мне видео, аудио или голосовое сообщение!\n\n"
            "**Команды:**\n"
            "/start - Начать работу\n"
            "/help - Справка\n"
            "/plans - Тарифные планы\n\n"
            "Приятного использования! *радостно мурчит*"
        )
        
        await context.bot.send_message(
            chat_id=chat.id,
            text=welcome_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"Отправлено приветственное сообщение в чат {chat.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при отправке приветственного сообщения в чат {chat.id}: {e}")

async def check_bot_permissions(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет права бота в чате."""
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return bot_member.status in ['member', 'administrator']
    except Exception as e:
        logger.error(f"Ошибка при проверке прав бота в чате {chat_id}: {e}")
        return False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки в сообщениях."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("raw_"):
        try:
            message_id = query.data.split("_")[1]
            # Сначала пробуем видео-файл, затем аудио
            raw_transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}_raw.txt"
            if not raw_transcript_path.exists():
                raw_transcript_path = TRANSCRIPTIONS_DIR / f"telegram_audio_{message_id}_raw.txt"
            
            if not raw_transcript_path.exists():
                await query.message.reply_text(
                    "Не могу найти сырую транскрипцию для этого файла. *растерянно смотрит*"
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
    


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для всех типов сообщений."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    chat_type = update.effective_chat.type
    
    # Логируем сообщение
    logger.info(f"Получено сообщение от пользователя {user_id} в чате {chat_id} (тип: {chat_type})")
    
    # Проверяем права бота в групповых чатах
    if chat_type in ['group', 'supergroup']:
        has_permissions = await check_bot_permissions(chat_id, context)
        if not has_permissions:
            logger.warning(f"Бот не имеет прав в чате {chat_id}")
            return
    
    URL_RE = re.compile(r"https?://\S+")

    # 1) Ссылки на медиа / YouTube
    if update.message.text and URL_RE.search(update.message.text):
        url = URL_RE.search(update.message.text).group(0)
        status = await update.message.reply_text("🔗 Скачиваю медиа по ссылке…")
        target_dir = VIDEOS_DIR
        dl_path = await download_media(url, target_dir)
        if not dl_path:
            await status.edit_text("Не удалось скачать файл по ссылке 😿")
            return

        ext = dl_path.suffix.lower()
        if ext in {'.mp3', '.wav', '.flac', '.m4a'}:
            await process_audio_file(dl_path, chat_id, message_id, context, status_message=status)
        else:
            await process_video_file(dl_path, chat_id, message_id, context, status_message=status)
        return

    # 2) Обработка промокодов (если сообщение является текстом и выглядит как промокод)
    if update.message.text and not update.message.video and not update.message.document:
        text = update.message.text.strip().upper()
        
        # Проверяем, похоже ли это на промокод (определенные паттерны)
        if (text.startswith(("KITTY", "LIGHTKITTY", "LIGHT", "VIP", "SPECIAL", "PROMO")) or 
            (len(text) >= 5 and len(text) <= 20 and text.replace("-", "").replace("_", "").isalnum())):
            from transkribator_modules.bot.commands import activate_promo_code
            try:
                await activate_promo_code(update, context, text)
                return  # Прекращаем обработку как обычного сообщения
            except Exception as e:
                logger.error(f"Ошибка при обработке возможного промокода '{text}': {e}")
                # Если промокод не найден, отвечаем мягко
                await update.message.reply_text("🤔 Это похоже на промокод, но я его не нашёл. *задумчиво наклоняет голову*")
                return
    
    # Проверяем наличие видео в сообщении
    if update.message.voice or update.message.audio:
        # ----- аудио или голосовое сообщение -----
        if chat_type in ['group', 'supergroup']:
            # В группах - без статусных сообщений
            audio_file = await context.bot.get_file(update.message.voice.file_id if update.message.voice else update.message.audio.file_id)
            audio_path = AUDIO_DIR / f"telegram_audio_{message_id}{Path(audio_file.file_path).suffix or '.ogg'}"
            await audio_file.download_to_drive(custom_path=audio_path)
            await process_audio_file_silent(audio_path, chat_id, message_id, context)
        else:
            # В личном чате - как раньше
            status = await update.message.reply_text("Скачиваю аудио…")
            audio_file = await context.bot.get_file(update.message.voice.file_id if update.message.voice else update.message.audio.file_id)
            audio_path = AUDIO_DIR / f"telegram_audio_{message_id}{Path(audio_file.file_path).suffix or '.ogg'}"
            await audio_file.download_to_drive(custom_path=audio_path)
            await process_audio_file(audio_path, chat_id, message_id, context, status_message=status)
        return

    elif update.message.document and update.message.document.mime_type:
        mime = update.message.document.mime_type
        if mime.startswith('video/') or mime.startswith('audio/'):
            if chat_type in ['group', 'supergroup']:
                # В группах - без статусных сообщений
                doc_file = await context.bot.get_file(update.message.document.file_id)
                ext = Path(doc_file.file_path).suffix or ''.join(['.', mime.split('/')[-1]])
                if mime.startswith('audio/'):
                    local_path = AUDIO_DIR / f"telegram_audio_{message_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_audio_file_silent(local_path, chat_id, message_id, context)
                else:
                    local_path = VIDEOS_DIR / f"telegram_video_{message_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_video_file_silent(local_path, chat_id, message_id, context)
            else:
                # В личном чате - как раньше
                status = await update.message.reply_text("Скачиваю файл…")
                doc_file = await context.bot.get_file(update.message.document.file_id)
                ext = Path(doc_file.file_path).suffix or ''.join(['.', mime.split('/')[-1]])
                if mime.startswith('audio/'):
                    local_path = AUDIO_DIR / f"telegram_audio_{message_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_audio_file(local_path, chat_id, message_id, context, status_message=status)
                else:
                    local_path = VIDEOS_DIR / f"telegram_video_{message_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_video_file(local_path, chat_id, message_id, context, status_message=status)
            return

    if update.message.video:
        logger.info(f"Получено видео от пользователя {user_id}")
        
        if chat_type in ['group', 'supergroup']:
            # В группах - без статусных сообщений
            video = update.message.video
            try:
                video_file = await context.bot.get_file(video.file_id)
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                video_path.parent.mkdir(exist_ok=True)
                
                try:
                    await video_file.download_to_drive(custom_path=video_path)
                except Exception as download_err:
                    api_file_path = getattr(video_file, "file_path", None)
                    if api_file_path and str(api_file_path).startswith("/var/lib/telegram-bot-api"):
                        try:
                            import shutil, os
                            os.makedirs(video_path.parent, exist_ok=True)
                            shutil.copy(api_file_path, video_path)
                            logger.info(f"Скопировал файл напрямую из {api_file_path} в {video_path}")
                        except Exception as copy_err:
                            logger.error(f"Ошибка при копировании файла из локального Bot API: {copy_err}")
                            raise download_err
                    else:
                        raise download_err
                
                if video_path.exists() and video_path.stat().st_size > 0:
                    logger.info(f"Видео успешно загружено: {video_path} (размер: {video_path.stat().st_size} байт)")
                    await process_video_file_silent(video_path, chat_id, message_id, context)
                else:
                    logger.error(f"Ошибка при скачивании видео: файл не существует или пустой")
                    
            except Exception as e:
                logger.error(f"Ошибка при скачивании видео: {e}")
                if "File is too big" in str(e):
                    await update.message.reply_text(
                        "😿 Файл превышает лимит Telegram (≈ 2 ГБ). Пришлите прямую ссылку на файл."
                    )
                else:
                    await update.message.reply_text(
                        f"Произошла ошибка при скачивании видео: {str(e)}"
                    )
        else:
            # В личном чате - как раньше
            status_message = await update.message.reply_text(
                "Мяу! Вижу видео! Скачиваю его... *возбужденно виляет хвостом*"
            )
            
            video = update.message.video
            
            try:
                video_file = await context.bot.get_file(video.file_id)
                video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
                video_path.parent.mkdir(exist_ok=True)
                
                try:
                    await video_file.download_to_drive(custom_path=video_path)
                except Exception as download_err:
                    api_file_path = getattr(video_file, "file_path", None)
                    if api_file_path and str(api_file_path).startswith("/var/lib/telegram-bot-api"):
                        try:
                            import shutil, os
                            os.makedirs(video_path.parent, exist_ok=True)
                            shutil.copy(api_file_path, video_path)
                            logger.info(f"Скопировал файл напрямую из {api_file_path} в {video_path}")
                        except Exception as copy_err:
                            logger.error(f"Ошибка при копировании файла из локального Bot API: {copy_err}")
                            raise download_err
                    else:
                        raise download_err
                
                if video_path.exists() and video_path.stat().st_size > 0:
                    logger.info(f"Видео успешно загружено: {video_path} (размер: {video_path.stat().st_size} байт)")
                    await status_message.edit_text(
                        "Видео успешно загружено! Начинаю обработку... *радостно мурчит*"
                    )
                    await process_video(chat_id, message_id, update, context)
                else:
                    logger.error(f"Ошибка при скачивании видео: файл не существует или пустой")
                    await status_message.edit_text(
                        "Не удалось скачать видео. Пожалуйста, попробуйте снова. *печально опускает ушки*"
                    )
                    
            except Exception as e:
                logger.error(f"Ошибка при скачивании видео: {e}")
                if "File is too big" in str(e):
                    await status_message.edit_text(
                        "😿 Бот больше не имеет лимитов на размер файла, но **файл превышает лимит Telegram (≈ 2 ГБ)**. \n"
                        "Пожалуйста, пришлите прямую ссылку на файл — скоро добавим поддержку скачивания по URL."
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

async def process_video(chat_id: int, message_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает видео и отправляет результат."""
    video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
    await process_video_file(video_path, chat_id, message_id, context)

async def handle_summary_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик коллбэков для кнопок саммари."""
    query = update.callback_query
    await query.answer()
    
    try:
        # Получаем id сообщения
        message_id = query.data.split("_")[-1]
        
        # Определяем тип саммари
        summary_type = "подробное" if query.data.startswith("detailed_") else "краткое"
        
        # Отправляем сообщение о начале генерации
        status_message = await query.message.reply_text(
            f"Генерирую {summary_type} саммари для этого видео... *сосредоточенно обдумывает содержание*"
        )
        
        # Загружаем транскрипцию (видео или аудио)
        transcript_path = TRANSCRIPTIONS_DIR / f"telegram_video_{message_id}.txt"
        if not transcript_path.exists():
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_audio_{message_id}.txt"

        if not transcript_path.exists():
            await status_message.edit_text(
                "Мяу... Не могу найти транскрипцию для этого файла! 🔍 *растерянно оглядывается* Возможно, что-то пошло не так при обработке. Напишите @Like_a_duck - он разберётся! ️‍♂️"
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
                f"Мяу... Не удалось создать {summary_type} саммари! 😿 *виновато опускает уши* Что-то не так с моими киберсхемами. Сообщите @Like_a_duck - он всё починит! ⚡"
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
            await status_message.edit_text(
                f"Готово! {summary_type.capitalize()} саммари получилось объемным, отправляю файлом... *довольно мурлычет*"
            )
            
            with open(summary_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=f,
                    filename=f"{summary_type.capitalize()} саммари видео {message_id}.txt",
                    caption=f"Вот {summary_type} саммари для вашего видео! *гордо выпрямляется*"
                )
        else:
            # Иначе отправляем текстом
            await status_message.edit_text(
                f"Вот {summary_type} саммари для вашего видео:\n\n{summary}\n\n"
                f"@CyberKitty19_bot"
            )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки саммари {query.data}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Определяем summary_type для сообщения об ошибке
        summary_type = "подробное" if query.data.startswith("detailed_") else "краткое"
        
        await query.message.reply_text(
            f"Ой-ой! Произошла киберошибка при генерации {summary_type} саммари! 🤖💥 *смущенно прячет мордочку* \n\nРасскажите @Like_a_duck что случилось - он разберётся с моими схемами! 🔧\n\nДетали: {str(e)}"
        ) 