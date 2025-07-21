import asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
import re
from urllib.parse import urlparse
import httpx
import os
import time

from transkribator_modules.config import (
    logger, user_transcriptions, VIDEOS_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH, AUDIO_DIR, BOT_TOKEN
)
from transkribator_modules.utils.processor import process_video, process_video_file, process_audio_file, process_video_file_silent, process_audio_file_silent
from transkribator_modules.utils.downloader import download_media
from transkribator_modules.utils.large_file_downloader import download_large_file, get_file_info

# --- Функции для работы с API сервером ---

async def send_file_to_api_server(file_path: Path, chat_id: int, message_id: int, file_type: str) -> dict:
    """Отправляет файл в API сервер для обработки"""
    try:
        api_url = os.getenv("API_SERVER_URL", "http://api:8000")
        
        # Создаем API ключ для бота (если нужно)
        api_key = await get_or_create_bot_api_key()
        
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            data = {
                "format_with_llm": "true",
                "chat_id": str(chat_id),
                "message_id": str(message_id)
            }
            headers = {"X-API-Key": api_key}
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{api_url}/transcribe",
                    files=files,
                    data=data,
                    headers=headers
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(f"API сервер вернул ошибку: {response.status_code} - {response.text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Ошибка при отправке файла в API сервер: {e}")
        return None

