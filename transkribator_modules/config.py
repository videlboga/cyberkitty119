import os
import sys
import logging
import importlib
from pathlib import Path
from typing import Any, Mapping, Optional

# Загружаем переменные окружения из .env файла
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv не установлен, продолжаем без него
    pass

# Определяем, запущены ли мы в контейнере
IN_CONTAINER = os.path.exists('/app') and os.access('/app', os.W_OK)

# Создаем директории для хранения данных
if IN_CONTAINER:
    DATA_DIR = Path("/app/data")
else:
    DATA_DIR = Path("./data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Определяем окружение
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development').lower()

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
# Никогда не храните реальные токены в коде/репозитории.
# Значение должно приходить из переменных окружения или .env (который игнорируется git).
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Проверяем BOT_TOKEN только для модулей бота (не для API сервера)
_running_tests = 'PYTEST_CURRENT_TEST' in os.environ or any('pytest' in arg for arg in sys.argv)
default_require_bot_token = 'false' if _running_tests else 'true'
REQUIRE_BOT_TOKEN = os.getenv('REQUIRE_BOT_TOKEN', default_require_bot_token).lower() == 'true'
if REQUIRE_BOT_TOKEN and not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN не установлен!")
    raise ValueError("BOT_TOKEN обязателен")
if not REQUIRE_BOT_TOKEN and not BOT_TOKEN and not _running_tests:
    logger.warning("⚠️ BOT_TOKEN отключён через REQUIRE_BOT_TOKEN=false — используйте только в тестах")

# ===== TELEGRAM BOT API SERVER =====
USE_LOCAL_BOT_API = os.getenv('USE_LOCAL_BOT_API', 'true').lower() == 'true'
LOCAL_BOT_API_URL = os.getenv('LOCAL_BOT_API_URL', 'http://localhost:8083')

# API_ID и API_HASH нужны только для Bot API Server (в docker-compose.yml)
TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID', '0'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH', '')

if USE_LOCAL_BOT_API:
    logger.info(f"🚀 Используется локальный Telegram Bot API Server: {LOCAL_BOT_API_URL}")
    if TELEGRAM_API_ID == 0:
        logger.warning("⚠️ TELEGRAM_API_ID не задан! Нужен для Bot API Server")
    if not TELEGRAM_API_HASH:
        logger.warning("⚠️ TELEGRAM_API_HASH не задан! Нужен для Bot API Server")
else:
    logger.info("🌐 Используется стандартный Telegram Bot API")

# ===== API КЛЮЧИ ДЛЯ AI СЕРВИСОВ =====
DEEPINFRA_API_KEY = os.getenv('DEEPINFRA_API_KEY', '')
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')
OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'google/gemini-2.5-flash-lite')
EMBEDDING_PROVIDER = os.getenv('EMBEDDING_PROVIDER', 'openrouter')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'openai/text-embedding-3-small')
EMBEDDING_TIMEOUT = float(os.getenv('EMBEDDING_TIMEOUT', '15'))
DISABLE_REMOTE_EMBEDDINGS = os.getenv('DISABLE_REMOTE_EMBEDDINGS', 'false').lower() in ('1', 'true', 'yes')

# ===== НАСТРОЙКИ ЮКАССЫ =====
YUKASSA_SHOP_ID = os.getenv('YUKASSA_SHOP_ID', '')
YUKASSA_SECRET_KEY = os.getenv('YUKASSA_SECRET_KEY', '')
YUKASSA_DEFAULT_EMAIL = os.getenv('YUKASSA_DEFAULT_EMAIL', 'billing@transkribator.local')
YUKASSA_VAT_CODE = int(os.getenv('YUKASSA_VAT_CODE', '1'))  # 1 = без НДС
YUKASSA_TAX_SYSTEM_CODE = os.getenv('YUKASSA_TAX_SYSTEM_CODE')

