"""
Helpers for sending plan expiration reminders to Telegram users.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

import httpx
from sqlalchemy.orm import Session
from zoneinfo import ZoneInfo

from transkribator_modules.config import (
    BOT_TOKEN,
    LOCAL_BOT_API_URL,
    USE_LOCAL_BOT_API,
    logger,
)
from transkribator_modules.db.database import (
    DEFAULT_PLAN_DISPLAY_NAMES,
    SessionLocal,
)
from transkribator_modules.db.models import Event, Plan, PlanType, User

PRE_EXPIRY_KIND = "plan_pre_expiry_notification"
EXPIRED_KIND = "plan_expired_notification"
PRE_EXPIRY_WINDOW = timedelta(days=3)
EXPIRED_LOOKBACK = timedelta(days=3)


@dataclass(frozen=True)
class PlanNotification:
    user_id: int
    telegram_id: int
    kind: str
    plan_expires_at: datetime
    message: str


def _isoformat(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _get_plan_names(session: Session) -> dict[str, str]:
    """Return mapping of plan slug -> display name."""
    plan_rows = session.query(Plan.name, Plan.display_name).all()
    names = {name: display or name for name, display in plan_rows}
    names.update(DEFAULT_PLAN_DISPLAY_NAMES)
    return names


def _resolve_timezone(user: User) -> Optional[ZoneInfo]:
    tz_name = getattr(user, "timezone", None) or "Europe/Moscow"
    try:
        return ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 - fallback to UTC
        try:
            return ZoneInfo("Europe/Moscow")
        except Exception:
            return None


def _format_local(dt: datetime, tz: Optional[ZoneInfo]) -> str:
    aware = dt.replace(tzinfo=timezone.utc)
    if tz:
        aware = aware.astimezone(tz)
    return aware.strftime("%d.%m.%Y %H:%M")


def _already_sent(
    session: Session,
    user_id: int,
    kind: str,
    plan_expires_at: datetime,
) -> bool:
    threshold = plan_expires_at - timedelta(days=60)
    query = (
        session.query(Event)
        .filter(Event.user_id == user_id, Event.kind == kind)
        .order_by(Event.ts.desc())
    )
    if threshold:
        query = query.filter(Event.ts >= threshold)
    target_iso = _isoformat(plan_expires_at)

    for entry in query.all():
        if not entry.payload:
            continue
        try:
            payload = json.loads(entry.payload)
        except Exception:  # noqa: BLE001 - ignore broken payloads
            continue
        if payload.get("plan_expires_at") == target_iso:
            return True
    return False


def _pre_expiry_message(
    user: User,
    now: datetime,
    plan_expires_at: datetime,
    plan_name: str,
) -> str:
    days_left = max(
        1,
        math.ceil((plan_expires_at - now).total_seconds() / 86400),
    )
    tz = _resolve_timezone(user)
    local_ts = _format_local(plan_expires_at, tz)
    return (
        f"⏰ До окончания тарифа {plan_name} осталось {days_left} дн. "
        f"(до {local_ts}).\n\n"
        "Продлите подписку заранее, чтобы сохранить полный доступ: /plans"
    )


def _expired_message(user: User, plan_expires_at: datetime, plan_name: str) -> str:
    tz = _resolve_timezone(user)
    local_ts = _format_local(plan_expires_at, tz)
    return (
        f"⚠️ Тариф {plan_name} закончился {local_ts}.\n\n"
        "Сервис переключится на бесплатный план с ограничениями. "
        "Продлите подписку, чтобы вернуть полный доступ: /plans"
    )


def _telegram_endpoint(method: str) -> str:
    base = LOCAL_BOT_API_URL if USE_LOCAL_BOT_API else "https://api.telegram.org"
    return f"{base.rstrip('/')}/bot{BOT_TOKEN}/{method}"


def _dispatch_notifications(notifications: Iterable[PlanNotification]) -> int:
    sent = 0
    endpoint = _telegram_endpoint("sendMessage")
    notifications = list(notifications)
    if not notifications:
        return sent

    logger.info(
        "Sending plan reminders",
        extra={"count": len(notifications)},
    )
    with httpx.Client(timeout=10.0) as client:
        for item in notifications:
            payload = {
                "chat_id": item.telegram_id,
                "text": item.message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            try:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    logger.warning(
                        "Telegram API rejected reminder",
                        extra={
                            "user_id": item.user_id,
                            "kind": item.kind,
                            "response": data,
                        },
                    )
                    continue
            except Exception as exc:  # noqa: BLE001 - log and continue
                logger.warning(
                    "Failed to send plan reminder",
                    extra={
                        "user_id": item.user_id,
                        "kind": item.kind,
                        "error": str(exc),
                    },
                )
                continue

            sent += 1

            # Lazy import to avoid circular dependency on module import.
            from transkribator_modules.db.database import log_event  # pylint: disable=import-outside-toplevel

            log_event(
                item.user_id,
                item.kind,
                {
                    "plan_expires_at": _isoformat(item.plan_expires_at),
                },
            )
    return sent


def collect_plan_notifications(
    session: Session,
    now: Optional[datetime] = None,
) -> List[PlanNotification]:
    now = now or datetime.utcnow()
    notifications: List[PlanNotification] = []
    plan_names = _get_plan_names(session)

    candidates = (
        session.query(User)
        .filter(
            User.plan_expires_at.isnot(None),
            User.current_plan != PlanType.FREE.value,
            User.is_active.is_(True),
        )
        .all()
    )

    for user in candidates:
        expires_at = user.plan_expires_at
        if not isinstance(expires_at, datetime):
            continue

        plan_name = plan_names.get(user.current_plan, user.current_plan or "тариф")

        if expires_at <= now:
            if now - expires_at > EXPIRED_LOOKBACK:
                continue
            if _already_sent(session, user.id, EXPIRED_KIND, expires_at):
                continue
            message = _expired_message(user, expires_at, plan_name)
            notifications.append(
                PlanNotification(
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    kind=EXPIRED_KIND,
                    plan_expires_at=expires_at,
                    message=message,
                )
            )
            continue

        remaining = expires_at - now
        if remaining <= PRE_EXPIRY_WINDOW:
            if _already_sent(session, user.id, PRE_EXPIRY_KIND, expires_at):
                continue
            message = _pre_expiry_message(user, now, expires_at, plan_name)
            notifications.append(
                PlanNotification(
                    user_id=user.id,
                    telegram_id=user.telegram_id,
                    kind=PRE_EXPIRY_KIND,
                    plan_expires_at=expires_at,
                    message=message,
                )
            )

    return notifications


def send_plan_reminders(now: Optional[datetime] = None) -> int:
    """Collect and send plan notifications. Returns number of messages sent."""
    session = SessionLocal()
    try:
        notifications = collect_plan_notifications(session, now=now)
    finally:
        session.close()

    return _dispatch_notifications(notifications)


def send_expired_notification(user: User, plan_expires_at: datetime) -> bool:
    """
    Send an expiration notification for a specific user.

    Returns True if the notification was sent (or already sent previously),
    False if sending failed.
    """
    if not isinstance(plan_expires_at, datetime):
        return False

    session = SessionLocal()
    try:
        if user.current_plan == PlanType.FREE.value:
            # User already downgraded; still check whether we owe a reminder.
            pass
        if _already_sent(session, user.id, EXPIRED_KIND, plan_expires_at):
            return True

        plan_names = _get_plan_names(session)
        plan_name = plan_names.get(user.current_plan, user.current_plan or "тариф")
        message = _expired_message(user, plan_expires_at, plan_name)
        notification = PlanNotification(
            user_id=user.id,
            telegram_id=user.telegram_id,
            kind=EXPIRED_KIND,
            plan_expires_at=plan_expires_at,
            message=message,
        )
    finally:
        session.close()

    sent = _dispatch_notifications([notification])
    return sent > 0


__all__ = [
    "send_plan_reminders",
    "send_expired_notification",
    "collect_plan_notifications",
    "PlanNotification",
    "PRE_EXPIRY_KIND",
    "EXPIRED_KIND",
]