async def get_or_create_bot_api_key() -> str:
    """Получает или создает API ключ для бота"""
    # Используем ключ из переменной окружения или дефолтный
    import os
    return os.getenv('LOCAL_API_KEY', 'cyberkitty_local_api_key_2024')





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
    """Обработчик всех сообщений"""
    print("=== ПОЛУЧЕНО СООБЩЕНИЕ ===")
    print(f"Пользователь: {update.effective_user.id}")
    print(f"Chat ID: {update.effective_chat.id}")
    print(f"Тип чата: {update.effective_chat.type}")
    
    # Определяем тип сообщения
    message_type = "text"
    if update.message.video:
        message_type = "video"
    elif update.message.audio:
        message_type = "audio"
    elif update.message.document:
        message_type = "document"
    
    print(f"Тип сообщения: {message_type}")
    
    if update.message.video:
        print("=== ЭТО ВИДЕО! ===")
        print(f"Размер видео: {update.message.video.file_size}")
        print(f"File ID: {update.message.video.file_id}")
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    chat_type = update.effective_chat.type
    
    print(f"Обрабатываю сообщение для пользователя {user_id} в чате {chat_id}")
    
    # Проверяем, является ли пользователь администратором
    # ADMIN_IDS = [123456789, 987654321] # Placeholder for actual admin IDs
    # if user_id in ADMIN_IDS:
    #     print("Пользователь является администратором")
    #     # Для администраторов - полная функциональность
    #     await handle_admin_message(update, context)
    # else:
    #     print("Пользователь НЕ является администратором")
    #     # Для обычных пользователей - минимальная функциональность
    #     await handle_regular_user_message(update, context)

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
        # --- Фикс: не реагировать на промокоды в группах ---
        if chat_type in ['group', 'supergroup']:
            pass  # Игнорируем текстовые сообщения в группах
        else:
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
            # В группах - без статусных сообщений и меню
            audio_file = await context.bot.get_file(update.message.voice.file_id if update.message.voice else update.message.audio.file_id)
            audio_path = AUDIO_DIR / f"telegram_audio_{message_id}_chat_{chat_id}{Path(audio_file.file_path).suffix or '.ogg'}"
            await audio_file.download_to_drive(custom_path=audio_path)
            await process_audio_file_silent(audio_path, chat_id, message_id, context, user_username=update.effective_user.username, user_id=update.effective_user.id)
            return
        else:
            # В личном чате - как в продакшн-версии
            status_message = await update.message.reply_text(
                "Мяу! Вижу аудио! Скачиваю его... *возбужденно виляет хвостом*"
            )
            audio_file = await context.bot.get_file(update.message.voice.file_id if update.message.voice else update.message.audio.file_id)
            audio_path = AUDIO_DIR / f"telegram_audio_{message_id}_chat_{chat_id}{Path(audio_file.file_path).suffix or '.ogg'}"
            await audio_file.download_to_drive(custom_path=audio_path)
            await status_message.edit_text(
                "Аудио успешно загружено! Начинаю обработку... *радостно мурчит*"
            )
            from transkribator_modules.utils.processor import process_audio_file
            await process_audio_file(audio_path, chat_id, message_id, context, status_message=status_message)
            return

    elif update.message.document and update.message.document.mime_type:
        mime = update.message.document.mime_type
        if mime.startswith('video/') or mime.startswith('audio/'):
            if chat_type in ['group', 'supergroup']:
                # В группах - без статусных сообщений и меню
                doc_file = await context.bot.get_file(update.message.document.file_id)
                ext = Path(doc_file.file_path).suffix or ''.join(['.', mime.split('/')[-1]])
                if mime.startswith('audio/'):
                    local_path = AUDIO_DIR / f"telegram_audio_{message_id}_chat_{chat_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_audio_file_silent(local_path, chat_id, message_id, context, user_username=update.effective_user.username, user_id=update.effective_user.id)
                else:
                    local_path = VIDEOS_DIR / f"telegram_video_{message_id}_chat_{chat_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await process_video_file_silent(local_path, chat_id, message_id, context, user_username=update.effective_user.username, user_id=update.effective_user.id)
                return
            else:
                # В личном чате - как в продакшн-версии
                status_message = await update.message.reply_text(
                    "Мяу! Вижу файл! Скачиваю его... *возбужденно виляет хвостом*"
                )
                doc_file = await context.bot.get_file(update.message.document.file_id)
                ext = Path(doc_file.file_path).suffix or ''.join(['.', mime.split('/')[-1]])
                if mime.startswith('audio/'):
                    local_path = AUDIO_DIR / f"telegram_audio_{message_id}_chat_{chat_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await status_message.edit_text(
                        "Аудио файл успешно загружен! Начинаю обработку... *радостно мурчит*"
                    )
                    from transkribator_modules.utils.processor import process_audio_file
                    await process_audio_file(local_path, chat_id, message_id, context, status_message=status_message)
                else:
                    local_path = VIDEOS_DIR / f"telegram_video_{message_id}_chat_{chat_id}{ext}"
                    await doc_file.download_to_drive(custom_path=local_path)
                    await status_message.edit_text(
                        "Видео файл успешно загружен! Начинаю обработку... *радостно мурчит*"
                    )
                    from transkribator_modules.utils.processor import process_video_file
                    await process_video_file(local_path, chat_id, message_id, context, status_message=status_message)
            return

    if update.message.video:
        if chat_type in ['group', 'supergroup']:
            # В группах - сразу обработка видео без меню и статусных сообщений
            await process_video_file_silent(update.message.video, chat_id, message_id, context, user_username=update.effective_user.username, user_id=update.effective_user.id)
            return
        else:
            logger.info(f"Получено видео от пользователя {user_id}")
            await process_video_file_direct(update, context, update.message.video)
            return

    # В минимальном режиме просто отвечаем текстом (только в личных чатах)
    if chat_type not in ['group', 'supergroup']:
        await update.message.reply_text(
            "Мяу! *игриво смотрит* Отправь мне видео, и я создам текстовую расшифровку! *виляет хвостиком*"
        ) 

async def save_file_info_for_local_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, file_type: str) -> None:
    """Сохраняет информацию о файле для обработки локальным ботом."""
    try:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        message_id = update.message.message_id
        
        # Создаем файл с информацией о том, что нужно обработать
        if file_type == "video":
            info_file = VIDEOS_DIR / f"pending_{file_type}_{message_id}.txt"
        else:
            info_file = AUDIO_DIR / f"pending_{file_type}_{message_id}.txt"
        with open(info_file, "w", encoding="utf-8") as f:
            f.write(f"user_id={user_id}\n")
            f.write(f"chat_id={chat_id}\n")
            f.write(f"message_id={message_id}\n")
            f.write(f"file_type={file_type}\n")
            f.write(f"timestamp={update.message.date.isoformat()}\n")
        
        logger.info(f"Сохранена информация о файле {file_type} для локального бота: {info_file}")
        
    except Exception as e:
        logger.error(f"Ошибка при сохранении информации о файле для локального бота: {e}")

