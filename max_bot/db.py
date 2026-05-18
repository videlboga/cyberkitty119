"""DB glue for max_bot — provider-aware ensure_user wrapper."""
from __future__ import annotations
from transkribator_modules.db.user_service import get_or_create_user_by_provider


def ensure_user(max_id: str, username: str | None = None, first_name: str | None = None, last_name: str | None = None) -> int:
    return get_or_create_user_by_provider(
        provider="max",
        external_id=str(max_id),
        username=username,
        first_name=first_name,
        last_name=last_name,
    )
