import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Получаем настройки из .env файла
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELETHON_WORKER_CHAT_ID = int(os.getenv('TELETHON_WORKER_CHAT_ID', '0'))

# Настройки для Pyrogram воркера
PYROGRAM_WORKER_ENABLED = os.getenv('PYROGRAM_WORKER_ENABLED', 'false').lower() == 'true'
TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID', '')
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')
PYROGRAM_WORKER_CHAT_ID = int(os.getenv('PYROGRAM_WORKER_CHAT_ID', '0'))

# Настройки для API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3-opus:beta')
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY', '')

# Пути для файлов
BASE_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR = BASE_DIR / "videos"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTIONS_DIR = BASE_DIR / "transcriptions"

# Создаем директории, если они не существуют
VIDEOS_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cyberkitty119.log")
    ]
)
logger = logging.getLogger(__name__)

# Константы
MAX_MESSAGE_LENGTH = 4096  # Максимальная длина сообщения в Telegram

# Глобальный словарь для хранения транскрипций пользователей
user_transcriptions = {} 