"""
Обработчики сообщений для CyberKitty Transkribator
"""

import asyncio
import tempfile
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    logger, MAX_FILE_SIZE_MB, VIDEOS_DIR, AUDIO_DIR, TRANSCRIPTIONS_DIR
)
from transkribator_modules.audio.extractor import extract_audio_from_video, compress_audio_for_api
from transkribator_modules.transcribe.transcriber import transcribe_audio

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
        
        # Отправляем уведомление о начале обработки
        status_msg = await update.message.reply_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"⏳ Скачиваю файл...",
            parse_mode='Markdown'
        )
        
        # Скачиваем файл
        file_obj = await context.bot.get_file(video_file.file_id)
        
        # Создаем временные пути
        video_path = VIDEOS_DIR / f"telegram_video_{video_file.file_id}.mp4"
        audio_path = AUDIO_DIR / f"telegram_audio_{video_file.file_id}.wav"
        
        # Скачиваем файл
        await file_obj.download_to_drive(video_path)
        
        # Обновляем статус
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🎵 Извлекаю аудио...",
            parse_mode='Markdown'
        )
        
        # Извлекаем аудио
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
        
        compressed_audio = await compress_audio_for_api(audio_path)
        
        # Транскрибируем
        await status_msg.edit_text(
            f"🎬 **Обрабатываю видео:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🤖 Создаю транскрипцию...",
            parse_mode='Markdown'
        )
        
        transcript = await transcribe_audio(compressed_audio)
        
        if transcript:
            # Сохраняем транскрипцию
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{video_file.file_id}.txt"
            transcript_path.write_text(transcript, encoding='utf-8')
            
            # Отправляем результат
            await status_msg.edit_text("✅ Транскрипция готова!")
            
            # Если текст короткий, отправляем в сообщении
            if len(transcript) <= 4000:
                await update.message.reply_text(
                    f"📝 **Транскрипция:**\n\n{transcript}",
                    parse_mode='Markdown'
                )
            else:
                # Если длинный, отправляем файлом
                await update.message.reply_document(
                    document=transcript_path,
                    filename=f"transcript_{filename}.txt",
                    caption="📝 Транскрипция готова!"
                )
        else:
            await status_msg.edit_text("❌ Не удалось создать транскрипцию")
        
        # Очищаем временные файлы
        try:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            if compressed_audio != audio_path:
                compressed_audio.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Не удалось удалить временные файлы: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        await update.message.reply_text(f"❌ Ошибка при обработке видео: {str(e)}")

async def process_audio_file(update: Update, context: ContextTypes.DEFAULT_TYPE, audio_file) -> None:
    """Обрабатывает аудио файл"""
    try:
        file_size_mb = audio_file.file_size / (1024 * 1024) if audio_file.file_size else 0
        filename = getattr(audio_file, 'file_name', f"audio_{audio_file.file_id}")
        
        # Отправляем уведомление о начале обработки
        status_msg = await update.message.reply_text(
            f"🎵 **Обрабатываю аудио:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"⏳ Скачиваю файл...",
            parse_mode='Markdown'
        )
        
        # Скачиваем файл
        file_obj = await context.bot.get_file(audio_file.file_id)
        
        # Создаем временный путь
        audio_path = AUDIO_DIR / f"telegram_audio_{audio_file.file_id}.mp3"
        
        # Скачиваем файл
        await file_obj.download_to_drive(audio_path)
        
        # Сжимаем если нужно
        await status_msg.edit_text(
            f"🎵 **Обрабатываю аудио:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🗜️ Подготавливаю аудио...",
            parse_mode='Markdown'
        )
        
        processed_audio = await compress_audio_for_api(audio_path)
        
        # Транскрибируем
        await status_msg.edit_text(
            f"🎵 **Обрабатываю аудио:** {filename}\n"
            f"📊 **Размер:** {file_size_mb:.1f} МБ\n\n"
            f"🤖 Создаю транскрипцию...",
            parse_mode='Markdown'
        )
        
        transcript = await transcribe_audio(processed_audio)
        
        if transcript:
            # Сохраняем транскрипцию
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{audio_file.file_id}.txt"
            transcript_path.write_text(transcript, encoding='utf-8')
            
            # Отправляем результат
            await status_msg.edit_text("✅ Транскрипция готова!")
            
            # Если текст короткий, отправляем в сообщении
            if len(transcript) <= 4000:
                await update.message.reply_text(
                    f"📝 **Транскрипция:**\n\n{transcript}",
                    parse_mode='Markdown'
                )
            else:
                # Если длинный, отправляем файлом
                await update.message.reply_document(
                    document=transcript_path,
                    filename=f"transcript_{filename}.txt",
                    caption="📝 Транскрипция готова!"
                )
        else:
            await status_msg.edit_text("❌ Не удалось создать транскрипцию")
        
        # Очищаем временные файлы
        try:
            audio_path.unlink(missing_ok=True)
            if processed_audio != audio_path:
                processed_audio.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Не удалось удалить временные файлы: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при обработке аудио: {e}")
        await update.message.reply_text(f"❌ Ошибка при обработке аудио: {str(e)}") 