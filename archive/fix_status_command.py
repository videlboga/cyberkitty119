from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes

# Предполагаем, что эта константа определена ранее
TELETHON_WORKER_CHAT_ID = "your_telethon_worker_chat_id"

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