# ===== НАСТРОЙКИ БАЗЫ ДАННЫХ =====
if IN_CONTAINER:
    DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR}/cyberkitty19_transkribator.db')
else:
    DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{DATA_DIR.absolute()}/cyberkitty19_transkribator.db')

# ===== НАСТРОЙКИ ОБРАБОТКИ ФАЙЛОВ =====
MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '2000'))
MAX_AUDIO_DURATION_MINUTES = int(os.getenv('MAX_AUDIO_DURATION_MINUTES', '240'))
ENABLE_LLM_FORMATTING = os.getenv('ENABLE_LLM_FORMATTING', 'true').lower() == 'true'
ENABLE_SEGMENTATION = os.getenv('ENABLE_SEGMENTATION', 'true').lower() == 'true'
SEGMENT_DURATION_SECONDS = int(os.getenv('SEGMENT_DURATION_SECONDS', '30'))

# ===== ДИРЕКТОРИИ =====
if IN_CONTAINER:
    VIDEOS_DIR = Path("/app/videos")
    AUDIO_DIR = Path("/app/audio")
    TRANSCRIPTIONS_DIR = Path("/app/transcriptions")
else:
    VIDEOS_DIR = Path("./videos")
    AUDIO_DIR = Path("./audio")
    TRANSCRIPTIONS_DIR = Path("./transcriptions")

for directory in [VIDEOS_DIR, AUDIO_DIR, TRANSCRIPTIONS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ===== ФИЧЕФЛАГИ И НОВЫЕ СЕРВИСЫ =====
FEATURE_BETA_MODE = os.getenv('FEATURE_BETA_MODE', 'false').lower() == 'true'
ROUTER_MODEL = os.getenv('ROUTER_MODEL', 'google/gemini-2.5-flash-lite')
ROUTER_CONF_HIGH = float(os.getenv('ROUTER_CONF_HIGH', '0.80'))
ROUTER_CONF_MID = float(os.getenv('ROUTER_CONF_MID', '0.55'))
SEARCH_BACKEND = os.getenv('SEARCH_BACKEND', 'pgvector')
ENABLE_STRUCT_LOGS = os.getenv('ENABLE_STRUCT_LOGS', '0').lower() in ('1', 'true')
FEATURE_GOOGLE_CALENDAR = os.getenv('FEATURE_GOOGLE_CALENDAR', 'true').lower() == 'true'
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', '')
GOOGLE_ENCRYPTION_KEY = os.getenv('GOOGLE_ENCRYPTION_KEY', '')
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
]
GOOGLE_OAUTH_CONFIGURED = bool(
    GOOGLE_CLIENT_ID
    and GOOGLE_CLIENT_SECRET
    and GOOGLE_REDIRECT_URI
    and GOOGLE_ENCRYPTION_KEY
)
SHOW_GOOGLE_OAUTH_IN_MENU = os.getenv(
    'SHOW_GOOGLE_OAUTH_IN_MENU',
    'false' if ENVIRONMENT in ('production', 'prod') else 'true',
).lower() in ('1', 'true', 'yes')

AGENT_FIRST = os.getenv('AGENT_FIRST', 'false').lower() in ('1', 'true', 'yes')
if FEATURE_GOOGLE_CALENDAR:
    GOOGLE_SCOPES.append('https://www.googleapis.com/auth/calendar.readonly')
    GOOGLE_SCOPES.append('https://www.googleapis.com/auth/calendar.events')

