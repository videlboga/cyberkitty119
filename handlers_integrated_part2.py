async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Интегрированный обработчик для всех типов сообщений с поддержкой Bot API Server."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Логируем сообщение
    logger.info(f"Получено сообщение от пользователя {user_id}")
    
    # Обработка промокодов (если сообщение является текстом и выглядит как промокод)
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

    # Обработка видео файлов
    if update.message.video:
        await handle_video_message(update, context)
        return
    
    # Обработка документов (включая видео файлы, отправленные как документы)
    if update.message.document:
        await handle_document_message(update, context)
        return
    
    # Обработка голосовых сообщений
    if update.message.voice:
        await handle_voice_message(update, context)
        return
    
    # Обработка аудио файлов
    if update.message.audio:
        await handle_audio_message(update, context)
        return
    
    # Если это обычное текстовое сообщение, отвечаем дружелюбно
    if update.message.text:
        await update.message.reply_text(
            "Привет! 🐱 Отправь мне видео или аудио файл, и я создам для тебя транскрипцию!\n\n"
            "Поддерживаемые форматы:\n"
            "📹 Видео: MP4, AVI, MOV, MKV и другие\n"
            "🎵 Аудио: MP3, WAV, M4A, OGG и другие\n"
            "🎤 Голосовые сообщения\n\n"
            "Максимальный размер файла: 2 ГБ\n"
            "Максимальная длительность: 4 часа\n\n"
            "Используй /help для получения дополнительной информации!"
        )

async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает видео сообщения с использованием Bot API Server."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    video = update.message.video
    
    logger.info(f"📹 Получено видео от пользователя {user_id}: {video.file_name or 'без имени'}")
    
    # Проверяем размер файла
    file_size_mb = video.file_size / (1024 * 1024) if video.file_size else 0
    logger.info(f"📊 Размер видео: {file_size_mb:.1f} МБ")
    
    if file_size_mb > 2000:  # 2 ГБ лимит
        await update.message.reply_text(
            f"❌ Файл слишком большой ({file_size_mb:.1f} МБ)!\n"
            f"Максимальный размер: 2000 МБ\n\n"
            f"*виновато опускает уши*"
        )
        return
    
    # Проверяем длительность
    if video.duration and video.duration > 14400:  # 4 часа
        duration_hours = video.duration / 3600
        await update.message.reply_text(
            f"❌ Видео слишком длинное ({duration_hours:.1f} часа)!\n"
            f"Максимальная длительность: 4 часа\n\n"
            f"*смущенно прячет мордочку*"
        )
        return
    
    # Отправляем сообщение о начале обработки
    status_message = await update.message.reply_text(
        f"📥 Начинаю скачивание видео...\n"
        f"📊 Размер: {file_size_mb:.1f} МБ\n"
        f"⏱️ Длительность: {video.duration // 60 if video.duration else '?'} мин\n\n"
        f"*сосредоточенно готовится к работе*"
    )
    
    try:
        # Скачиваем файл с использованием нового загрузчика
        filename = video.file_name or f"video{message_id}.mp4"
        logger.info(f"📥 Начинаю скачивание файла {filename} размером {file_size_mb:.1f} МБ")
        
        await status_message.edit_text(
            f"📥 Скачиваю видео {filename}...\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
            f"*усердно работает лапками*"
        )
        
        # Используем новый загрузчик файлов
        file_path = await download_large_file(
            context.bot, 
            video.file_id, 
            VIDEOS_DIR, 
            filename,
            status_message
        )
        
        if not file_path:
            await status_message.edit_text(
                "❌ Не удалось скачать видео файл\n\n"
                "*расстроенно опускает уши*"
            )
            return
        
        logger.info(f"✅ Файл успешно скачан: {file_path}")
        
        # Обрабатываем видео
        await status_message.edit_text(
            f"🎬 Видео скачано! Начинаю обработку...\n\n"
            f"*радостно мурчит и приступает к транскрибации*"
        )
        
        # Обрабатываем видео файл
        await process_video_file(file_path, chat_id, message_id, context, status_message)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке видео: {e}")
        await status_message.edit_text(
            f"❌ Произошла ошибка при обработке видео:\n{str(e)}\n\n"
            f"*виновато прячет мордочку*"
        )

async def handle_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает документы (включая видео файлы)."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    document = update.message.document
    
    # Проверяем, является ли документ видео файлом
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
    audio_extensions = {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.aac', '.wma'}
    
    file_name = document.file_name or ""
    file_ext = Path(file_name).suffix.lower()
    
    if file_ext in video_extensions:
        logger.info(f"📹 Получен видео документ от пользователя {user_id}: {file_name}")
        await handle_video_document(update, context, document)
    elif file_ext in audio_extensions:
        logger.info(f"🎵 Получен аудио документ от пользователя {user_id}: {file_name}")
        await handle_audio_document(update, context, document)
    else:
        await update.message.reply_text(
            f"❌ Неподдерживаемый тип файла: {file_ext}\n\n"
            f"Поддерживаемые форматы:\n"
            f"📹 Видео: {', '.join(video_extensions)}\n"
            f"🎵 Аудио: {', '.join(audio_extensions)}\n\n"
            f"*смущенно наклоняет голову*"
        )

async def handle_video_document(update: Update, context: ContextTypes.DEFAULT_TYPE, document) -> None:
    """Обрабатывает видео файлы, отправленные как документы."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Проверяем размер файла
    file_size_mb = document.file_size / (1024 * 1024) if document.file_size else 0
    logger.info(f"📊 Размер видео документа: {file_size_mb:.1f} МБ")
    
    if file_size_mb > 2000:  # 2 ГБ лимит
        await update.message.reply_text(
            f"❌ Файл слишком большой ({file_size_mb:.1f} МБ)!\n"
            f"Максимальный размер: 2000 МБ\n\n"
            f"*виновато опускает уши*"
        )
        return
    
    # Отправляем сообщение о начале обработки
    status_message = await update.message.reply_text(
        f"📥 Начинаю скачивание видео документа...\n"
        f"📊 Размер: {file_size_mb:.1f} МБ\n"
        f"📄 Файл: {document.file_name}\n\n"
        f"*сосредоточенно готовится к работе*"
    )
    
    try:
        # Скачиваем файл
        filename = document.file_name or f"video_doc{message_id}.mp4"
        logger.info(f"📥 Начинаю скачивание документа {filename} размером {file_size_mb:.1f} МБ")
        
        await status_message.edit_text(
            f"📥 Скачиваю видео документ {filename}...\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
            f"*усердно работает лапками*"
        )
        
        # Используем новый загрузчик файлов
        file_path = await download_large_file(
            context.bot, 
            document.file_id, 
            VIDEOS_DIR, 
            filename,
            status_message
        )
        
        if not file_path:
            await status_message.edit_text(
                "❌ Не удалось скачать видео документ\n\n"
                "*расстроенно опускает уши*"
            )
            return
        
        logger.info(f"✅ Документ успешно скачан: {file_path}")
        
        # Обрабатываем видео
        await status_message.edit_text(
            f"🎬 Видео документ скачан! Начинаю обработку...\n\n"
            f"*радостно мурчит и приступает к транскрибации*"
        )
        
        # Обрабатываем видео файл
        await process_video_file(file_path, chat_id, message_id, context, status_message)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке видео документа: {e}")
        await status_message.edit_text(
            f"❌ Произошла ошибка при обработке видео документа:\n{str(e)}\n\n"
            f"*виновато прячет мордочку*"
        ) 