"""
Обработчики сообщений для CyberKitty Transkribator
"""

import asyncio
import tempfile
import html
import re
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger, MAX_FILE_SIZE_MB, VIDEOS_DIR, AUDIO_DIR, TRANSCRIPTIONS_DIR, BOT_TOKEN
)
from transkribator_modules.audio.extractor import extract_audio_from_video, compress_audio_for_api
from transkribator_modules.transcribe.transcriber import transcribe_audio, format_transcript_with_llm, _basic_local_format
from transkribator_modules.utils.large_file_downloader import download_large_file, get_file_info

def clean_html_entities(text: str) -> str:
    """Минимальная очистка текста: только удаление HTML-тегов.
    Не удаляем не-ASCII, чтобы не портить кириллицу. parse_mode=None.
    """
    if not text:
        return text
    return re.sub(r'<[^>]*>', '', text)

# Поддерживаемые форматы
VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v', '.3gp'}
AUDIO_FORMATS = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma', '.opus'}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    welcome_text = """🎬 **CyberKitty Transkribator** 🐱

Привет! Я умею транскрибировать видео и аудио файлы любого размера!

**Что я умею:**
🎥 Обрабатывать видео до 2 ГБ
🎵 Работать с аудио файлами
📝 Создавать качественные транскрипции
🤖 Форматировать текст с помощью ИИ

**Как пользоваться:**
1. Отправьте мне видео или аудио файл
2. Подождите, пока я обработаю файл
3. Получите готовую транскрипцию!

Поддерживаемые форматы:
• Видео: MP4, AVI, MOV, MKV, WebM и другие
• Аудио: MP3, WAV, FLAC, AAC, OGG и другие

Отправьте /help для подробной помощи."""

    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """📖 **Справка по CyberKitty Transkribator**

**Основные возможности:**
• Транскрипция видео и аудио файлов
• Поддержка файлов до 2 ГБ
• Автоматическое извлечение аудио из видео
• ИИ-форматирование текста

**Команды:**
/start - Начать работу
/help - Показать эту справку
/status - Проверить статус бота

**Поддерживаемые форматы:**

🎥 **Видео:** MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V, 3GP
🎵 **Аудио:** MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS

**Ограничения:**
• Максимальный размер файла: 2 ГБ
• Максимальная длительность: 4 часа

**Как это работает:**
1. Вы отправляете файл
2. Если это видео - я извлекаю аудио
3. Аудио отправляется в AI API для транскрипции
4. Текст форматируется с помощью LLM
5. Вы получаете готовую транскрипцию

