"""Google OAuth helpers: state generation and auth URL construction."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Optional

from google_auth_oauthlib.flow import Flow

from transkribator_modules.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_ENCRYPTION_KEY,
    GOOGLE_SCOPES,
)

STATE_TTL_SECONDS = 900  # 15 minutes


def _get_state_secret() -> bytes:
    if not GOOGLE_ENCRYPTION_KEY:
        raise RuntimeError("GOOGLE_ENCRYPTION_KEY is not configured")
    raw = GOOGLE_ENCRYPTION_KEY.encode("utf-8")
    if len(raw) == 32:
        return raw
    # Derive fixed-size key from arbitrary string
    return hashlib.sha256(raw).digest()


def generate_state(user_id: int, ttl: int = STATE_TTL_SECONDS) -> str:
    """Generate HMAC-signed state payload for Google OAuth."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be positive int")
    secret = _get_state_secret()
    timestamp = int(time.time())
    nonce = secrets.token_urlsafe(8)
    data = f"{user_id}:{timestamp}:{nonce}:{ttl}"
    signature = hmac.new(secret, data.encode("utf-8"), hashlib.sha256).hexdigest()
    payload = f"{data}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("utf-8").rstrip("=")


def parse_state(state: str) -> tuple[int, int]:
    """Validate state and return (user_id, ttl_seconds)."""
    if not state:
        raise ValueError("Missing state")
    padding = "=" * (-len(state) % 4)
    try:
        decoded = base64.urlsafe_b64decode(state + padding).decode("utf-8")
        user_id_str, ts_str, nonce, ttl_str, signature = decoded.split(":", 4)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid state payload") from exc

    data = f"{user_id_str}:{ts_str}:{nonce}:{ttl_str}"
    secret = _get_state_secret()
    expected = hmac.new(secret, data.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise ValueError("Invalid state signature")

    user_id = int(user_id_str)
    issued_at = int(ts_str)
    ttl = int(ttl_str)

    if user_id <= 0:
        raise ValueError("Invalid user id")

    now = int(time.time())
    if now - issued_at > ttl:
        raise ValueError("State token expired")

    return user_id, ttl


def build_authorization_url(state: str) -> str:
    """Return Google OAuth authorization URL for provided state."""
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI):
        raise RuntimeError("Google OAuth client is not configured")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    return auth_url
