"""Shared helpers for enforcing timezone configuration in beta flows."""

from __future__ import annotations

from typing import Any, Optional

TIMEZONE_REMINDER = (
    "Сначала настрой часовой пояс командой /timezone <Region/City>.\n"
    "Например: /timezone Europe/Moscow"
)


def has_timezone(user: Any) -> bool:
    """Return True when the ORM user has a non-empty timezone configured."""

    value = getattr(user, "timezone", None)
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)


def timezone_required_message(user: Any) -> Optional[str]:
    """Return reminder text when timezone is missing, otherwise None."""

    return None if has_timezone(user) else TIMEZONE_REMINDER

