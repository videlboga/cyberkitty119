"""Shared logging helpers for Telegram bot handlers."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional
import inspect

from telegram import Update

from transkribator_modules.db.database import log_event, log_telegram_event


def _extract_update_meta(update: Optional[Update]) -> dict[str, Any]:
    if not update:
        return {}
    user = update.effective_user
    chat = update.effective_chat
    data: dict[str, Any] = {
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "chat_id": getattr(chat, "id", None) if chat else None,
        "chat_type": getattr(chat, "type", None) if chat else None,
    }
    try:
        if getattr(update, "callback_query", None):
            data["callback_data"] = (update.callback_query.data or "")[:200]
        message = getattr(update, "message", None)
        if message:
            if message.text:
                data["message_text"] = message.text[:200]
            data["has_audio"] = bool(message.audio or message.voice)
            data["has_video"] = bool(message.video)
            data["has_document"] = bool(message.document)
    except Exception:
        pass
    return data


def log_step(update: Optional[Update], kind: str, extra: Optional[dict[str, Any]] = None) -> None:
    """Write both structured event and raw telegram event for diagnostics."""
    if not update:
        return
    payload = _extract_update_meta(update)
    if extra:
        payload.update(extra)
    try:
        log_event(payload.get("user_id"), kind, payload)
    except Exception:
        pass
    try:
        log_telegram_event(update, kind)
    except Exception:
        pass


def log_simple_event(user_id: Optional[int], kind: str, payload: Optional[dict[str, Any]] = None) -> None:
    try:
        log_event(user_id, kind, payload or {})
    except Exception:
        pass


def _extract_update_from_args(*args, **kwargs) -> Optional[Update]:
    update = kwargs.get("update")
    if update:
        return update
    for arg in args:
        if isinstance(arg, Update):
            return arg
    return None


def trace_handler(kind: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to automatically log handler entry."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                update = _extract_update_from_args(*args, **kwargs)
                if update is not None:
                    log_step(update, kind)
                return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            update = _extract_update_from_args(*args, **kwargs)
            if update is not None:
                log_step(update, kind)
            return func(*args, **kwargs)

        return sync_wrapper

    return decorator
