"""Google OAuth credential storage and helper logic."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from base64 import urlsafe_b64encode
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from transkribator_modules.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GOOGLE_ENCRYPTION_KEY,
    GOOGLE_SCOPES,
    logger,
)
from transkribator_modules.db.models import GoogleCredential, User


def _get_fernet() -> Fernet:
    if not GOOGLE_ENCRYPTION_KEY:
        raise RuntimeError("GOOGLE_ENCRYPTION_KEY is not configured")
    raw = GOOGLE_ENCRYPTION_KEY.encode()
    if len(raw) != 44:
        digest = hashlib.sha256(raw).digest()
        raw = urlsafe_b64encode(digest)
    return Fernet(raw)


class GoogleCredentialService:
    """Persist Google tokens encrypted in the database."""

    def __init__(self, db):
        self.db = db
        self._fernet = _get_fernet()

    def _encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as exc:
            raise RuntimeError("Failed to decrypt Google credential") from exc

    def _client_config(self) -> dict:
        return {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uris": [GOOGLE_REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

    def build_flow(self, state: Optional[str] = None) -> Flow:
        if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
            raise RuntimeError("Google OAuth client is not configured")
        flow = Flow.from_client_config(
            self._client_config(),
            scopes=GOOGLE_SCOPES,
            redirect_uri=GOOGLE_REDIRECT_URI,
        )
        if state:
            flow.state = state
        return flow

    def store_tokens(self, user_id: int, tokens: dict, scopes: list[str]) -> GoogleCredential:
        cred = (
            self.db.query(GoogleCredential)
            .filter(GoogleCredential.user_id == user_id)
            .one_or_none()
        )
        encrypted_access = self._encrypt(tokens.get("access_token", ""))
        encrypted_refresh = (
            self._encrypt(tokens.get("refresh_token"))
            if tokens.get("refresh_token")
            else None
        )
        scopes_json = json.dumps(scopes)
        expiry = tokens.get("expiry")
        if isinstance(expiry, str):
            expiry_dt = datetime.fromisoformat(expiry)
        else:
            expiry_dt = expiry

        if cred:
            cred.access_token = encrypted_access
            cred.refresh_token = encrypted_refresh or cred.refresh_token
            cred.expiry = expiry_dt
            cred.scopes = scopes_json
            cred.updated_at = datetime.utcnow()
        else:
            cred = GoogleCredential(
                user_id=user_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expiry=expiry_dt,
                scopes=scopes_json,
            )
            self.db.add(cred)
        self.db.commit()
        self.db.refresh(cred)

        user = self.db.query(User).filter(User.id == user_id).one_or_none()
        if user:
            user.google_connected = True
            user.updated_at = datetime.utcnow()
            self.db.commit()
        return cred

    def get_credentials(self, user_id: int) -> Optional[Credentials]:
        cred = (
            self.db.query(GoogleCredential)
            .filter(GoogleCredential.user_id == user_id)
            .one_or_none()
        )
        if not cred:
            return None
        access_token = self._decrypt(cred.access_token)
        refresh_token = self._decrypt(cred.refresh_token) if cred.refresh_token else None
        info = {
            "token": access_token,
            "refresh_token": refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": json.loads(cred.scopes or "[]"),
        }
        credentials = Credentials.from_authorized_user_info(info)
        return credentials

    def revoke(self, user_id: int) -> None:
        cred = (
            self.db.query(GoogleCredential)
            .filter(GoogleCredential.user_id == user_id)
            .one_or_none()
        )
        if cred:
            self.db.delete(cred)
            user = self.db.query(User).filter(User.id == user_id).one_or_none()
            if user:
                user.google_connected = False
                user.updated_at = datetime.utcnow()
            self.db.commit()
            logger.info("Google OAuth credentials revoked", extra={"user_id": user_id})

    def has_credentials(self, user_id: int) -> bool:
        return self.db.query(GoogleCredential.id).filter(GoogleCredential.user_id == user_id).first() is not None
