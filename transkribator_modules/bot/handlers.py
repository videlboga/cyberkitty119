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
            if status_msg:
                await status_msg.edit_text("❌ Не удалось извлечь аудио из видео")
            else:
                await update.message.reply_text("❌ Не удалось извлечь аудио из видео")
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
            if transcript:
                formatted_transcript = await format_transcript_with_llm(transcript)
        except Exception as e:
            logger.warning(f"LLM-форматирование (video) исключение: {e}")
        if not formatted_transcript and transcript:
            logger.info("LLM недоступен/неверный ключ — применяю локальное форматирование")
            formatted_transcript = _basic_local_format(transcript)

        # Проверяем результат до сохранения и отправки
        if formatted_transcript and formatted_transcript.strip():
            # Сохраняем транскрипцию (уже отформатированную)
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{video_file.file_id}.txt"
            transcript_path.write_text(formatted_transcript or "", encoding='utf-8')

            # Сохраняем в базу данных и обновляем счетчики
            try:
                from transkribator_modules.db.database import SessionLocal, UserService, TranscriptionService
                from transkribator_modules.db.database import get_media_duration

                db = SessionLocal()
                try:
                    user_service = UserService(db)
                    transcription_service = TranscriptionService(db)

                    # Получаем пользователя
                    user = user_service.get_or_create_user(
                        telegram_id=update.effective_user.id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name
                    )

                    # Получаем реальную длительность аудио из видео
                    duration_minutes = get_media_duration(str(audio_path))

                    # Сохраняем транскрипцию в базу
                    transcription_service.save_transcription(
                        user=user,
                        filename=filename,
                        file_size_mb=file_size_mb,
                        audio_duration_minutes=duration_minutes,
                        raw_transcript=transcript or "",
                        formatted_transcript=formatted_transcript or "",
                        processing_time=0.0,
                        transcription_service="deepinfra",
                        formatting_service="llm" if formatted_transcript != transcript else "none"
                    )

                    # Обновляем счетчики использования
                    user_service.add_usage(user, duration_minutes)

                    logger.info(f"✅ Транскрипция сохранена для пользователя {user.telegram_id}")

                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Ошибка при сохранении транскрипции: {e}")

            # Отправляем результат
            if status_msg:
                await status_msg.edit_text("✅ Транскрипция готова!")

            # Если текст короткий, отправляем в сообщении
            clean_transcript = clean_html_entities((formatted_transcript or ""))
            full_message = f"📝 Транскрипция:\n\n{clean_transcript}\n\n@CyberKitty19_bot"

            logger.info(f"Длина исходной транскрипции: {len(transcript or '')} символов")
            logger.info(f"Длина отформатированной транскрипции: {len(formatted_transcript or '')} символов")
            logger.info(f"Длина полного сообщения: {len(full_message)} символов")

            # Проверяем длину исходной транскрипции для решения о формате отправки
            if len(transcript or "") <= 4000:
                logger.info("Отправляем транскрипцию как текстовое сообщение")
                await update.message.reply_text(full_message)
            else:
                # Если длинный, отправляем .docx
                logger.info("Отправляем транскрипцию как .docx файл")
                from docx import Document
                # Убеждаемся, что директория существует
                TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
                docx_path = TRANSCRIPTIONS_DIR / f"transcript_{Path(filename).stem}.docx"
                document = Document()
                for line in (formatted_transcript or "").split('\n'):
                    document.add_paragraph(line)
                document.save(docx_path)
                logger.info(f"Создан .docx файл: {docx_path}")
                with open(docx_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=docx_path.name,
                        caption="📝 Транскрипция готова!\n\n@CyberKitty19_bot"
                    )

            # Создаем кнопки для дальнейших действий
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [
                    InlineKeyboardButton("🔧 Обработать", callback_data=f"process_transcript_{update.effective_user.id}"),
                    InlineKeyboardButton("📤 Прислать ещё", callback_data=f"send_more_{update.effective_user.id}")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data=f"main_menu_{update.effective_user.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем сообщение с кнопками
            await update.message.reply_text(
                "Что дальше будем с этим делать? 🤔",
                reply_markup=reply_markup
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
            if transcript:
                formatted_transcript = await format_transcript_with_llm(transcript)
        except Exception as e:
            logger.warning(f"LLM-форматирование (audio) исключение: {e}")
        if not formatted_transcript and transcript:
            logger.info("LLM недоступен/неверный ключ — применяю локальное форматирование")
            formatted_transcript = _basic_local_format(transcript)

        if formatted_transcript and formatted_transcript.strip():
            # Сохраняем транскрипцию (уже отформатированную)
            transcript_path = TRANSCRIPTIONS_DIR / f"telegram_transcript_{audio_file.file_id}.txt"
            transcript_path.write_text(formatted_transcript or "", encoding='utf-8')

            # Сохраняем в базу данных и обновляем счетчики
            try:
                from transkribator_modules.db.database import SessionLocal, UserService, TranscriptionService
                from transkribator_modules.db.database import get_media_duration

                db = SessionLocal()
                try:
                    user_service = UserService(db)
                    transcription_service = TranscriptionService(db)

                    # Получаем пользователя
                    user = user_service.get_or_create_user(
                        telegram_id=update.effective_user.id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name
                    )

                    # Получаем реальную длительность аудио
                    duration_minutes = get_media_duration(str(audio_path))

                    # Сохраняем транскрипцию в базу
                    transcription_service.save_transcription(
                        user=user,
                        filename=filename,
                        file_size_mb=file_size_mb,
                        audio_duration_minutes=duration_minutes,
                        raw_transcript=transcript or "",
                        formatted_transcript=formatted_transcript or "",
                        processing_time=0.0,
                        transcription_service="deepinfra",
                        formatting_service="llm" if formatted_transcript != transcript else "none"
                    )

                    # Обновляем счетчики использования
                    user_service.add_usage(user, duration_minutes)

                    logger.info(f"✅ Транскрипция сохранена для пользователя {user.telegram_id}")

                finally:
                    db.close()
            except Exception as e:
                logger.error(f"Ошибка при сохранении транскрипции: {e}")

            # Отправляем результат
            if status_msg:
                await status_msg.edit_text("✅ Транскрипция готова!")

            # Если текст короткий, отправляем в сообщении
            clean_transcript = clean_html_entities(formatted_transcript or "")
            full_message = f"📝 Транскрипция:\n\n{clean_transcript}\n\n@CyberKitty19_bot"

            logger.info(f"Длина исходной транскрипции (аудио): {len(transcript or '')} символов")
            logger.info(f"Длина отформатированной транскрипции (аудио): {len(formatted_transcript or '')} символов")
            logger.info(f"Длина полного сообщения (аудио): {len(full_message)} символов")

            # Проверяем длину исходной транскрипции для решения о формате отправки
            if len(transcript or "") <= 4000:
                logger.info("Отправляем транскрипцию как текстовое сообщение (аудио)")
                await update.message.reply_text(full_message)
            else:
                # Если длинный, отправляем .docx
                logger.info("Отправляем транскрипцию как .docx файл (аудио)")
                from docx import Document
                # Убеждаемся, что директория существует
                TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
                docx_path = TRANSCRIPTIONS_DIR / f"transcript_{Path(filename).stem}.docx"
                document = Document()
                for line in (formatted_transcript or "").split('\n'):
                    document.add_paragraph(line)
                document.save(docx_path)
                logger.info(f"Создан .docx файл (аудио): {docx_path}")
                with open(docx_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=docx_path.name,
                        caption="📝 Транскрипция готова!\n\n@CyberKitty19_bot"
                    )

            # Создаем кнопки для дальнейших действий
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [
                    InlineKeyboardButton("🔧 Обработать", callback_data=f"process_transcript_{update.effective_user.id}"),
                    InlineKeyboardButton("📤 Прислать ещё", callback_data=f"send_more_{update.effective_user.id}")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data=f"main_menu_{update.effective_user.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем сообщение с кнопками
            await update.message.reply_text(
                "Что дальше будем с этим делать? 🤔",
                reply_markup=reply_markup
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

    # Если это обычное текстовое сообщение
    if update.message.text:
        # Проверяем, что это не группа или что бот упомянут в сообщении
        is_group = update.effective_chat and update.effective_chat.type in ("group", "supergroup")
        bot_mentioned = False

        if is_group:
            # В группах проверяем, упомянут ли бот
            bot_username = context.bot.username
            if bot_username and f"@{bot_username}" in update.message.text:
                bot_mentioned = True

        # Отвечаем только в личных чатах или если бот упомянут в группе
        if not is_group or bot_mentioned:
            # Проверяем, ожидаем ли мы задачу для обработки транскрипции
            if context.user_data.get('waiting_for_task', False):
                await handle_transcript_processing_task(update, context)
            else:
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

async def handle_transcript_processing_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения с задачами для обработки транскрипции."""
    try:
        user_id = update.effective_user.id
        task_description = update.message.text

        # Сбрасываем флаг ожидания задачи
        context.user_data['waiting_for_task'] = False

        # Отправляем сообщение о начале обработки
        processing_msg = await update.message.reply_text(
            "🤖 Обрабатываю транскрипцию согласно твоей задаче...\n\n"
            "*сосредоточенно работает*\n"
            "Это может занять некоторое время...",
            parse_mode='Markdown'
        )

        # Получаем последнюю транскрипцию пользователя из базы данных
        from transkribator_modules.db.database import SessionLocal, UserService, TranscriptionService

        db = SessionLocal()
        try:
            user_service = UserService(db)
            transcription_service = TranscriptionService(db)

            # Получаем пользователя
            user = user_service.get_or_create_user(telegram_id=user_id)

            # Получаем последнюю транскрипцию пользователя
            transcriptions = transcription_service.get_user_transcriptions(user, limit=1)

            if not transcriptions:
                await processing_msg.edit_text(
                    "❌ Не найдено транскрипций для обработки.\n\n"
                    "Сначала отправьте файл для транскрипции!"
                )
                return

            latest_transcription = transcriptions[0]
            transcript_text = latest_transcription.formatted_transcript or latest_transcription.raw_transcript

            if not transcript_text:
                await processing_msg.edit_text("❌ Транскрипция пуста")
                return

            # Обрабатываем транскрипцию согласно задаче
            processed_text = await process_transcript_with_task(transcript_text, task_description)

            if not processed_text:
                await processing_msg.edit_text(
                    "❌ Не удалось обработать транскрипцию.\n\n"
                    "Возможно, сервис временно недоступен. Попробуйте позже."
                )
                return

            # Отправляем результат
            result_text = f"✅ **Результат обработки:**\n\n{processed_text}\n\n@CyberKitty19_bot"

            # Если результат длинный, отправляем файлом
            if len(result_text) > 4000:
                from docx import Document
                from pathlib import Path

                # Убеждаемся, что директория существует
                TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
                docx_path = TRANSCRIPTIONS_DIR / f"processed_transcript_{user_id}.docx"

                document = Document()
                document.add_heading("Обработанная транскрипция", 0)
                document.add_paragraph(f"Задача: {task_description}")
                document.add_paragraph("Результат:")
                document.add_paragraph(processed_text)
                document.save(docx_path)

                with open(docx_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"processed_transcript.docx",
                        caption="✅ Результат обработки готов!\n\n@CyberKitty19_bot"
                    )

                # Удаляем временный файл
                docx_path.unlink(missing_ok=True)
            else:
                # Отправляем без parse_mode чтобы избежать ошибок с markdown entities
                await update.message.reply_text(result_text)

            # Обновляем сообщение о завершении
            await processing_msg.edit_text("✅ Обработка завершена!")

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Ошибка при обработке задачи транскрипции: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке транскрипции.\n\n"
            "Попробуйте позже или обратитесь в поддержку."
        )

async def process_transcript_with_task(transcript_text: str, task_description: str) -> str:
    """Обрабатывает транскрипцию согласно задаче пользователя."""
    try:
        from transkribator_modules.transcribe.transcriber import format_transcript_with_llm

        # Создаем промпт для обработки транскрипции
        prompt = f"""Ты эксперт по обработке транскрипций. Пользователь просит обработать транскрипцию согласно следующей задаче:

ЗАДАЧА: {task_description}

ТРАНСКРИПЦИЯ:
{transcript_text}

Обработай транскрипцию согласно задаче пользователя. Если в задаче указан конкретный формат или пример, следуй ему точно. Сохрани важную информацию и структурируй результат так, чтобы он соответствовал запросу пользователя."""

        # Используем LLM для обработки
        processed_text = await format_transcript_with_llm(prompt)

        if processed_text and not processed_text.startswith("Произошла ошибка"):
            # Очищаем текст от потенциальных markdown сущностей
            cleaned_text = processed_text.replace("*", "").replace("_", "").replace("`", "")
            return cleaned_text
        else:
            # Fallback - возвращаем исходную транскрипцию с комментарием
            return f"Не удалось обработать транскрипцию через ИИ. Вот исходная транскрипция:\n\n{transcript_text}"

    except Exception as e:
        logger.error(f"Ошибка при обработке транскрипции с задачей: {e}")
        return f"Произошла ошибка при обработке: {str(e)}"