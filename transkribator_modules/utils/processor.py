import asyncio
from pathlib import Path
from transkribator_modules.config import (
    logger, user_transcriptions, AUDIO_DIR, TRANSCRIPTIONS_DIR, MAX_MESSAGE_LENGTH
)
from transkribator_modules.audio.extractor import extract_audio_from_video
from transkribator_modules.transcribe.transcriber import (
    transcribe_audio, format_transcript_with_llm
)
from transkribator_modules.db.database import SessionLocal, UserService
from transkribator_modules.db.models import PlanType, Transcription

async def process_video_file(video_path, chat_id, message_id, context, status_message=None):
    """Обрабатывает видео из файла, извлекает аудио и выполняет транскрибацию.
    Эта версия не требует объекта Update и может быть использована напрямую с файлами."""
    
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
        
        # --- Унифицированный вывод ---
        transcript_path, raw_transcript_path = await send_transcription_result(
            chat_id=chat_id,
            message_id=message_id,
            formatted_transcript=formatted_transcript,
            raw_transcript=raw_transcript,
            media_prefix="telegram_video",
            context=context,
            status_message=status_message,
        )
        
        # Проверяем лимиты
        await check_user_limits_and_notify(chat_id, context)
        
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
            # Иначе отправляем текстом без parse_mode, чтобы избежать ошибок Telegram
            await status_message.edit_text(
                f"Готово! Вот транскрипция видео:\n\n{formatted_transcript}\n\n@CyberKitty19_bot",
                parse_mode=None,
                disable_web_page_preview=True,
            )
        
        # Добавляем кнопки для получения саммари и исходной транскрипции
        keyboard = [
            [
                InlineKeyboardButton("📝 Подробное саммари", callback_data=f"detailed_summary_{message_id}"),
                InlineKeyboardButton("📋 Краткое саммари", callback_data=f"brief_summary_{message_id}"),
            ],
            [InlineKeyboardButton("🔍 Показать сырую транскрипцию", callback_data=f"raw_{message_id}")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            'Вы можете получить саммари или необработанную версию транскрипции:\nНажмите кнопку ниже:',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке видео: {e}")
        await update.message.reply_text(
            f"Произошла ошибка при обработке видео: {str(e)} *испуганно прячется*"
        ) 

async def check_user_limits_and_notify(chat_id, context):
    """Проверяет лимиты пользователя и отправляет уведомления"""
    db = SessionLocal()
    try:
        user_service = UserService(db)
        db_user = user_service.get_or_create_user(telegram_id=chat_id)
        usage_info = user_service.get_usage_info(db_user)
        
        # Проверяем лимиты и отправляем уведомления
        if usage_info['minutes_limit']:
            percentage = usage_info['usage_percentage']
            remaining = usage_info['minutes_remaining']
            
            # Уведомление при 80% использования
            if 75 <= percentage < 90 and remaining > 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ **Внимание!** У тебя осталось {remaining:.1f} минут транскрибации в этом месяце (использовано {percentage:.1f}%)\n\n"
                         f"💡 Рекомендую обновить тарифный план для безлимитного использования!\n\n"
                         f"⭐ /plans — посмотреть тарифы",
                    parse_mode='Markdown'
                )
            
            # Уведомление при 90% использования
            elif percentage >= 90 and remaining > 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚨 **Лимит почти исчерпан!** Осталось всего {remaining:.1f} минут\n\n"
                         f"🔥 **Специальное предложение:** обнови план прямо сейчас и получи +20% бонусных минут!\n\n"
                         f"⭐ /plans — срочно обновить тариф",
                    parse_mode='Markdown'
                )
            
            # Уведомление при исчерпании лимита
            elif remaining <= 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"😿 **Лимит исчерпан!** В этом месяце больше нет доступных минут\n\n"
                         f"🎯 **Восстановление лимита:** {_get_next_reset_date()}\n\n"
                         f"🚀 **Или обнови план для мгновенного доступа:**\n"
                         f"⭐ /plans — купить тариф",
                    parse_mode='Markdown'
                )
        
        # Ранее здесь отправлялся промокод для первой транскрибации — отключено
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при проверке лимитов: {e}")
        return False
    finally:
        db.close()

def _get_next_reset_date():
    """Возвращает дату следующего сброса лимитов"""
    from datetime import datetime, timedelta
    import calendar
    
    now = datetime.utcnow()
    # Находим первое число следующего месяца
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1)
    else:
        next_month = datetime(now.year, now.month + 1, 1)
    
    return next_month.strftime('%d.%m.%Y')

# --- новый путь для чистых аудио ---------------------------------------------------

# -----------------------------------------------------------------------------
# Helper: unified result sending for any media type (video, audio, links)
# -----------------------------------------------------------------------------

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


