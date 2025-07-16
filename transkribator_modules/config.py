import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("cyberkitty119.log")
    ]
)

logger = logging.getLogger(__name__)

# Получаем настройки из .env файла
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не установлен в .env файле!")
    raise ValueError("TELEGRAM_BOT_TOKEN не установлен в .env файле!")

# Настройки для API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3-opus:beta')
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY', '')

# Настройки для ЮKassa
YUKASSA_SHOP_ID = os.getenv('YUKASSA_SHOP_ID', '')
YUKASSA_SECRET_KEY = os.getenv('YUKASSA_SECRET_KEY', '')
YUKASSA_WEBHOOK_SECRET = os.getenv('YUKASSA_WEBHOOK_SECRET', '')

# Проверка доступности ЮKassa
try:
    from transkribator_modules.payments.yukassa import YukassaPaymentService
    YUKASSA_AVAILABLE = bool(YUKASSA_SHOP_ID and YUKASSA_SECRET_KEY)
except ImportError:
    YUKASSA_AVAILABLE = False
    logger.warning("ЮKassa SDK не установлен")

# Настройки для Replicate API
REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN', '')
REPLICATE_WHISPER_MODEL = os.getenv('REPLICATE_WHISPER_MODEL', 'carnifexer/whisperx')  # Бюджетная модель по умолчанию
REPLICATE_WHISPER_DIARIZATION_MODEL = os.getenv('REPLICATE_WHISPER_DIARIZATION_MODEL', 'thomasmol/whisper-diarization')  # Модель с диаризацией

# Пути для файлов
BASE_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR = BASE_DIR / "videos"
AUDIO_DIR = BASE_DIR / "audio"
TRANSCRIPTIONS_DIR = BASE_DIR / "transcriptions"

# Создаем директории, если они не существуют
VIDEOS_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)
TRANSCRIPTIONS_DIR.mkdir(exist_ok=True)

# ID администратора по умолчанию (добавьте свои при необходимости)
DEFAULT_ADMIN_IDS = {648981358}

# Дополнительные ID из переменной окружения, разделённые запятыми
_admin_env = os.getenv("ADMIN_TELEGRAM_IDS", "")
env_admins = {int(x) for x in _admin_env.split(",") if x.strip().isdigit()}

# Итоговый список админов без дубликатов
ADMIN_IDS = list(DEFAULT_ADMIN_IDS.union(env_admins))

# Константы
MAX_MESSAGE_LENGTH = 4096  # Максимальная длина сообщения в Telegram

# Глобальный словарь для хранения транскрипций пользователей
user_transcriptions = {} 