"""Helpers for automatic post-processing of notes in beta mode."""

from __future__ import annotations

import json
from typing import Optional

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, NoteService
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.search import IndexService

from .content_processor import _build_summary_and_tags

__all__ = [
    "auto_finalize_note",
    "safe_parse_tags",
    "safe_parse_links",
]


def safe_parse_tags(raw) -> list[str]:
    """Return list of string tags from db payload."""
    if not raw:
        return []
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    result: list[str] = []
    for item in data:
        if item is None:
            continue
        candidate = str(item).strip()
        if candidate:
            result.append(candidate[:48])
    return result


def safe_parse_links(raw) -> dict[str, str]:
    """Return dict of links from db payload."""
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str):
            cleaned[key] = value
    return cleaned


async def auto_finalize_note(note_id: int) -> Optional[Note]:
    """Ensure note has summary, tags, status and is indexed."""

    db = SessionLocal()
    try:
        note_service = NoteService(db)
        note = note_service.get_note(note_id)
        if not note:
            return None

        text_body = (note.text or "").strip()
        if not text_body:
            return note

        existing_tags = safe_parse_tags(note.tags)
        needs_summary = not (note.summary and note.summary.strip())
        needs_status = (note.status or NoteStatus.INGESTED.value) == NoteStatus.INGESTED.value

        summary_text = note.summary.strip() if note.summary else ""
        tags = existing_tags
        if needs_summary:
            summary_text, tags = await _build_summary_and_tags(
                text_body,
                text_body,
                existing_tags=existing_tags or None,
            )

        metadata_kwargs: dict[str, object] = {}
        if needs_summary and summary_text:
            metadata_kwargs["summary"] = summary_text
        if needs_status:
            metadata_kwargs["status"] = NoteStatus.PROCESSED.value
        if needs_summary or tags != existing_tags:
            metadata_kwargs["tags"] = tags

        if metadata_kwargs:
            note_service.update_note_metadata(note, **metadata_kwargs)
            db.refresh(note)

        links = safe_parse_links(note.links)
        try:
            IndexService().add(
                note.id,
                note.user_id,
                note.text or "",
                summary=note.summary or summary_text,
                type_hint=note.type_hint or "other",
                tags=tags,
                links=links,
            )
        except Exception as index_exc:  # noqa: BLE001
            logger.warning(
                "Auto indexing failed",
                extra={"note_id": note.id, "error": str(index_exc)},
            )
        return note
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto finalize note failed", extra={"note_id": note_id, "error": str(exc)})
        return None
    finally:
        db.close()
