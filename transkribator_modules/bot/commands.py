from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from transkribator_modules.config import logger, user_transcriptions, MAX_MESSAGE_LENGTH, TELETHON_WORKER_CHAT_ID

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    await update.message.reply_text(
        "Мур! Привет! Я КиберКотик - бот для транскрибации видео и аудио! *виляет хвостиком*\n\n"
        "Отправь мне видео или аудио файл, и я создам текстовую расшифровку! "
        "Также ты можешь отправить ссылку на YouTube или Google Drive."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /help."""
    await update.message.reply_text(
        "Мур-мур! Вот что я умею: *игриво машет лапкой*\n\n"
        "1. Транскрибировать видео, которые ты отправишь мне напрямую\n"
        "2. Транскрибировать видео из пересланных сообщений\n"
        "3. Скачивать и транскрибировать видео по ссылкам с YouTube или Google Drive\n\n"
        "Просто отправь мне видео или ссылку, и я займусь расшифровкой! *подмигивает*"
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статус телетон-воркера и проверяет его работоспособность."""
    session_file = Path("telethon_worker.session")
    
    if session_file.exists():
        session_status = "✅ Файл сессии Telethon существует"
    else:
        session_status = "❌ Файл сессии Telethon отсутствует. Выполните авторизацию с помощью telethon_auth.py"
    
    await update.message.reply_text(
        f"Статус системы:\n\n"
        f"{session_status}\n"
        f"🆔 ID телетон-воркера: {TELETHON_WORKER_CHAT_ID}\n\n"
        f"Для работы с видео необходимо:\n"
        f"1. Авторизовать Telethon клиент через telethon_auth.py\n"
        f"2. Запустить телетон-воркер (telethon_worker.py)\n"
        f"3. Убедиться, что BOT_ID в .env соответствует имени пользователя бота"
    )

async def raw_transcript_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /rawtranscript для получения необработанной транскрипции."""
    user_id = update.effective_user.id
    
    if user_id not in user_transcriptions or 'raw' not in user_transcriptions[user_id]:
        await update.message.reply_text(
            "У вас пока нет сохраненных транскрипций. *растерянно оглядывается*"
        )
        return
        
    transcript_data = user_transcriptions[user_id]
    raw_transcript = transcript_data['raw']
    
    if len(raw_transcript) > MAX_MESSAGE_LENGTH:
        # Если транскрипция слишком длинная, отправляем файлом
        raw_file_path = transcript_data.get('raw_path')
        
        if raw_file_path and Path(raw_file_path).exists():
            with open(raw_file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=f"raw_transcript_{user_id}.txt",
                    caption="Вот необработанная транскрипция вашего последнего видео! *деловито машет хвостом*"
                )
        else:
            await update.message.reply_text(
                "Не могу найти файл с сырой транскрипцией. *растерянно смотрит*"
            )
    else:
        # Иначе отправляем текстом
        await update.message.reply_text(
            f"Вот необработанная транскрипция вашего последнего видео:\n\n{raw_transcript}\n\n"
            f"*деловито кивает*"
        ) 