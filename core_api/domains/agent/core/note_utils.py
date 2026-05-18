"""Helpers for automatic post-processing of notes in beta mode."""

from __future__ import annotations

import ast
import json
import inspect
from datetime import datetime
from typing import Any, Optional

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, NoteService
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.search import IndexService

from .content_processor import _build_summary_and_tags


async def _maybe_await(val):
    """Await val if it's awaitable, otherwise return val directly.

    Tests may monkeypatch async methods with sync functions; this helper
    keeps the caller tolerant to either form.
    """
    try:
        if inspect.isawaitable(val):
            return await val
    except Exception:
        pass
    return val

__all__ = [
    "auto_finalize_note",
    "safe_parse_tags",
    "safe_parse_links",
    "build_note_artifact_content",
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


def _coerce_meta(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            return {}
        if isinstance(data, dict):
            return data
    return {}


def _format_dt(value: Optional[datetime]) -> str:
    if not value:
        return "—"
    try:
        return value.strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return str(value)


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:  # noqa: BLE001
        return str(value)


def _format_timestamp(value: Any) -> str:
    seconds = _coerce_seconds(value)
    if seconds is None:
        return "00:00"
    total = max(0, int(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _coerce_seconds(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return None


def _normalize_segments(payload: Any) -> Optional[list[Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("segments"), (list, tuple)):
            return list(payload["segments"])
        if any(key in payload for key in ("text", "start", "end", "duration", "words")):
            return [payload]
        return None
    if isinstance(payload, (list, tuple)):
        return list(payload)
    return None


def _parse_segments_string(raw: str) -> Optional[list[Any]]:
    stripped = raw.strip()
    if not stripped:
        return []
    for loader in (json.loads, ast.literal_eval):
        try:
            parsed = loader(stripped)
        except Exception:  # noqa: BLE001
            continue
        normalized = _normalize_segments(parsed)
        if normalized is not None:
            return normalized
    return None


def _build_timecode_text(payload: Any) -> str:
    if not payload:
        return ""

    segments_data: Optional[list[Any]] = None
    if isinstance(payload, str):
        parsed = _parse_segments_string(payload)
        if parsed is None:
            return payload.strip()
        segments_data = parsed
    else:
        segments_data = _normalize_segments(payload)

    if not segments_data:
        return _stringify_value(payload).strip()

    lines: list[str] = []
    for segment in segments_data:
        if isinstance(segment, dict):
            text_value = segment.get("text") or segment.get("line") or segment.get("segment")
            if isinstance(text_value, (list, tuple)):
                text_value = " ".join(str(part) for part in text_value if part is not None)
            text = " ".join(str(text_value or "").split())
            if not text and isinstance(segment.get("words"), (list, tuple)):
                tokens = []
                for item in segment["words"]:
                    if isinstance(item, dict):
                        word = item.get("word") or item.get("text")
                    else:
                        word = item
                    if word:
                        tokens.append(str(word))
                text = " ".join(tokens).strip()
            start_raw = segment.get("start") or segment.get("from") or segment.get("offset")
            end_raw = segment.get("end") or segment.get("to") or segment.get("stop")
            duration_raw = segment.get("duration") or segment.get("length")
            speaker = segment.get("speaker") or segment.get("speaker_label") or segment.get("spk")
        else:
            text = " ".join(str(segment).split())
            start_raw = None
            end_raw = None
            duration_raw = None
            speaker = None

        if not text:
            continue

        start_seconds = _coerce_seconds(start_raw)
        end_seconds = _coerce_seconds(end_raw)
        duration_seconds = _coerce_seconds(duration_raw)
        if end_seconds is None and start_seconds is not None and duration_seconds is not None:
            end_seconds = start_seconds + duration_seconds

        start_label = _format_timestamp(start_seconds)
        end_label = _format_timestamp(end_seconds if end_seconds is not None else start_seconds)
        speaker_prefix = f"{speaker}: " if speaker else ""
        lines.append(f"[{start_label} - {end_label}] {speaker_prefix}{text}")

    return "\n".join(lines).strip()


def build_note_artifact_content(
    note: Note,
    note_text: Optional[str],
    *,
    metadata: Optional[dict[str, Any]] = None,
    raw_transcript: Optional[str] = None,
    timecoded_transcript: Optional[str] = None,
) -> str:
    """Compose a human-readable export that includes metadata, summary and transcripts."""
    meta = _coerce_meta(getattr(note, "meta", None))
    if metadata:
        merged = dict(meta)
        merged.update(metadata)
        meta = merged

    title = (
        (getattr(note, "draft_title", None) or "").strip()
        or (getattr(note, "summary", None) or "").strip()
        or f"Заметка #{note.id}"
    )
    summary = (getattr(note, "summary", None) or "").strip() or "—"
    tags = safe_parse_tags(getattr(note, "tags", None))
    links = safe_parse_links(getattr(note, "links", None))

    original_file = (
        meta.get("file_name")
        or meta.get("filename")
        or meta.get("original_file_name")
        or meta.get("source_file_name")
        or meta.get("source_filename")
        or meta.get("original_file")
        or "—"
    )

    links_text = "\n".join(f"- {key}: {value}" for key, value in links.items()) if links else "—"
    tags_text = ", ".join(tags) if tags else "нет"

    raw_text = raw_transcript or meta.get("raw_transcript")
    raw_text = (raw_text if isinstance(raw_text, str) else _stringify_value(raw_text)).strip() if raw_text else ""
    raw_text = raw_text or "—"

    timecodes_blob = timecoded_transcript or meta.get("timecodes_text") or meta.get("timecodes") or meta.get("segments")
    timecodes_text = _build_timecode_text(timecodes_blob)
    timecodes_text = timecodes_text or "—"

    created_ts = getattr(note, "created_at", None) or getattr(note, "ts", None)
    updated_ts = getattr(note, "updated_at", None) or created_ts

    sections = [
        "=== Файл ===",
        f"Оригинальный файл: {original_file}",
        "",
        "=== Метаданные ===",
        f"Note ID: {note.id}",
        f"Название: {title}",
        "",
        f"Создана: {_format_dt(created_ts)}",
        f"Обновлена: {_format_dt(updated_ts)}",
        f"Теги: {tags_text}",
        "Ссылки:",
        links_text,
        "",
        "=== Summary ===",
        summary,
        "",
        "=== Транскрипция ===",
        raw_text,
        "",
        "=== Транскрипция с таймкодами ===",
        timecodes_text,
    ]
    return "\n".join(sections)


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
        needs_summary = not (getattr(note, "summary", None) and getattr(note, "summary", "").strip())
        needs_title = not (getattr(note, "draft_title", None) and getattr(note, "draft_title", "").strip())
        needs_status = (note.status or NoteStatus.INGESTED.value) == NoteStatus.INGESTED.value

        print(f"DEBUG: auto_finalize_note called for {note_id}, needs_summary={needs_summary}, needs_title={needs_title}", flush=True)
        summary_text = note.summary.strip() if note.summary else ""
        tags = existing_tags
        if needs_summary:
            print(f"DEBUG: calling _build_summary_and_tags for {note_id}", flush=True)
            summary_text, tags = await _build_summary_and_tags(
                text_body,
                text_body,
                existing_tags=existing_tags or None,
            )

        # Генерируем короткое название если его нет
        title_text = None
        if needs_title:
            try:
                from transkribator_modules.transcribe.transcriber_v4 import generate_title_with_llm
                title_text = await generate_title_with_llm(text_body)
            except Exception as exc:
                logger.debug(f"Failed to generate title for note {note_id}: {exc}")

        metadata_kwargs: dict[str, object] = {}
        if needs_summary and summary_text:
            metadata_kwargs["summary"] = summary_text
        if needs_title and title_text:
            metadata_kwargs["draft_title"] = title_text
        if needs_status:
            metadata_kwargs["status"] = NoteStatus.PROCESSED.value
        if needs_summary or tags != existing_tags:
            metadata_kwargs["tags"] = tags

        if metadata_kwargs:
            note_service.update_note_metadata(note, **metadata_kwargs)
            db.refresh(note)

        links = safe_parse_links(note.links)
        try:
            await _maybe_await(
                IndexService().add(
                    note.id,
                    note.user_id,
                    note.text or "",
                    summary=note.summary or summary_text,
                    type_hint=note.type_hint or "other",
                    tags=tags,
                    links=links,
                )
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
