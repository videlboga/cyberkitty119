"""Google Calendar helper functions."""

from __future__ import annotations

from typing import Optional

from googleapiclient.errors import HttpError

from transkribator_modules.config import logger
from .service import build_service


def calendar_read_changes(credentials, time_min: str, time_max: str, *, max_results: int = 10) -> list[dict]:
    """Read calendar events between time_min/time_max (RFC3339)."""
    service = build_service('calendar', 'v3', credentials)
    try:
        response = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime',
            maxResults=max(1, min(max_results, 50)),
        ).execute()
        return response.get('items', [])
    except HttpError as exc:
        logger.error("Google Calendar list failed", extra={"error": str(exc)})
        raise


def calendar_create_timebox(
    credentials,
    title: str,
    start_iso: str,
    end_iso: str,
    description: Optional[str] = None,
    time_zone: Optional[str] = None,
) -> dict:
    """Create a blocking event in the primary calendar."""
    service = build_service('calendar', 'v3', credentials)
    body = {
        'summary': title,
        'description': description or '',
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
    }
    if time_zone:
        body['start']['timeZone'] = time_zone
        body['end']['timeZone'] = time_zone
    try:
        event = service.events().insert(calendarId='primary', body=body).execute()
        return event
    except HttpError as exc:
        logger.error("Google Calendar create failed", extra={"error": str(exc)})
        raise


def calendar_get_event(credentials, event_id: str) -> dict:
    """Fetch existing event from the primary calendar."""

    service = build_service('calendar', 'v3', credentials)
    try:
        return service.events().get(calendarId='primary', eventId=event_id).execute()
    except HttpError as exc:
        logger.error("Google Calendar fetch failed", extra={"error": str(exc), "event_id": event_id})
        raise


def calendar_update_timebox(
    credentials,
    event_id: str,
    start_iso: str,
    end_iso: str,
    description: Optional[str] = None,
    time_zone: Optional[str] = None,
) -> dict:
    """Update existing event timing in the primary calendar."""

    service = build_service('calendar', 'v3', credentials)
    body: dict = {
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
    }
    if description is not None:
        body['description'] = description
    if time_zone:
        body['start']['timeZone'] = time_zone
        body['end']['timeZone'] = time_zone
    try:
        event = service.events().patch(
            calendarId='primary',
            eventId=event_id,
            body=body,
        ).execute()
        return event
    except HttpError as exc:
        logger.error("Google Calendar update failed", extra={"error": str(exc), "event_id": event_id})
        raise