Просто отправьте файл и я начну обработку! 🚀"""

    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /status"""
    status_text = """✅ **Статус CyberKitty Transkribator**

🤖 Бот: Активен
🌐 Telegram Bot API Server: Активен
🎵 Обработка аудио: Доступна
🎥 Обработка видео: Доступна
🧠 ИИ транскрипция: Подключена
📝 ИИ форматирование: Активно

**Настройки:**
• Макс. размер файла: 2 ГБ
• Макс. длительность: 4 часа
• Форматы видео: 9 поддерживаемых
• Форматы аудио: 8 поддерживаемых

Готов к работе! 🚀"""

    await update.message.reply_text(status_text, parse_mode='Markdown')

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик документов (файлов)"""
    document = update.message.document
    
    if not document:
        await update.message.reply_text("❌ Не удалось получить информацию о файле.")
        return
    
    # Проверяем размер файла
    file_size_mb = document.file_size / (1024 * 1024) if document.file_size else 0
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Файл слишком большой: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return
    
    # Определяем тип файла по расширению
    file_extension = Path(document.file_name).suffix.lower() if document.file_name else ''
    
    if file_extension in VIDEO_FORMATS:
        await process_video_file(update, context, document)
    elif file_extension in AUDIO_FORMATS:
        await process_audio_file(update, context, document)
    else:
        await update.message.reply_text(
            f"❌ Неподдерживаемый формат файла: {file_extension}\n\n"
            f"Поддерживаемые форматы:\n"
            f"🎥 Видео: {', '.join(sorted(VIDEO_FORMATS))}\n"
            f"🎵 Аудио: {', '.join(sorted(AUDIO_FORMATS))}"
        )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик видео файлов"""
    video = update.message.video
    
    if not video:
        await update.message.reply_text("❌ Не удалось получить информацию о видео.")
        return
    
    # Проверяем размер файла
    file_size_mb = video.file_size / (1024 * 1024) if video.file_size else 0
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Видео слишком большое: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return
    
    await process_video_file(update, context, video)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик аудио файлов"""
    audio = update.message.audio or update.message.voice
    
    if not audio:
        await update.message.reply_text("❌ Не удалось получить информацию об аудио.")
        return
    
    # Проверяем размер файла
    file_size_mb = audio.file_size / (1024 * 1024) if audio.file_size else 0
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        await update.message.reply_text(
            f"❌ Аудио слишком большое: {file_size_mb:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE_MB} МБ"
        )
        return
    
    await process_audio_file(update, context, audio)

async def process_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE, video_file) -> None:
    """Обрабатывает видео файл"""
    try:
        file_size_mb = video_file.file_size / (1024 * 1024) if video_file.file_size else 0
        filename = getattr(video_file, 'file_name', f"video_{video_file.file_id}")

        # В группах не показываем статусные сообщения
        is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
        status_msg = None
        if not is_group:
            status_msg = await update.message.reply_text(
                f"🎬 Обрабатываю видео: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"⏳ Скачиваю файл..."
            )
        
        # Создаем временные пути
        video_path = VIDEOS_DIR / f"telegram_video_{video_file.file_id}.mp4"
        audio_path = AUDIO_DIR / f"telegram_audio_{video_file.file_id}.wav"
        
        # Обновляем статус с информацией о скачивании
        if status_msg:
            await status_msg.edit_text(
                f"🎬 Обрабатываю видео: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"⬇️ Скачиваю файл... (это может занять несколько минут)"
            )
        
        # Скачиваем файл через нашу утилиту для больших файлов
        logger.info(f"📥 Начинаю скачивание файла {filename} размером {file_size_mb:.1f} МБ")
        
        success = await download_large_file(
            bot_token=BOT_TOKEN,
            file_id=video_file.file_id,
            destination=video_path
        )
        
        if not success:
            if status_msg:
                await status_msg.edit_text("❌ Не удалось скачать файл")
            else:
                await update.message.reply_text("❌ Не удалось скачать файл")
            return
            
        logger.info(f"✅ Файл {filename} успешно скачан")
        
        # Обновляем статус
        if status_msg:
            await status_msg.edit_text(
                f"🎬 Обрабатываю видео: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"🎵 Извлекаю аудио..."
            )
        
        # Извлекаем аудио
        if not await extract_audio_from_video(video_path, audio_path):
            await status_msg.edit_text("❌ Не удалось извлечь аудио из видео")
            return
        
        # Сжимаем аудио
        if status_msg:
            await status_msg.edit_text(
                f"🎬 Обрабатываю видео: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"🗜️ Сжимаю аудио..."
            )
        
        compressed_audio = await compress_audio_for_api(audio_path)
        
        # Транскрибируем
        if status_msg:
            await status_msg.edit_text(
                f"🎬 Обрабатываю видео: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"🤖 Создаю транскрипцию..."
            )
        
        transcript = await transcribe_audio(compressed_audio)
        # Форматируем транскрипт для читаемости (OpenRouter/DeepSeek) с локальным fallback
        logger.info("Запускаю LLM-форматирование транскрипта (video)")
        formatted_transcript = None
        try:
            formatted_transcript = await format_transcript_with_llm(transcript)
        except Exception as e:
            logger.warning(f"LLM-форматирование (video) исключение: {e}")
        if not formatted_transcript:
            logger.info("LLM недоступен/неверный ключ — применяю локальное форматирование")
            formatted_transcript = _basic_local_format(transcript)
        
        # Проверяем результат до сохранения и отправки
        if formatted_transcript and formatted_transcript.strip():
            # Сохраняем транскрипцию (уже отформатированную)
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{video_file.file_id}.txt"
            transcript_path.write_text(formatted_transcript or "", encoding='utf-8')
            
            # Отправляем результат
            if status_msg:
                await status_msg.edit_text("✅ Транскрипция готова!")
            
            # Если текст короткий, отправляем в сообщении
            if len(formatted_transcript or "") <= 4000:
                # Очищаем текст от HTML-сущностей для безопасной отправки
                clean_transcript = clean_html_entities((formatted_transcript or ""))
                await update.message.reply_text(
                    f"📝 Транскрипция:\n\n{clean_transcript}"
                )
            else:
                # Если длинный, отправляем .docx
                from docx import Document
                docx_path = TRANSCRIPTIONS_DIR / f"transcript_{Path(filename).stem}.docx"
                document = Document()
                for line in (formatted_transcript or "").split('\n'):
                    document.add_paragraph(line)
                document.save(docx_path)
                with open(docx_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=docx_path.name,
                        caption="📝 Транскрипция готова!"
                    )
        else:
            if status_msg:
                await status_msg.edit_text("❌ Не удалось создать транскрипцию")
            else:
                await update.message.reply_text("❌ Не удалось создать транскрипцию")
        
        # Очищаем временные файлы
        try:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            if compressed_audio != audio_path:
                compressed_audio.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Не удалось удалить временные файлы: {e}")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка при обработке видео: {e}")
        
        # Более информативные сообщения об ошибках
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            await update.message.reply_text(
                f"⏰ Таймаут при скачивании файла\n\n"
                f"Файл размером {file_size_mb:.1f} МБ слишком долго скачивается.\n"
                f"Это может происходить из-за медленного интернета или больших размеров файла.\n\n"
                f"💡 Рекомендации:\n"
                f"• Попробуйте файл поменьше (до 100 МБ)\n"
                f"• Проверьте скорость интернета\n"
                f"• Повторите попытку через несколько минут"
            )
        else:
            await update.message.reply_text(f"❌ Ошибка при обработке видео: {error_msg}")

async def process_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE, audio_file) -> None:
    """Обрабатывает аудио файл"""
    try:
        file_size_mb = audio_file.file_size / (1024 * 1024) if audio_file.file_size else 0
        filename = getattr(audio_file, 'file_name', f"audio_{audio_file.file_id}")
        
        # В группах не показываем статусные сообщения
        is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
        status_msg = None
        if not is_group:
            status_msg = await update.message.reply_text(
                f"🎵 Обрабатываю аудио: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"⏳ Скачиваю файл..."
            )
        
        # Создаем временный путь
        audio_path = AUDIO_DIR / f"telegram_audio_{audio_file.file_id}.mp3"
        
        # Обновляем статус с информацией о скачивании
        if status_msg:
            await status_msg.edit_text(
                f"🎵 Обрабатываю аудио: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"⬇️ Скачиваю файл... (это может занять несколько минут)"
            )
        
        # Скачиваем файл через нашу утилиту для больших файлов
        logger.info(f"📥 Начинаю скачивание файла {filename} размером {file_size_mb:.1f} МБ")
        
        success = await download_large_file(
            bot_token=BOT_TOKEN,
            file_id=audio_file.file_id,
            destination=audio_path
        )
        
        if not success:
            if status_msg:
                await status_msg.edit_text("❌ Не удалось скачать файл")
            else:
                await update.message.reply_text("❌ Не удалось скачать файл")
            return
            
        logger.info(f"✅ Файл {filename} успешно скачан")
        
        # Сжимаем если нужно
        if status_msg:
            await status_msg.edit_text(
                f"🎵 Обрабатываю аудио: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"🗜️ Подготавливаю аудио..."
            )
        
        processed_audio = await compress_audio_for_api(audio_path)
        
        # Транскрибируем
        if status_msg:
            await status_msg.edit_text(
                f"🎵 Обрабатываю аудио: {filename}\n"
                f"📊 Размер: {file_size_mb:.1f} МБ\n\n"
                f"🤖 Создаю транскрипцию..."
            )
        
        transcript = await transcribe_audio(processed_audio)
        # Форматируем транскрипт для читаемости (OpenRouter/DeepSeek) с локальным fallback
        logger.info("Запускаю LLM-форматирование транскрипта (audio)")
        formatted_transcript = None
        try:
            formatted_transcript = await format_transcript_with_llm(transcript)
        except Exception as e:
            logger.warning(f"LLM-форматирование (audio) исключение: {e}")
        if not formatted_transcript:
            logger.info("LLM недоступен/неверный ключ — применяю локальное форматирование")
            formatted_transcript = _basic_local_format(transcript)
        
        if formatted_transcript and formatted_transcript.strip():
            # Сохраняем транскрипцию (уже отформатированную)
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{audio_file.file_id}.txt"
            transcript_path.write_text(formatted_transcript or "", encoding='utf-8')
            
            # Отправляем результат
            if status_msg:
                await status_msg.edit_text("✅ Транскрипция готова!")
            
            # Если текст короткий, отправляем в сообщении
            if len(formatted_transcript or "") <= 4000:
                # Очищаем текст от HTML-сущностей для безопасной отправки
                clean_transcript = clean_html_entities(formatted_transcript or "")
                await update.message.reply_text(
                    f"📝 Транскрипция:\н\n{clean_transcript}"
                )
            else:
                # Если длинный, отправляем .docx
                from docx import Document
                docx_path = TRANSCRIPTIONS_DIR / f"transcript_{Path(filename).stem}.docx"
                document = Document()
                for line in (formatted_transcript or "").split('\n'):
                    document.add_paragraph(line)
                document.save(docx_path)
                with open(docx_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=docx_path.name,
                        caption="📝 Транскрипция готова!"
                    )
        else:
            if status_msg:
                await status_msg.edit_text("❌ Не удалось создать транскрипцию")
            else:
                await update.message.reply_text("❌ Не удалось создать транскрипцию")
        
        # Очищаем временные файлы
        try:
            audio_path.unlink(missing_ok=True)
            if processed_audio != audio_path:
                processed_audio.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Не удалось удалить временные файлы: {e}")
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка при обработке аудио: {e}")
        
        # Более информативные сообщения об ошибках
        if "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
            await update.message.reply_text(
                f"⏰ Таймаут при скачивании файла\n\n"
                f"Файл размером {file_size_mb:.1f} МБ слишком долго скачивается.\n"
                f"Это может происходить из-за медленного интернета или больших размеров файла.\n\n"
                f"💡 Рекомендации:\n"
                f"• Попробуйте файл поменьше (до 100 МБ)\n"
                f"• Проверьте скорость интернета\n"
                f"• Повторите попытку через несколько минут"
            )
        else:
            await update.message.reply_text(f"❌ Ошибка при обработке аудио: {error_msg}")

# Убрали обработчик кнопок сырой транскрипции по требованию — сосредотачиваемся на основной выдаче

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Интегрированный обработчик для всех типов сообщений с поддержкой Bot API Server."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Логируем сообщение
    logger.info(f"Получено сообщение от пользователя {user_id} в чате {chat_id}")
    
    # Обработка видео
    if update.message.video:
        logger.info(f"Получено видео от пользователя {user_id}")
        # Запускаем локальный обработчик видео (скачивание и обработка)
        await process_video_file(update, context, update.message.video)
        return
    
    # Обработка аудио
    if update.message.audio:
        logger.info(f"Получено аудио от пользователя {user_id}")
        await process_audio_file(update, context, update.message.audio)
        return
    
    # Обработка голосовых сообщений
    if update.message.voice:
        logger.info(f"Получено голосовое сообщение от пользователя {user_id}")
        await process_audio_file(update, context, update.message.voice)
        return
    
    # Обработка документов (видео/аудио файлы)
    if update.message.document:
        document = update.message.document
        filename = document.file_name.lower() if document.file_name else ""
        
        # Проверяем, является ли документ видео или аудио
        if any(ext in filename for ext in VIDEO_FORMATS):
            logger.info(f"Получен видео-документ от пользователя {user_id}: {filename}")
            await process_video_file(update, context, document)
            return
        elif any(ext in filename for ext in AUDIO_FORMATS):
            logger.info(f"Получен аудио-документ от пользователя {user_id}: {filename}")
            await process_audio_file(update, context, document)
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