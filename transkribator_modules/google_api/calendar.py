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
) -> dict:
    """Create a blocking event in the primary calendar."""
    service = build_service('calendar', 'v3', credentials)
    body = {
        'summary': title,
        'description': description or '',
        'start': {'dateTime': start_iso},
        'end': {'dateTime': end_iso},
    }
    try:
        event = service.events().insert(calendarId='primary', body=body).execute()
        return event
    except HttpError as exc:
        logger.error("Google Calendar create failed", extra={"error": str(exc)})
        raise