async def process_video(chat_id: int, message_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает видео и отправляет результат."""
    video_path = VIDEOS_DIR / f"telegram_video_{message_id}.mp4"
    await process_video_file(video_path, chat_id, message_id, context)

async def process_video_file_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, video_file) -> None:
    """Обрабатывает видео файл напрямую (рабочая версия)"""
    try:
        file_size_mb = video_file.file_size / (1024 * 1024) if video_file.file_size else 0
        filename = getattr(video_file, 'file_name', f"video_{video_file.file_id}")
        
        # Отправляем уведомление о начале обработки
        status_msg = await update.message.reply_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"⏳ Скачиваю файл...",
            parse_mode='Markdown'
        )
        
        # Создаем временные пути
        video_path = VIDEOS_DIR / f"telegram_video_{video_file.file_id}.mp4"
        audio_path = AUDIO_DIR / f"telegram_audio_{video_file.file_id}.wav"
        
        # Обновляем статус с информацией о скачивании
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"⬇️ Скачиваю файл... (это может занять несколько минут)",
            parse_mode='Markdown'
        )
        
        # Скачиваем файл через нашу утилиту для больших файлов
        logger.info(f"📥 Начинаю скачивание файла {filename} размером {file_size_mb:.1f} МБ")
        
        success = await download_large_file(
            bot_token=BOT_TOKEN,
            file_id=video_file.file_id,
            destination=video_path
        )
        
        if not success:
            await status_msg.edit_text("❌ Не удалось скачать файл")
            return
            
        logger.info(f"✅ Файл {filename} успешно скачан")
        
        # Обновляем статус
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🎵 Извлекаю аудио...",
            parse_mode='Markdown'
        )
        
        # Извлекаем аудио
        from transkribator_modules.audio.extractor import extract_audio_from_video
        if not await extract_audio_from_video(video_path, audio_path):
            await status_msg.edit_text("❌ Не удалось извлечь аудио из видео")
            return
        
        # Сжимаем аудио
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🗜️ Сжимаю аудио...",
            parse_mode='Markdown'
        )
        
        from transkribator_modules.audio.extractor import compress_audio_for_api
        compressed_audio = await compress_audio_for_api(audio_path)
        
        # Транскрибируем
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🤖 Создаю транскрипцию...",
            parse_mode='Markdown'
        )
        
        from transkribator_modules.transcribe.transcriber import transcribe_audio
        transcript = await transcribe_audio(compressed_audio)
        
        if transcript:
            # Форматируем транскрипцию
            from transkribator_modules.transcribe.transcriber import format_transcript_with_llm
            formatted_transcript = await format_transcript_with_llm(transcript)
            
            # Используем унифицированную функцию с кнопками
            from transkribator_modules.utils.processor import send_transcription_result
            
            await send_transcription_result(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
                formatted_transcript=formatted_transcript,
                raw_transcript=transcript,
                media_prefix="telegram_video",
                context=context,
                status_message=status_msg,
            )
        else:
            await status_msg.edit_text("❌ Не удалось создать транскрипцию")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка при обработке видео: {e}")
        
        # Более информативные сообщения об ошибках
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            await update.message.reply_text(
                f"⏰ **Таймаут при скачивании файла**\n\n"
                f"Файл размером {file_size_mb:.1f} МБ слишком долго скачивается.\n"
                f"Это может происходить из-за медленного интернета или больших размеров файла.\n\n"
                f"💡 **Рекомендации:**\n"
                f"• Попробуйте файл поменьше (до 100 МБ)\n"
                f"• Проверьте скорость интернета\n"
                f"• Повторите попытку через несколько минут",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ **Ошибка при обработке видео**\n\n"
                f"Произошла непредвиденная ошибка: {error_msg}\n\n"
                f"Пожалуйста, попробуйте еще раз или обратитесь к администратору.",
                parse_mode='Markdown'
            )

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
                "Мяу... Не могу найти транскрипцию для этого файла! 🔍 *растерянно оглядывается* Возможно, что-то пошло не так при обработке. Напишите @Like\\_a\\_duck - он разберётся! ️‍♂️"
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
                f"Мяу... Не удалось создать {summary_type} саммари! 😿 *виновато опускает уши* Что-то не так с моими киберсхемами. Сообщите @Like\\_a\\_duck - он всё починит! ⚡"
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
            f"Ой-ой! Произошла киберошибка при генерации {summary_type} саммари! 🤖💥 *смущенно прячет мордочку* \n\nРасскажите @Like\\_a\\_duck что случилось - он разберётся с моими схемами! 🔧\n\nДетали: {str(e)}"
        ) 

