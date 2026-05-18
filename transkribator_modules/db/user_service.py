"""Helper service for provider-aware user lookup / creation.

This keeps database access centralized and supports multiple external providers
(e.g. telegram, max). Other modules should call these helpers instead of
writing provider-specific logic themselves.
"""
from __future__ import annotations

from typing import Optional
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from transkribator_modules.db.models import User, UserIdentifier
from transkribator_modules.db.database import SessionLocal


def get_user_id_by_provider(provider: str, external_id: str) -> Optional[int]:
    db = SessionLocal()
    try:
        row = (
            db.query(UserIdentifier)
            .filter(UserIdentifier.provider == provider, UserIdentifier.external_id == str(external_id))
            .first()
        )
        if not row:
            return None
        return int(row.user_id)
    finally:
        db.close()


def get_or_create_user_by_provider(
    provider: str,
    external_id: str,
    *,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> int:
    """Find or create internal User for given provider+external_id.

    Returns internal user.id.
    """
    db = SessionLocal()
    try:
        # Try to find identifier first
        identifier = (
            db.query(UserIdentifier)
            .filter(UserIdentifier.provider == provider, UserIdentifier.external_id == str(external_id))
            .first()
        )
        if identifier:
            return int(identifier.user_id)

        # If no identifier, try to find a user by username (best-effort) for convenience
        user = None
        if username:
            user = db.query(User).filter(User.username == username).first()

        # Create new user if needed
        if user is None:
            user = User(
                telegram_id=None,  # legacy field kept nullable
                username=username or str(external_id),
                first_name=first_name,
                last_name=last_name,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Create identifier
        identifier = UserIdentifier(
            user_id=user.id,
            provider=provider,
            external_id=str(external_id),
        )
        db.add(identifier)
        db.commit()
        return int(user.id)
    finally:
        db.close()
 