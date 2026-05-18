"""Configuration for max_bot (read from environment)."""
from __future__ import annotations
import os
from pathlib import Path

MAX_API_TOKEN = os.getenv("MAX_API_TOKEN")
MAX_API_URL = os.getenv("MAX_API_URL", "https://api.max.example/v1")
MEDIA_INCOMING_DIR = Path(os.getenv("MEDIA_INCOMING_DIR", "media/incoming"))
MEDIA_INCOMING_DIR.mkdir(parents=True, exist_ok=True)

# Polling / delivery
PROGRESS_POLL_INTERVAL = float(os.getenv("PROGRESS_POLL_INTERVAL", "2.0"))
PROGRESS_TIMEOUT = float(os.getenv("PROGRESS_TIMEOUT", "3600"))

# Logging helper (simple)
import logging
logger = logging.getLogger("max_bot")
logger.setLevel(os.getenv("MAX_BOT_LOGLEVEL", "INFO"))

# Poller configuration
MAX_POLL_INTERVAL = float(os.getenv("MAX_POLL_INTERVAL", "5"))
# If provider supports long polling, set to "1"/"true" (no sleep between requests, use timeout param)
MAX_POLL_LONGPOLL = os.getenv("MAX_POLL_LONGPOLL", "true").lower() in ("1", "true", "yes")
# Timeout (seconds) used for longpoll request to provider
MAX_POLL_TIMEOUT = int(os.getenv("MAX_POLL_TIMEOUT", "30"))
# Path to store last_update_id state (file-based fallback)
MAX_POLL_STATE_FILE = os.getenv("MAX_POLL_STATE_FILE", "data/max_poll_state.json")