MINIAPP_PUBLIC_URL = os.getenv('MINIAPP_PUBLIC_URL', 'https://cyberkitty.ru/miniapp').rstrip("/")
# Dev override for MiniApp URL (typically a HTTPS tunnel such as cloudflared/ngrok).
# If set, the bot will use this URL for MiniApp buttons.
MINIAPP_DEV_TUNNEL_URL = os.getenv('MINIAPP_DEV_TUNNEL_URL', '').strip().rstrip("/")
# Effective URL used by bot UI.
MINIAPP_EFFECTIVE_URL = (MINIAPP_DEV_TUNNEL_URL or MINIAPP_PUBLIC_URL).rstrip("/")
MINIAPP_PROXY_URL = os.getenv('MINIAPP_PROXY_URL', 'https://t.me/CyberKitty19_bot/journal').rstrip('/')
MINIAPP_PROXY_QUERY_PARAM = os.getenv('MINIAPP_PROXY_QUERY_PARAM', 'startapp').strip() or 'startapp'
MINIAPP_NOTE_LINK_TEMPLATE = os.getenv('MINIAPP_NOTE_LINK_TEMPLATE', '').strip()
TELEGRAM_REFERRAL_URL = os.getenv('TELEGRAM_REFERRAL_URL', 'https://t.me/CyberKitty19_bot/journal').rstrip('/')

logger.info("✅ Конфигурация загружена успешно")
logger.info(f"🏠 Режим: {'контейнер' if IN_CONTAINER else 'локальный'}")
logger.info(f"📁 Директория данных: {DATA_DIR}")
logger.info(f"📁 Директория видео: {VIDEOS_DIR}")
logger.info(f"📁 Директория аудио: {AUDIO_DIR}")
logger.info(f"📁 Директория транскрипций: {TRANSCRIPTIONS_DIR}")
logger.info(f"🔧 Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ")
logger.info(f"⏱️ Максимальная длительность: {MAX_AUDIO_DURATION_MINUTES} минут")
logger.info(f"🧪 Бета-режим включен по умолчанию: {FEATURE_BETA_MODE}")
logger.info(f"🧭 Router модель: {ROUTER_MODEL}")
logger.info(f"📂 Google Drive интеграция включена: {GOOGLE_OAUTH_CONFIGURED}")

# Управление пользовательскими уведомлениями об ошибках
SUPPRESS_FAILURE_MESSAGES = os.getenv('SUPPRESS_FAILURE_MESSAGES', 'true').lower() in ('1', 'true', 'yes')
if SUPPRESS_FAILURE_MESSAGES:
    logger.info("🔇 Пользовательские сообщения об ошибках обработки медиa отключены (SUPPRESS_FAILURE_MESSAGES=true)")


def load_media_service_overrides() -> Optional[Mapping[str, Any]]:
    """Загрузить переопределения сервисов пайплайна из переменной окружения.

    Ожидается значение формата ``module.path:factory``. Фабрика возвращает mapping
    с ключами prepare/download/transcribe/finalize/deliver/cleanup.
    """

    target = os.getenv("MEDIA_SERVICE_OVERRIDES")
    if not target:
        return None

    module_name, _, attr = target.partition(":")
    if not module_name or not attr:
        logger.warning(
            "MEDIA_SERVICE_OVERRIDES: некорректное значение, ожидается 'module:attr'",
            extra={"value": target},
        )
        return None

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "MEDIA_SERVICE_OVERRIDES: не удалось импортировать модуль",
            extra={"module": module_name, "error": str(exc)},
        )
        return None

    value = getattr(module, attr, None)
    if value is None:
        logger.warning(
            "MEDIA_SERVICE_OVERRIDES: атрибут не найден",
            extra={"module": module_name, "attr": attr},
        )
        return None

    if callable(value):
        try:
            value = value()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MEDIA_SERVICE_OVERRIDES: фабрика завершилась ошибкой",
                extra={"module": module_name, "attr": attr, "error": str(exc)},
            )
            return None

    if not isinstance(value, Mapping):
        logger.warning(
            "MEDIA_SERVICE_OVERRIDES: ожидается mapping",
            extra={"returned_type": type(value).__name__},
        )
        return None

    return value


__all__ = [
    "BOT_TOKEN",
    "DATABASE_URL",
    "IN_CONTAINER",
    "logger",
    "SUPPRESS_FAILURE_MESSAGES",
    "load_media_service_overrides",
]
