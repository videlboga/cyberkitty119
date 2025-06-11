import os
import logging
from pathlib import Path

# Создаем директории для хранения данных
DATA_DIR = Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Настройка логирования
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(DATA_DIR / 'bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== ОСНОВНЫЕ НАСТРОЙКИ БОТА =====
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    raise ValueError("BOT_TOKEN обязателен")

# ===== TELEGRAM BOT API SERVER =====
USE_LOCAL_BOT_API = os.getenv('USE_LOCAL_BOT_API', 'false').lower() == 'true'
LOCAL_BOT_API_URL = os.getenv('LOCAL_BOT_API_URL', 'http://telegram-bot-api:8081')

if USE_LOCAL_BOT_API:
    logger.info(f"🚀 Используется локальный Telegram Bot API Server: {LOCAL_BOT_API_URL}")
else:
    logger.info("🌐 Используется стандартный Telegram Bot API")

# ===== API КЛЮЧИ ДЛЯ AI СЕРВИСОВ =====
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY', '')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet')

# ===== НАСТРОЙКИ БАЗЫ ДАННЫХ =====
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR}/cyberkitty19_transkribator.db')

# ===== НАСТРОЙКИ ОБРАБОТКИ ФАЙЛОВ =====
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '2000'))
MAX_AUDIO_DURATION_MINUTES = int(os.getenv('MAX_AUDIO_DURATION_MINUTES', '240'))
ENABLE_LLM_FORMATTING = os.getenv('ENABLE_LLM_FORMATTING', 'true').lower() == 'true'
ENABLE_SEGMENTATION = os.getenv('ENABLE_SEGMENTATION', 'true').lower() == 'true'
SEGMENT_DURATION_SECONDS = int(os.getenv('SEGMENT_DURATION_SECONDS', '30'))

# ===== ДИРЕКТОРИИ =====
VIDEOS_DIR = Path("/app/videos")
AUDIO_DIR = Path("/app/audio")
TRANSCRIPTIONS_DIR = Path("/app/transcriptions")

# Создаем необходимые директории
for directory in [VIDEOS_DIR, AUDIO_DIR, TRANSCRIPTIONS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

logger.info("✅ Конфигурация загружена успешно")
logger.info(f"📁 Директория данных: {DATA_DIR}")
logger.info(f"📁 Директория видео: {VIDEOS_DIR}")
logger.info(f"📁 Директория аудио: {AUDIO_DIR}")
logger.info(f"📁 Директория транскрипций: {TRANSCRIPTIONS_DIR}")
logger.info(f"🔧 Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ")
logger.info(f"⏱️ Максимальная длительность: {MAX_AUDIO_DURATION_MINUTES} минут") 