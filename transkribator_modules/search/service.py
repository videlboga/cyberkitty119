"""LLM-assisted note search with metadata filters."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

import dateparser

from transkribator_modules.beta.llm import AgentLLMError, call_agent_llm_with_retry
from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import Note
from transkribator_modules.search.index import IndexService


class NoteSearchError(RuntimeError):
    """Raised when note search fails."""


@dataclass
class NoteSearchSpec:
    query: str
    tag_terms: list[str]
    date_from: Optional[datetime]
    date_to: Optional[datetime]


def _coerce_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, list):
            return [str(tag).strip() for tag in data if str(tag).strip()]
    return []


def _collect_user_tags(user_id: int, limit: int = 30) -> list[str]:
    with SessionLocal() as session:
        rows = (
            session.query(Note.tags)
            .filter(Note.user_id == user_id, Note.status != "archived")
            .limit(500)
            .all()
        )
    unique: list[str] = []
    seen = set()
    for row in rows:
        raw_tags = _coerce_tags(row[0])
        for tag in raw_tags:
            if tag.lower() not in seen:
                seen.add(tag.lower())
                unique.append(tag)
            if len(unique) >= limit:
                break
        if len(unique) >= limit:
            break
    return unique


def _match_tags(known_tags: list[str], candidates: list[str]) -> list[str]:
    if not candidates or not known_tags:
        return []
    matched: list[str] = []
    for cand in candidates:
        cand_clean = cand.strip().lower()
        if not cand_clean:
            continue
        best_tag = None
        best_score = 0.0
        for tag in known_tags:
            tag_clean = tag.lower()
            if cand_clean in tag_clean or tag_clean in cand_clean:
                score = 0.95
            else:
                score = SequenceMatcher(None, cand_clean, tag_clean).ratio()
            if score > best_score:
                best_score = score
                best_tag = tag
        if best_tag and best_score >= 0.55 and best_tag not in matched:
            matched.append(best_tag)
    return matched


def _parse_date(value: Optional[str], base_dt: datetime) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = dateparser.parse(
            value,
            settings={"RELATIVE_BASE": base_dt, "RETURN_AS_TIMEZONE_AWARE": True},
        )
    except Exception:  # noqa: BLE001
        parsed = None
    if not parsed:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=base_dt.tzinfo or timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_search_payload(raw: str) -> dict[str, Any]:
    """Parse LLM response that is *supposed* to be JSON, but may contain wrappers."""
    text = (raw or "").strip()
    if not text:
        raise NoteSearchError("LLM вернул некорректный JSON для поиска")

    candidates: list[str] = []

    # ```json { ... } ``` style
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1).strip())

    # First/last brace slice
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1].strip())

    # As-is fallback
    candidates.append(text)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    logger.warning(
        "LLM intent parser returned invalid JSON",
        extra={"raw_response_snippet": text[:500]},
    )
    raise NoteSearchError("LLM вернул некорректный JSON для поиска")


async def _build_search_spec(query: str, now: datetime, known_tags: list[str]) -> NoteSearchSpec:
    instructions = (
        "Ты ассистент, который превращает пользовательский запрос поиска заметок "
        "в структуру фильтров. Всегда отвечай JSON без дополнительного текста.\n"
        "Структура: {\n"
        '  "search_query": "<короткая формулировка запроса>",\n'
        '  "tag_terms": ["список возможных тегов или тематик"],\n'
        '  "date_from": "ISO-8601 дата или null",\n'
        '  "date_to": "ISO-8601 дата или null"\n'
        "}\n"
        "Если пользователь упоминает относительные периоды, вычисли даты, "
        "используя текущие дату/время."
    )
    user_payload = (
        f"CURRENT_DATETIME: {now.isoformat()}\n"
        f"KNOWN_TAGS: {', '.join(known_tags) if known_tags else '—'}\n"
        f"QUERY: {query}"
    )
    messages = [
        {"role": "system", "content": instructions},
        {"role": "user", "content": user_payload},
    ]
    try:
        raw = await call_agent_llm_with_retry(messages, timeout=30.0)
    except AgentLLMError as exc:
        raise NoteSearchError(f"LLM intent parser unavailable: {exc}") from exc

    payload = _parse_search_payload(raw)

    search_query = str(payload.get("search_query") or query).strip()
    tag_terms = payload.get("tag_terms") or []
    if not isinstance(tag_terms, list):
        tag_terms = []
    tag_terms = [str(term).strip() for term in tag_terms if str(term).strip()]

    date_from = _parse_date(payload.get("date_from"), now)
    date_to = _parse_date(payload.get("date_to"), now)

    return NoteSearchSpec(
        query=search_query or query,
        tag_terms=tag_terms,
        date_from=date_from,
        date_to=date_to,
    )


def _build_context(matches: list[dict]) -> str:
    lines: list[str] = []
    for idx, match in enumerate(matches, start=1):
        note = match.get("note") or {}
        tags = note.get("tags") or []
        tags_text = ", ".join(tags) if tags else "—"
        ts = note.get("ts") or "-"
        snippet = (match.get("chunk") or "").strip().replace("\n", " ")
        if len(snippet) > 600:
            snippet = snippet[:600].rstrip() + "…"
        summary = (note.get("summary") or "").strip()
        if summary and len(summary) > 400:
            summary = summary[:400].rstrip() + "…"
        lines.append(
            f"[{idx}] Заметка #{note.get('id', '?')} — {ts}\n"
            f"Теги: {tags_text}\n"
            f"Summary: {summary or '—'}\n"
            f"Фрагмент: {snippet or '—'}"
        )
    return "\n\n".join(lines)


async def _summarize_matches(user_query: str, context_text: str) -> str:
    system_prompt = (
        "Ты помощник, который ищет ответы в заметках пользователя. "
        "Используй только предоставленный контекст. "
        "Если ответа нет, честно скажи об этом."
    )
    user_prompt = (
        f"Запрос: {user_query}\n\n"
        f"Контекст заметок:\n{context_text}\n\n"
        "Ответь коротко и по делу на русском языке."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        return await call_agent_llm_with_retry(messages, timeout=40.0)
    except AgentLLMError as exc:
        raise NoteSearchError(f"LLM summarizer unavailable: {exc}") from exc


async def run_note_search(user_id: int, query: str, max_results: int = 5) -> dict:
    """Run semantic note search and return agent response plus metadata."""
    now = datetime.now(timezone.utc)
    known_tags = _collect_user_tags(user_id)
    spec = await _build_search_spec(query, now, known_tags)
    matched_tags = _match_tags(known_tags, spec.tag_terms)

    date_from = spec.date_from.isoformat() if spec.date_from else None
    date_to = spec.date_to.isoformat() if spec.date_to else None

    index = IndexService()
    matches = await index.search(
        user_id=user_id,
        query=spec.query,
        k=max_results,
        tags=matched_tags or None,
        date_from=date_from,
        date_to=date_to,
    )

    if not matches:
        return {
            "response": "Не нашёл заметок, подходящих под запрос. Попробуй уточнить формулировку.",
            "matches": [],
        }

    context_text = _build_context(matches)
    try:
        summary = await _summarize_matches(query, context_text)
    except NoteSearchError as exc:
        logger.warning("Note search summarizer failed", extra={"error": str(exc)})
        summary = "Нашёл несколько заметок, но не смог построить обзор. Вот список:"

    note_lines = []
    for idx, match in enumerate(matches, start=1):
        note = match.get("note") or {}
        tags = ", ".join(note.get("tags") or [])
        ts = note.get("ts") or "-"
        note_lines.append(
            f"{idx}. Заметка #{note.get('id', '?')} — {ts} ({tags or 'без тегов'})"
        )

    response = f"{summary.strip()}\n\nПохожие заметки:\n" + "\n".join(note_lines)
    return {"response": response.strip(), "matches": matches}