async def send_transcription_result(
    *,
    chat_id: int,
    message_id: int,
    formatted_transcript: str,
    raw_transcript: str,
    media_prefix: str,
    context,
    status_message=None,
):
    """Отправляет пользователю результаты транскрипции в едином формате.

    media_prefix — строка-«префикс» для имён файлов (например, `telegram_video` или
    `telegram_audio`). Таким образом везде будет единый стиль, и функцию можно
    использовать для любого источника.
    """

    # --- 1. Сохраняем файлы ---------------------------------------------------
    transcript_path = TRANSCRIPTIONS_DIR / f"{media_prefix}_{message_id}.txt"
    raw_transcript_path = TRANSCRIPTIONS_DIR / f"{media_prefix}_{message_id}_raw.txt"

    # гарантируем директорию
    transcript_path.parent.mkdir(parents=True, exist_ok=True)

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(formatted_transcript)

    with open(raw_transcript_path, "w", encoding="utf-8") as f:
        f.write(raw_transcript)

    # --- 2. Кэшируем для дальнейших команд -----------------------------------
    user_transcriptions[chat_id] = {
        "raw": raw_transcript,
        "formatted": formatted_transcript,
        "path": str(transcript_path),
        "raw_path": str(raw_transcript_path),
        "timestamp": asyncio.get_event_loop().time(),
    }

    # --- 3. Отправляем результат ---------------------------------------------
    if len(formatted_transcript) > MAX_MESSAGE_LENGTH:
        # Попытка создать Google Doc (как в обработке видео)
        if status_message:
            await status_message.edit_text(
                "Готово! Транскрипция получилась длинной, создаю Google Doc… 📝"
            )
        try:
            from transkribator_modules.utils.google_docs import create_transcript_google_doc

            filename = f"{media_prefix}_{message_id}.mp4" if media_prefix.endswith("video") else f"{media_prefix}_{message_id}.wav"
            doc_url = await create_transcript_google_doc(formatted_transcript, filename, chat_id)

            if doc_url:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "✅ **Транскрипция готова!**\n\n"
                        f"📄 **Google Doc:** [Открыть документ]({doc_url})\n\n"
                        "📋 Документ содержит полную транскрипцию с красивым оформлением\n"
                        "🔗 Ссылка остаётся активной навсегда\n\n"
                        "🐾 *гордо машет хвостом*"
                    ),
                    parse_mode="Markdown",
                    disable_web_page_preview=False,
                )
            else:
                raise RuntimeError("Google Docs недоступен")
        except Exception:
            # Fallback — отправляем файлом
            if status_message:
                await status_message.edit_text(
                    "Не удалось создать Google Doc, отправляю файлом… 📄"
                )
            with open(transcript_path, "rb") as file:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    filename=f"Транскрипция {message_id}.txt",
                    caption="📄 Полная транскрипция во вложении",
                )
    else:
        # Помещается в сообщение — отвечаем текстом
        if status_message:
            await status_message.edit_text(
                f"Готово! Вот транскрипция:\n\n{formatted_transcript}\n\n@CyberKitty19_bot",
                parse_mode=None,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Готово! Вот транскрипция:\n\n{formatted_transcript}\n\n@CyberKitty19_bot",
                parse_mode=None,
            )

    # --- 4. Кнопочки ----------------------------------------------------------
    keyboard = [
        [
            InlineKeyboardButton("📝 Подробное саммари", callback_data=f"detailed_summary_{message_id}"),
            InlineKeyboardButton("📋 Краткое саммари", callback_data=f"brief_summary_{message_id}"),
        ],
        [InlineKeyboardButton("🔍 Показать сырую транскрипцию", callback_data=f"raw_{message_id}")],
    ]
    await context.bot.send_message(
        chat_id=chat_id,
        text='Вы можете получить саммари или необработанную версию транскрипции:\nНажмите кнопку ниже:',
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    return transcript_path, raw_transcript_path

async def process_audio_file(audio_path, chat_id, message_id, context, status_message=None):
    """Обрабатывает аудио-файл (без этапа извлечения из видео)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    try:
        if not audio_path.exists():
            await context.bot.send_message(chat_id=chat_id, text="Файл не найден 😿")
            return

        if not status_message:
            status_message = await context.bot.send_message(chat_id=chat_id, text="Начинаю транскрипцию аудио…")

        # 1. Транскрипция
        await status_message.edit_text("Транскрибирую… 🐾")
        raw_transcript = await transcribe_audio(audio_path)
        if not raw_transcript:
            await status_message.edit_text("Не удалось выполнить транскрипцию 😿")
            return

        # 2. Форматирование
        await status_message.edit_text("Форматирую текст… ✨")
        formatted_transcript = await format_transcript_with_llm(raw_transcript)

        # 3. Унифицированный вывод
        await send_transcription_result(
            chat_id=chat_id,
            message_id=message_id,
            formatted_transcript=formatted_transcript,
            raw_transcript=raw_transcript,
            media_prefix="telegram_audio",
            context=context,
            status_message=status_message,
        )

        # 4. Проверка лимитов
        await check_user_limits_and_notify(chat_id, context)

    except Exception as e:
        logger.error(f"Ошибка process_audio_file: {e}")
        if status_message:
            await status_message.edit_text(f"Произошла ошибка: {e}") 