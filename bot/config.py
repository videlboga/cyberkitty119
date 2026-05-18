"""
Конфигурация нового бота.

Читаем из тех же .env что и старый бот, чтобы не дублировать настройки.
"""

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ── Telegram ──────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.environ["BOT_TOKEN"]                       # обязателен

USE_LOCAL_BOT_API: bool = os.getenv("USE_LOCAL_BOT_API", "false").lower() == "true"
LOCAL_BOT_API_URL: str = os.getenv("LOCAL_BOT_API_URL", "http://localhost:8083")
LOCAL_BOT_FILE_API_URL: str = os.getenv("LOCAL_BOT_FILE_API_URL", LOCAL_BOT_API_URL)
LOCAL_BOT_API_DATA_DIR_HOST = Path(os.getenv("LOCAL_BOT_API_DATA_DIR_HOST", "/var/lib/telegram-bot-api-vpn"))
LOCAL_BOT_API_DATA_DIR = Path(os.getenv("LOCAL_BOT_API_DATA_DIR", ""))
if str(LOCAL_BOT_API_DATA_DIR).strip() == "":
    LOCAL_BOT_API_DATA_DIR = None
LOCAL_BOT_API_FILE_WAIT_ATTEMPTS = int(os.getenv("LOCAL_BOT_API_FILE_WAIT_ATTEMPTS", "10"))
LOCAL_BOT_API_FILE_WAIT_DELAY = float(os.getenv("LOCAL_BOT_API_FILE_WAIT_DELAY", "0.5"))
LOCAL_BOT_API_HTTP_RETRIES = int(os.getenv("LOCAL_BOT_API_HTTP_RETRIES", "3"))
LOCAL_BOT_API_HTTP_RETRY_DELAY = float(os.getenv("LOCAL_BOT_API_HTTP_RETRY_DELAY", "1.5"))

# VPN Proxy для доступа к Telegram API через VPN
VPN_PROXY_URL: str = os.getenv("VPN_PROXY_URL", "")  # если пусто, используем прямое соединение

# ── Директории ────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_INCOMING_DIR = ROOT_DIR / "media" / "incoming"
MEDIA_INCOMING_DIR.mkdir(parents=True, exist_ok=True)

# ── База данных ───────────────────────────────────────────────────────────────
# Наследуем от существующей инфраструктуры
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{ROOT_DIR / 'data' / 'cyberkitty19_transkribator.db'}",
)

# ── Логирование ───────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("transkribator.bot")

# ── Core API / Headless backend ──────────────────────────────────────────────
CORE_API_BASE_URL = os.getenv("CORE_API_BASE_URL", "http://core-api:8000/api/v1").rstrip("/")
CORE_API_TIMEOUT = float(os.getenv("CORE_API_TIMEOUT", "15"))
CORE_API_SERVICE_TOKEN = os.getenv("CORE_API_SERVICE_TOKEN", "").strip()
INTERNAL_BOT_API_BASE = f"{CORE_API_BASE_URL}/internal_bot"

def core_api_headers(extra: dict | None = None) -> dict:
    headers: dict = {}
    if CORE_API_SERVICE_TOKEN:
        headers["X-Service-Token"] = CORE_API_SERVICE_TOKEN
    if extra:
        headers.update(extra)
    return headers

# ── Прогресс polling ──────────────────────────────────────────────────────────
# Как часто проверять статус задачи в БД (секунды)
PROGRESS_POLL_INTERVAL: float = float(os.getenv("PROGRESS_POLL_INTERVAL", "3"))
# Максимальное время ожидания завершения задачи (секунды)
PROGRESS_TIMEOUT: float = float(os.getenv("PROGRESS_TIMEOUT", "1800"))
