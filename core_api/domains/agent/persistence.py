from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import User

logger = logging.getLogger(__name__)


def _parse_links(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if isinstance(v, str) and v.strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items() if isinstance(v, str) and v.strip()}
    return {}


def _parse_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(item).strip() for item in raw if str(item or "").strip()]
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(payload, list):
            return [str(item).strip() for item in payload if str(item or "").strip()]
    return []


@dataclass(slots=True)
class NoteSnapshot:
    id: int
    user_id: int
    summary: Optional[str]
    text: Optional[str]
    tags: list[str]
    links: dict[str, str]
    draft_title: Optional[str] = None
    type_hint: Optional[str] = None


class AgentPersistenceGateway:
    """Thin wrapper over legacy DB services for agent runtime."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    def ensure_user(self, telegram_user) -> dict[str, Any]:
        """Return payload for AgentUser instantiation."""
        db = self._session_factory()
        try:
            user_service = UserService(db)
            user = user_service.get_or_create_user(
                telegram_id=telegram_user.id,
                username=getattr(telegram_user, "username", None),
                first_name=getattr(telegram_user, "first_name", None),
                last_name=getattr(telegram_user, "last_name", None),
            )
            return {
                "telegram_id": telegram_user.id,
                "db_id": int(user.id),
                "username": getattr(telegram_user, "username", None),
                "first_name": getattr(telegram_user, "first_name", None),
                "last_name": getattr(telegram_user, "last_name", None),
            }
        finally:
            db.close()

    def get_note_snapshot(self, note_id: int, expected_user_id: int) -> Optional[NoteSnapshot]:
        db = self._session_factory()
        try:
            service = NoteService(db)
            note = service.get_note(note_id)
            if not note or int(note.user_id) != int(expected_user_id):
                return None
            return NoteSnapshot(
                id=int(note.id),
                user_id=int(note.user_id),
                summary=getattr(note, "summary", None),
                text=getattr(note, "text", None),
                tags=_parse_tags(getattr(note, "tags", None)),
                links=_parse_links(getattr(note, "links", None)),
                draft_title=getattr(note, "draft_title", None),
                type_hint=getattr(note, "type_hint", None),
            )
        except Exception:
            logger.exception("Failed to fetch note snapshot", extra={"note_id": note_id})
            return None
        finally:
            db.close()

    def get_user_timezone(self, user_id: int) -> Optional[str]:
        db = self._session_factory()
        try:
            user = db.query(User).filter(User.id == user_id).one_or_none()
            if not user:
                return None
            tz_value = getattr(user, "timezone", None)
            if isinstance(tz_value, str) and tz_value.strip():
                return tz_value.strip()
            return None
        finally:
            db.close()
