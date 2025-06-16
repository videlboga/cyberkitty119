async def handle_audio_document(update: Update, context: ContextTypes.DEFAULT_TYPE, document) -> None:
    """Обрабатывает аудио файлы, отправленные как документы."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    
    # Проверяем размер файла
    file_size_mb = document.file_size / (1024 * 1024) if document.file_size else 0
    logger.info(f"📊 Размер аудио документа: {file_size_mb:.1f} МБ")
    
    if file_size_mb > 2000:  # 2 ГБ лимит
        await update.message.reply_text(
            f"❌ Файл слишком большой ({file_size_mb:.1f} МБ)!\n"
            f"Максимальный размер: 2000 МБ\n\n"
            f"*виновато опускает уши*"
        )
        return
    
    # Отправляем сообщение о начале обработки
    status_message = await update.message.reply_text(
        f"📥 Начинаю скачивание аудио документа...\n"
        f"📊 Размер: {file_size_mb:.1f} МБ\n"
        f"📄 Файл: {document.file_name}\n\n"
        f"*сосредоточенно готовится к работе*"
    )
    
    try:
        # Скачиваем файл
        filename = document.file_name or f"audio_doc{message_id}.mp3"
        logger.info(f"📥 Начинаю скачивание аудио документа {filename} размером {file_size_mb:.1f} МБ")
        
        await status_message.edit_text(
            f"📥 Скачиваю аудио документ {filename}...\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
            f"*усердно работает лапками*"
        )
        
        # Используем новый загрузчик файлов
        file_path = await download_large_file(
            context.bot, 
            document.file_id, 
            VIDEOS_DIR,  # Сохраняем в videos для совместимости с процессором
            filename,
            status_message
        )
        
        if not file_path:
            await status_message.edit_text(
                "❌ Не удалось скачать аудио документ\n\n"
                "*расстроенно опускает уши*"
            )
            return
        
        logger.info(f"✅ Аудио документ успешно скачан: {file_path}")
        
        # Обрабатываем аудио
        await status_message.edit_text(
            f"🎵 Аудио документ скачан! Начинаю обработку...\n\n"
            f"*радостно мурчит и приступает к транскрибации*"
        )
        
        # Обрабатываем аудио файл как видео (процессор универсальный)
        await process_video_file(file_path, chat_id, message_id, context, status_message)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке аудио документа: {e}")
        await status_message.edit_text(
            f"❌ Произошла ошибка при обработке аудио документа:\n{str(e)}\n\n"
            f"*виновато прячет мордочку*"
        )

async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает голосовые сообщения."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    voice = update.message.voice
    
    logger.info(f"🎤 Получено голосовое сообщение от пользователя {user_id}")
    
    # Проверяем размер файла
    file_size_mb = voice.file_size / (1024 * 1024) if voice.file_size else 0
    logger.info(f"📊 Размер голосового сообщения: {file_size_mb:.1f} МБ")
    
    if file_size_mb > 2000:  # 2 ГБ лимит
        await update.message.reply_text(
            f"❌ Голосовое сообщение слишком большое ({file_size_mb:.1f} МБ)!\n"
            f"Максимальный размер: 2000 МБ\n\n"
            f"*виновато опускает уши*"
        )
        return
    
    # Проверяем длительность
    if voice.duration and voice.duration > 14400:  # 4 часа
        duration_hours = voice.duration / 3600
        await update.message.reply_text(
            f"❌ Голосовое сообщение слишком длинное ({duration_hours:.1f} часа)!\n"
            f"Максимальная длительность: 4 часа\n\n"
            f"*смущенно прячет мордочку*"
        )
        return
    
    # Отправляем сообщение о начале обработки
    status_message = await update.message.reply_text(
        f"📥 Начинаю скачивание голосового сообщения...\n"
        f"📊 Размер: {file_size_mb:.1f} МБ\n"
        f"⏱️ Длительность: {voice.duration // 60 if voice.duration else '?'} мин\n\n"
        f"*внимательно слушает*"
    )
    
    try:
        # Скачиваем файл
        filename = f"voice{message_id}.ogg"
        logger.info(f"📥 Начинаю скачивание голосового сообщения размером {file_size_mb:.1f} МБ")
        
        await status_message.edit_text(
            f"📥 Скачиваю голосовое сообщение...\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
            f"*усердно работает лапками*"
        )
        
        # Используем новый загрузчик файлов
        file_path = await download_large_file(
            context.bot, 
            voice.file_id, 
            VIDEOS_DIR,  # Сохраняем в videos для совместимости с процессором
            filename,
            status_message
        )
        
        if not file_path:
            await status_message.edit_text(
                "❌ Не удалось скачать голосовое сообщение\n\n"
                "*расстроенно опускает уши*"
            )
            return
        
        logger.info(f"✅ Голосовое сообщение успешно скачано: {file_path}")
        
        # Обрабатываем голосовое сообщение
        await status_message.edit_text(
            f"🎤 Голосовое сообщение скачано! Начинаю обработку...\n\n"
            f"*радостно мурчит и приступает к транскрибации*"
        )
        
        # Обрабатываем аудио файл как видео (процессор универсальный)
        await process_video_file(file_path, chat_id, message_id, context, status_message)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке голосового сообщения: {e}")
        await status_message.edit_text(
            f"❌ Произошла ошибка при обработке голосового сообщения:\n{str(e)}\n\n"
            f"*виновато прячет мордочку*"
        )

async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает аудио файлы."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    message_id = update.message.message_id
    audio = update.message.audio
    
    logger.info(f"🎵 Получен аудио файл от пользователя {user_id}: {audio.file_name or 'без имени'}")
    
    # Проверяем размер файла
    file_size_mb = audio.file_size / (1024 * 1024) if audio.file_size else 0
    logger.info(f"📊 Размер аудио: {file_size_mb:.1f} МБ")
    
    if file_size_mb > 2000:  # 2 ГБ лимит
        await update.message.reply_text(
            f"❌ Файл слишком большой ({file_size_mb:.1f} МБ)!\n"
            f"Максимальный размер: 2000 МБ\n\n"
            f"*виновато опускает уши*"
        )
        return
    
    # Проверяем длительность
    if audio.duration and audio.duration > 14400:  # 4 часа
        duration_hours = audio.duration / 3600
        await update.message.reply_text(
            f"❌ Аудио слишком длинное ({duration_hours:.1f} часа)!\n"
            f"Максимальная длительность: 4 часа\n\n"
            f"*смущенно прячет мордочку*"
        )
        return
    
    # Отправляем сообщение о начале обработки
    status_message = await update.message.reply_text(
        f"📥 Начинаю скачивание аудио...\n"
        f"📊 Размер: {file_size_mb:.1f} МБ\n"
        f"⏱️ Длительность: {audio.duration // 60 if audio.duration else '?'} мин\n\n"
        f"*сосредоточенно готовится к работе*"
    )
    
    try:
        # Скачиваем файл
        filename = audio.file_name or f"audio{message_id}.mp3"
        logger.info(f"📥 Начинаю скачивание аудио файла {filename} размером {file_size_mb:.1f} МБ")
        
        await status_message.edit_text(
            f"📥 Скачиваю аудио {filename}...\n"
            f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
            f"*усердно работает лапками*"
        )
        
        # Используем новый загрузчик файлов
        file_path = await download_large_file(
            context.bot, 
            audio.file_id, 
            VIDEOS_DIR,  # Сохраняем в videos для совместимости с процессором
            filename,
            status_message
        )
        
        if not file_path:
            await status_message.edit_text(
                "❌ Не удалось скачать аудио файл\n\n"
                "*расстроенно опускает уши*"
            )
            return
        
        logger.info(f"✅ Аудио файл успешно скачан: {file_path}")
        
        # Обрабатываем аудио
        await status_message.edit_text(
            f"🎵 Аудио скачано! Начинаю обработку...\n\n"
            f"*радостно мурчит и приступает к транскрибации*"
        )
        
        # Обрабатываем аудио файл как видео (процессор универсальный)
        await process_video_file(file_path, chat_id, message_id, context, status_message)
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке аудио: {e}")
        await status_message.edit_text(
            f"❌ Произошла ошибка при обработке аудио:\n{str(e)}\n\n"
            f"*виновато прячет мордочку*"
        ) 