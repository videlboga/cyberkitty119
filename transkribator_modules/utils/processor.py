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
from transkribator_modules.db.models import PlanType

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
            # Если транскрипция слишком длинная, создаем Google Doc
            await status_message.edit_text(
                "Готово! Транскрипция получилась длинной, создаю Google Doc... *деловито стучит лапками*"
            )
            
            # Пробуем создать Google Doc
            try:
                from transkribator_modules.utils.google_docs import create_transcript_google_doc
                video_filename = f"telegram_video_{message_id}.mp4"
                doc_url = await create_transcript_google_doc(formatted_transcript, video_filename, chat_id)
                
                if doc_url:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"✅ **Транскрипция готова!**\n\n"
                             f"📄 **Google Doc:** [Открыть документ]({doc_url})\n\n"
                             f"📋 Документ содержит полную транскрипцию с красивым оформлением\n"
                             f"🔗 Ссылка остается активной навсегда\n\n"
                             f"🐾 *гордо машет хвостом*",
                        parse_mode='Markdown',
                        disable_web_page_preview=False
                    )
                else:
                    # Fallback к файлу если Google Docs недоступен
                    with open(transcript_path, "rb") as file:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=file,
                            filename=f"Транскрипция видео {message_id}.txt",
                            caption="📄 Google Docs недоступен, отправляю файлом! *извиняющееся мяуканье*"
                        )
            except Exception as e:
                logger.error(f"Ошибка создания Google Doc: {e}")
                # Fallback к файлу
                with open(transcript_path, "rb") as file:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=file,
                        filename=f"Транскрипция видео {message_id}.txt",
                        caption="📄 Ошибка создания Google Doc, отправляю файлом! *смущенно прячется*"
                    )
        else:
            # Если транскрипция не слишком длинная, отправляем текстом
            await status_message.edit_text(
                f"✅ **Готово! Вот транскрипция видео:**\n\n{formatted_transcript}\n\n@CyberKitty19_bot"
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
        
        # Проверяем лимиты и отправляем уведомления после успешной обработки
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
        
        # Промо-уведомления для новых пользователей
        if db_user.transcriptions_count == 0:  # Первая транскрибация
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 **Поздравляю с первой транскрибацией!**\n\n"
                     f"🎁 **Специально для тебя промокод:** `ПЕРВЫЙ2024` — дает +50% к лимиту на месяц!\n\n"
                     f"💡 Просто отправь промокод следующим сообщением",
                parse_mode='Markdown'
            )
        
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

        # 3. Сохраняем файлы
        transcript_path = TRANSCRIPTIONS_DIR / f"telegram_audio_{message_id}.txt"
        raw_path = TRANSCRIPTIONS_DIR / f"telegram_audio_{message_id}_raw.txt"
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(formatted_transcript)
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(raw_transcript)

        # 4. Отправляем результат
        if len(formatted_transcript) > MAX_MESSAGE_LENGTH:
            await status_message.edit_text("Текст длинный, отправляю файлом…")
            with open(transcript_path, "rb") as f:
                await context.bot.send_document(chat_id=chat_id, document=f, filename=f"transcript_{message_id}.txt")
        else:
            await status_message.edit_text(f"Расшифровка готова:\n\n{formatted_transcript}")

        # 5. Кнопка саммари
        keyboard = [[InlineKeyboardButton("📋 Краткое саммари", callback_data=f"brief_summary_{message_id}")]]
        await context.bot.send_message(chat_id=chat_id, text="Хочешь краткое саммари?", reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        logger.error(f"Ошибка process_audio_file: {e}")
        if status_message:
            await status_message.edit_text(f"Произошла ошибка: {e}") 