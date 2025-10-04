"""Tools available to the beta agent runtime."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from transkribator_modules.config import FEATURE_GOOGLE_CALENDAR, logger
from transkribator_modules.db.database import (
    EventService,
    NoteService,
    SessionLocal,
    UserService,
)
from transkribator_modules.db.models import Note, NoteStatus, User
from transkribator_modules.google_api import (GoogleCredentialService,
                                              calendar_create_timebox,
                                              calendar_get_event,
                                              calendar_update_timebox)
from transkribator_modules.search import IndexService
from .content_processor import ContentProcessor
from .presets import get_free_prompt
from .timezone import timezone_required_message
from .command_processor import _format_generation_response

if TYPE_CHECKING:  # pragma: no cover - circular import guard
    from .agent_runtime import AgentSession


@dataclass(slots=True)
class ToolResult:
    message: str
    details: Optional[dict[str, Any]] = None
    suggestion: Optional[str] = None


@dataclass(slots=True)
class AgentTool:
    name: str
    description: str
    args_schema: dict[str, Any]
    func: Callable[["AgentSession", dict[str, Any]], "asyncio.Future[Any] | Any"]
    requires_note: bool = False


NOTE_PREVIEW_LEN = 60
_content_processor = ContentProcessor()


def _with_session(func: Callable[["AgentSession", SessionLocal, dict[str, Any]], ToolResult]) -> Callable[["AgentSession", dict[str, Any]], ToolResult]:
    """Helper decorator to create and cleanup DB sessions inside tools."""

    def wrapper(session: "AgentSession", args: dict[str, Any]) -> ToolResult:
        db = SessionLocal()
        try:
            return func(session, db, args)
        finally:
            db.close()

    return wrapper


def _coerce_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    return []


def _coerce_links(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return data
    return {}


def _ensure_google_credentials(db, user, action: str) -> tuple[Optional[object], Optional[str]]:
    service = GoogleCredentialService(db)
    try:
        credentials = service.get_credentials(user.id)
    except RuntimeError:
        return None, 'Нужно заново подключить Google аккаунт.'
    except Exception as exc:  # noqa: BLE001
        logger.error('Google credentials fetch failed', extra={'user_id': user.id, 'error': str(exc), 'action': action})
        return None, 'Google сервис сейчас недоступен. Попробуй позже.'
    if not credentials:
        return None, 'Сначала подключи Google аккаунт в личном кабинете.'
    return credentials, None


def _current_tz():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _ensure_rfc3339(value: Optional[str], *, fallback: Optional[datetime] = None) -> str:
    if value:
        dt = _parse_datetime(value)
    elif fallback is not None:
        dt = fallback
    else:
        dt = datetime.now().astimezone()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_current_tz())
    return dt.isoformat()


def _parse_datetime(value: str, tz_name: Optional[str] = None) -> datetime:
    text = (value or '').strip()
    tzinfo = _resolve_timezone(tz_name) or _current_tz()
    reference = datetime.now(tzinfo)

    cleaned = text.lower()
    day_offset = 0
    if 'послезавтра' in cleaned:
        day_offset = 2
        cleaned = cleaned.replace('послезавтра', ' ')
    elif 'завтра' in cleaned:
        day_offset = 1
        cleaned = cleaned.replace('завтра', ' ')
    elif 'today' in cleaned:
        cleaned = cleaned.replace('today', ' ')
    elif 'сегодня' in cleaned:
        cleaned = cleaned.replace('сегодня', ' ')

    cleaned = cleaned.replace(' в ', ' ').strip()
    cleaned = cleaned.replace('в ', '').strip()
    cleaned = cleaned.replace(' по ', ' ').strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)

    if re.fullmatch(r'\d{1,2}:\d{2}', cleaned):
        hours, minutes = map(int, cleaned.split(':'))
        result = reference.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        if day_offset:
            result += timedelta(days=day_offset)
        return result

    candidate = cleaned.replace(' ', 'T')
    if len(candidate) == 10:
        candidate += 'T00:00:00'
    if len(candidate) == 16:
        candidate += ':00'
    if candidate.endswith('Z') and '+' not in candidate:
        candidate = candidate[:-1] + '+00:00'
    dt = datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tzinfo)
    if day_offset:
        dt += timedelta(days=day_offset)
    return dt


def _coerce_meta(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return data
    return {}


def _extract_keywords(text: str | None) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[0-9]+:[0-9]+|[\wА-Яа-яёЁ]+", text.lower())
    return [tok for tok in tokens if len(tok) > 2 or ":" in tok]


def _note_preview(note: Note) -> str:
    snippet_source = (note.summary or note.text or '').strip()
    if not snippet_source:
        snippet = 'без названия'
    else:
        snippet = snippet_source.splitlines()[0]
        if len(snippet) > NOTE_PREVIEW_LEN:
            snippet = snippet[: NOTE_PREVIEW_LEN - 1] + '…'
    return f"#{note.id}: {snippet}"


def _tz_label(tzinfo: Optional[timezone]) -> Optional[str]:
    if tzinfo is None:
        return None
    key = getattr(tzinfo, 'key', None)
    if key:
        return key
    offset = tzinfo.utcoffset(None)
    if offset is None:
        return None
    minutes = int(offset.total_seconds() // 60)
    sign = '+' if minutes >= 0 else '-'
    hours, mins = divmod(abs(minutes), 60)
    return f'UTC{sign}{hours:02d}:{mins:02d}'


def _resolve_timezone(name: Optional[str]) -> Optional[timezone]:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        if name.startswith('UTC') and len(name) >= 4:
            sign = 1 if name[3] != '-' else -1
            try:
                hours, mins = name[4:].split(':')
                delta = timedelta(hours=int(hours), minutes=int(mins))
                return timezone(sign * delta)
            except Exception:  # noqa: BLE001
                return None
    return None


def _extract_event_id_from_link(link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    try:
        parsed = urlparse(link)
        query = parse_qs(parsed.query)
        if 'eid' in query:
            encoded = query['eid'][0]
        elif parsed.path.startswith('/calendar/event/'):
            encoded = parsed.path.rsplit('/', 1)[-1]
        else:
            return None
        encoded = encoded.replace(' ', '+')
        padded = encoded + '=' * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
        parts = decoded.split(' ')
        if parts:
            return parts[0]
    except Exception as exc:  # noqa: BLE001
        logger.debug('Failed to extract event id', extra={'link': link, 'error': str(exc)})
    return None


def _find_calendar_note(db, user_id: int, keywords: list[str]) -> list[dict[str, Any]]:
    candidates = (
        db.query(Note)
        .filter(Note.user_id == user_id)
        .order_by(Note.id.desc())
        .limit(50)
        .all()
    )
    norm_keywords = [kw for kw in keywords if kw]
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        meta = _coerce_meta(candidate.meta)
        links = _coerce_links(candidate.links)
        event_id = meta.get('calendar_event_id') or _extract_event_id_from_link(links.get('calendar_url'))
        if not event_id:
            continue
        text_blob = f"{candidate.summary or ''} {candidate.text or ''}".lower()
        score = 0
        if norm_keywords:
            matches_keywords = [kw for kw in norm_keywords if kw in text_blob]
            score = len(matches_keywords)
        matches.append(
            {
                'note': candidate,
                'event_id': event_id,
                'timezone': meta.get('calendar_timezone'),
                'link': links.get('calendar_url'),
                'score': score,
                'text': text_blob,
            }
        )

    matches.sort(key=lambda item: (item['score'], item['note'].id), reverse=True)
    return matches


@_with_session
def _tool_save_note(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    note_id = args.get("note_id") or session.active_note_id
    if not note_id:
        return ToolResult(message="Не нашёл заметку для сохранения.")

    status = args.get("status") or NoteStatus.APPROVED.value
    summary = args.get("summary")
    tags = _coerce_tags(args.get("tags")) or None

    note_service = NoteService(db)
    index = IndexService()
    note = note_service.get_note(note_id)
    if not note or note.user_id != session.user_db_id:
        return ToolResult(message="Заметка не найдена или принадлежит другому пользователю.")

    note_service.update_note_metadata(note, summary=summary, tags=tags, status=status)
    index.add(note.id, session.user_db_id, note.text or "", summary=note.summary or "", type_hint=note.type_hint)
    message = f"Заметка #{note.id} сохранена со статусом {status}."
    if summary:
        message += " Обновил краткое описание."
    if tags:
        message += f" Теги: {', '.join(tags)}."
    return ToolResult(message=message)


@_with_session
def _tool_update_text(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    note_id = args.get("note_id") or session.active_note_id
    if not note_id:
        return ToolResult(message="Не нашёл заметку для обновления.")

    new_text = args.get("text")
    append_text = args.get("append")
    if not new_text and not append_text:
        return ToolResult(message="Нет текста для обновления.")

    note_service = NoteService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != session.user_db_id:
        return ToolResult(message="Заметка не найдена или принадлежит другому пользователю.")

    if new_text:
        note.text = new_text
    if append_text:
        base = (note.text or "").rstrip()
        addition = append_text.strip()
        note.text = f"{base}\n\n{addition}" if base else addition
    note.status = args.get("status") or note.status or NoteStatus.PROCESSED.value
    db.commit()
    db.refresh(note)

    if args.get("reindex", True):
        IndexService().add(note.id, session.user_db_id, note.text or "", summary=note.summary or "", type_hint=note.type_hint)

    return ToolResult(message=f"Заметка #{note.id} обновлена." )


@_with_session
def _tool_create_task(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    description = args.get("text") or args.get("description") or ""
    if not description.strip():
        return ToolResult(message="Текст задачи пустой, пропустил создание.")

    tags = _coerce_tags(args.get("tags"))
    note_service = NoteService(db)
    user_service = UserService(db)
    user = user_service.get_user_by_id(session.user_db_id)
    if not user:
        return ToolResult(message="Пользователь не найден.")

    note = note_service.create_note(
        user=user,
        text=description,
        type_hint="task",
        summary=args.get("summary"),
        tags=tags,
        status=args.get("status") or NoteStatus.PROCESSED.value,
    )
    IndexService().add(note.id, session.user_db_id, note.text or "", summary=note.summary or "", type_hint="task")
    message = f"Создал задачу #{note.id}."
    if tags:
        message += f" Теги: {', '.join(tags)}."
    return ToolResult(message=message)


@_with_session
def _tool_search_notes(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    query = args.get("query") or args.get("text")
    if not (query and query.strip()):
        return ToolResult(message="Нет запроса для поиска.")

    index = IndexService()
    results = index.search(session.user_db_id, query.strip(), k=int(args.get("k") or 3))
    if not results:
        return ToolResult(message="По запросу ничего не нашлось.")

    lines: list[str] = []
    for item in results[:5]:
        note = item.get("note", {})
        summary = note.get("summary") or (note.get("text") or "")[:120]
        note_id = note.get("id")
        lines.append(f"• #{note_id}: {summary}")
    return ToolResult(message="Нашёл заметки:\n" + "\n".join(lines))


async def _tool_free_prompt(session: "AgentSession", args: dict[str, Any]) -> ToolResult:
    note_id = args.get("note_id") or session.active_note_id
    if not note_id:
        return ToolResult(message="Нужно выбрать заметку, чтобы обработать её промптом.")

    prompt = (args.get("prompt") or args.get("text") or "").strip()
    if not prompt:
        return ToolResult(message="Напиши, что сделать с заметкой — например, 'сделай саммари'.")

    db = SessionLocal()
    try:
        note_service = NoteService(db)

        note = note_service.get_note(note_id)
        if not note or note.user_id != session.user_db_id:
            return ToolResult(message="Заметка не найдена или принадлежит другому пользователю.")

        user = db.query(User).filter(User.id == session.user_db_id).one_or_none()
        if not user:
            return ToolResult(message="Пользователь не найден.")

        preset = get_free_prompt()
        if not preset:
            return ToolResult(message="Свободный промпт сейчас недоступен.")

        try:
            result = await _content_processor.process(
                user,
                note.text or "",
                note.type_hint or "other",
                preset,
                NoteStatus.PROCESSED.value,
                custom_prompt=prompt,
                tags=_coerce_tags(note.tags),
                type_confidence=note.type_confidence,
                existing_note_id=note.id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Free prompt tool failed",
                extra={"note_id": note.id, "error": str(exc)},
            )
            return ToolResult(message="Не удалось обработать заметку. Попробуй позже.")

        db.refresh(note)
        session.update_note_snapshot(
            text=note.text,
            summary=note.summary,
            links=_coerce_links(note.links),
        )

        message = _format_generation_response("free_prompt", result)
        return ToolResult(message=message)
    finally:
        db.close()


@_with_session
def _tool_suggest_calendar(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    note_id = args.get("note_id") or session.active_note_id
    if not note_id:
        return ToolResult(message="Нет заметки, к которой привязать встречу.")

    title = args.get("title") or "Встреча"
    when = args.get("when") or args.get("start")
    description = args.get("description")

    event_service = EventService(db)
    payload = {
        "note_id": note_id,
        "title": title,
        "when": when,
        "description": description,
    }
    event_service.add_event(session.user_db_id, "calendar_suggestion", payload)
    suggestion = f"Предлагаю запланировать встречу: {title}" + (f", когда: {when}" if when else "")
    return ToolResult(message="Сохранил предложение встречи.", suggestion=suggestion, details={"event": payload})


@_with_session
def _tool_create_calendar_event(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    if not FEATURE_GOOGLE_CALENDAR:
        return ToolResult(message="Интеграция с календарём отключена.")

    user = db.query(User).filter(User.id == session.user_db_id).one_or_none()
    if not user:
        return ToolResult(message="Пользователь не найден.")

    tz_message = timezone_required_message(user)
    if tz_message:
        return ToolResult(message=tz_message)
    user_tz = getattr(user, 'timezone', None)

    credentials, error = _ensure_google_credentials(db, user, 'agent_calendar_event')
    if error:
        return ToolResult(message=error)

    note_service = NoteService(db)
    note = None
    note_id = args.get('note_id') or session.active_note_id
    if note_id:
        note = note_service.get_note(note_id)
        if not note or note.user_id != user.id:
            note = None

    raw_start = args.get('start') or args.get('when')
    raw_end = args.get('end')
    duration = args.get('duration_minutes') or args.get('duration') or 60

    try:
        duration = int(duration)
        if duration <= 0:
            raise ValueError
    except ValueError:
        duration = 60

    calendar_tz = user_tz

    if raw_start:
        try:
            start_dt = _parse_datetime(str(raw_start), calendar_tz)
        except ValueError:
            start_dt = datetime.now().astimezone()
    else:
        start_dt = datetime.now().astimezone()

    if raw_end:
        try:
            end_dt = _parse_datetime(str(raw_end), calendar_tz)
        except ValueError:
            end_dt = start_dt + timedelta(minutes=duration)
    else:
        end_dt = start_dt + timedelta(minutes=duration)

    title = (args.get('title') or '').strip()
    if not title:
        if note and (note.summary or note.text):
            title = (note.summary or note.text or '').strip().split('\n')[0][:120] or 'Встреча'
        else:
            title = 'Встреча'

    description_parts: list[str] = []
    if args.get('description'):
        description_parts.append(str(args['description']).strip())
    if note and (note.summary or note.text):
        snippet = (note.summary or note.text or '').strip()[:400]
        if snippet:
            description_parts.append(f"Из заметки #{note.id}:\n{snippet}")
    description = '\n\n'.join(part for part in description_parts if part)

    start_iso = _ensure_rfc3339(None, fallback=start_dt)
    end_iso = _ensure_rfc3339(None, fallback=end_dt)

    try:
        event = calendar_create_timebox(
            credentials,
            title,
            start_iso,
            end_iso,
            description or None,
            time_zone=user_tz,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error('Calendar event creation failed', extra={'user_id': user.id, 'error': str(exc)})
        return ToolResult(message='Не удалось создать событие в календаре. Попробуй позже.')

    link = event.get('htmlLink') or event.get('hangoutLink') or title
    if note:
        start_info = event.get('start') or {}
        event_tz = start_info.get('timeZone')
        if not event_tz:
            dt_raw = start_info.get('dateTime')
            if dt_raw:
                try:
                    dt = datetime.fromisoformat(dt_raw.replace('Z', '+00:00'))
                    event_tz = _tz_label(dt.tzinfo)
                except Exception:  # noqa: BLE001
                    event_tz = None
        meta_update: dict[str, Any] = {}
        event_id = event.get('id')
        if event_id:
            meta_update['calendar_event_id'] = event_id
        if event_tz:
            meta_update['calendar_timezone'] = event_tz
        elif user_tz:
            meta_update['calendar_timezone'] = user_tz
        link_payload = {'calendar_url': event['htmlLink']} if event.get('htmlLink') else None
        if meta_update or link_payload:
            note_service.update_note_metadata(note, meta=meta_update or None, links=link_payload)

    note_label = _note_preview(note) if note else ''
    when_label = start_dt.strftime('%d.%m %H:%M')
    message = f"🗓 Создал встречу {note_label} на {when_label}." if note_label else f"🗓 Добавил событие: {link}"
    suggestion = None
    if not note_id:
        suggestion = 'Привяжи событие к заметке, чтобы не потерять контекст.'
    return ToolResult(message=message, details={'event': event}, suggestion=suggestion)


@_with_session
def _tool_update_calendar_event(session: "AgentSession", db, args: dict[str, Any]) -> ToolResult:
    if not FEATURE_GOOGLE_CALENDAR:
        return ToolResult(message="Интеграция с календарём отключена.")

    user = db.query(User).filter(User.id == session.user_db_id).one_or_none()
    if not user:
        return ToolResult(message="Пользователь не найден.")

    tz_message = timezone_required_message(user)
    if tz_message:
        return ToolResult(message=tz_message)

    credentials, error = _ensure_google_credentials(db, user, 'agent_calendar_update')
    if error:
        return ToolResult(message=error)

    note_service = NoteService(db)
    note_id = args.get('note_id') or session.active_note_id
    if not note_id:
        return ToolResult(message="Нужно указать заметку с привязанной встречей.")

    note = note_service.get_note(note_id)
    if not note or note.user_id != user.id:
        return ToolResult(message="Заметка не найдена или принадлежит другому пользователю.")

    meta = _coerce_meta(note.meta)
    links = _coerce_links(note.links)
    calendar_tz = meta.get('calendar_timezone')
    event_id = args.get('event_id') or meta.get('calendar_event_id')
    if not event_id and links.get('calendar_url'):
        event_id = _extract_event_id_from_link(links.get('calendar_url'))

    matches: list[dict[str, Any]] = []
    search_keywords: list[str] = []
    if not event_id:
        search_basis = ' '.join(
            filter(
                None,
                [
                    note.summary,
                    note.text,
                    args.get('title'),
                    str(args.get('start') or args.get('when') or ''),
                ],
            )
        )
        search_keywords = _extract_keywords(search_basis)
        matches = _find_calendar_note(db, user.id, search_keywords)
        if not matches:
            logger.info(
                'Calendar event id missing',
                extra={
                    'note_id': note.id,
                    'links': links,
                    'meta': meta,
                },
            )
            return ToolResult(message="Не нашёл связанную встречу. Укажи, из какой заметки переносим, или создай новую." )

        top = matches[0]
        same_score = [match for match in matches if match['score'] == top['score']]
        if len(matches) > 1 and (not search_keywords or len(same_score) > 1):
            options = '\n'.join(_note_preview(match['note']) for match in same_score[:5])
            return ToolResult(
                message=(
                    "Нашёл несколько подходящих встреч. Уточни, с какой заметкой работаем:\n"
                    + options
                    + "\nОтправь номер заметки или сформулируй запрос точнее."
                )
            )

        top_match = top
        note = top_match['note']
        note_id = note.id
        meta = _coerce_meta(note.meta)
        links = _coerce_links(note.links)
        event_id = top_match['event_id']
        calendar_tz = top_match['timezone'] or meta.get('calendar_timezone')
        if top_match['link'] and not links.get('calendar_url'):
            links['calendar_url'] = top_match['link']
        session.set_active_note(note)

    event_snapshot: Optional[dict[str, Any]] = None
    if not calendar_tz or not links.get('calendar_url'):
        try:
            event_snapshot = calendar_get_event(credentials, event_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug('Calendar event fetch failed', extra={'user_id': user.id, 'event_id': event_id, 'error': str(exc)})
        if event_snapshot:
            start_info = event_snapshot.get('start') or {}
            calendar_tz = calendar_tz or start_info.get('timeZone')
            if not links.get('calendar_url') and event_snapshot.get('htmlLink'):
                links['calendar_url'] = event_snapshot['htmlLink']

    raw_start = args.get('start') or args.get('when')
    if not raw_start:
        return ToolResult(message="Расскажи, на какое время перенести встречу.")

    raw_end = args.get('end')
    duration = args.get('duration_minutes') or args.get('duration') or 60
    try:
        duration = int(duration)
        if duration <= 0:
            raise ValueError
    except ValueError:
        duration = 60

    try:
        start_dt = _parse_datetime(str(raw_start), calendar_tz)
    except ValueError:
        return ToolResult(message="Не смог распознать дату. Пример: 2024-10-02 13:30")

    if raw_end:
        try:
            end_dt = _parse_datetime(str(raw_end), calendar_tz)
        except ValueError:
            end_dt = start_dt + timedelta(minutes=duration)
    else:
        end_dt = start_dt + timedelta(minutes=duration)

    description_parts: list[str] = []
    if args.get('description'):
        description_parts.append(str(args['description']).strip())
    if note.summary or note.text:
        snippet = (note.summary or note.text or '').strip()[:400]
        if snippet:
            description_parts.append(f"Из заметки #{note.id}:\n{snippet}")
    description = '\n\n'.join(description_parts) if description_parts else None

    start_iso = _ensure_rfc3339(None, fallback=start_dt)
    end_iso = _ensure_rfc3339(None, fallback=end_dt)

    try:
        event = calendar_update_timebox(
            credentials,
            event_id,
            start_iso,
            end_iso,
            description,
            time_zone=calendar_tz or getattr(user, 'timezone', None),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            'Calendar event update failed',
            extra={'user_id': user.id, 'error': str(exc), 'event_id': event_id},
        )
        return ToolResult(message='Не удалось перенести встречу. Попробуй ещё раз позже.')

    updated_meta = {'calendar_event_id': event.get('id') or event_id}
    start_info = event.get('start') or {}
    event_tz = start_info.get('timeZone')
    if not event_tz:
        dt_raw = start_info.get('dateTime')
        if dt_raw:
            try:
                dt = datetime.fromisoformat(dt_raw.replace('Z', '+00:00'))
                event_tz = _tz_label(dt.tzinfo)
            except Exception:  # noqa: BLE001
                event_tz = None
    if event_tz:
        updated_meta['calendar_timezone'] = event_tz
    elif calendar_tz:
        updated_meta['calendar_timezone'] = calendar_tz

    link = event.get('htmlLink') or meta.get('calendar_url')
    link_payload = {'calendar_url': link} if event.get('htmlLink') else None
    note_service.update_note_metadata(note, meta=updated_meta, links=link_payload)

    note_label = _note_preview(note)
    when_label = start_dt.strftime('%d.%m %H:%M')
    message = f"🗓 Перенёс встречу {note_label} на {when_label}." if note_label else f"🗓 Перенёс событие: {link or event_id}"
    return ToolResult(message=message, details={'event': event})


TOOLS: list[AgentTool] = [
    AgentTool(
        name="free_prompt",
        description="Обрабатывает активную заметку по пользовательскому запросу (свободный промпт).",
        args_schema={"prompt": "str", "note_id": "int|optional"},
        func=_tool_free_prompt,
        requires_note=True,
    ),
    AgentTool(
        name="save_note",
        description="Сохраняет активную заметку, обновляет саммари/теги и индекс.",
        args_schema={"note_id": "int|optional", "summary": "str|optional", "tags": "list[str]|optional", "status": "str|optional"},
        func=_tool_save_note,
        requires_note=True,
    ),
    AgentTool(
        name="update_note_text",
        description="Заменяет или дополняет текст заметки и переиндексирует её.",
        args_schema={"note_id": "int|optional", "text": "str|optional", "append": "str|optional", "status": "str|optional", "reindex": "bool|optional"},
        func=_tool_update_text,
        requires_note=True,
    ),
    AgentTool(
        name="create_task",
        description="Создаёт новую задачу на основе текста пользователя.",
        args_schema={"text": "str", "summary": "str|optional", "tags": "list[str]|optional", "status": "str|optional"},
        func=_tool_create_task,
    ),
    AgentTool(
        name="search_notes",
        description="Запускает семантический поиск по заметкам пользователя.",
        args_schema={"query": "str", "k": "int|optional"},
        func=_tool_search_notes,
    ),
    AgentTool(
        name="suggest_calendar_event",
        description="Создаёт рекомендацию встречи или события и сохраняет её в очереди событий.",
        args_schema={"note_id": "int|optional", "title": "str|optional", "when": "str|optional", "description": "str|optional"},
        func=_tool_suggest_calendar,
        requires_note=True,
    ),
    AgentTool(
        name="create_calendar_event",
        description="Создаёт событие в Google Calendar и привязывает его к заметке.",
        args_schema={
            "note_id": "int|optional",
            "title": "str|optional",
            "start": "str|optional",
            "end": "str|optional",
            "duration_minutes": "int|optional",
            "description": "str|optional",
        },
        func=_tool_create_calendar_event,
        requires_note=False,
    ),
    AgentTool(
        name="update_calendar_event",
        description="Переносит уже созданное событие Google Calendar.",
        args_schema={
            "note_id": "int|optional",
            "event_id": "str|optional",
            "start": "str",
            "end": "str|optional",
            "duration_minutes": "int|optional",
            "description": "str|optional",
        },
        func=_tool_update_calendar_event,
        requires_note=True,
    ),
]

TOOL_REGISTRY: dict[str, AgentTool] = {tool.name: tool for tool in TOOLS}


def get_tool_specs() -> list[dict[str, Any]]:
    """Return JSON-serialisable tool specs for the prompt."""

    specs: list[dict[str, Any]] = []
    for tool in TOOLS:
        specs.append(
            {
                "name": tool.name,
                "description": tool.description,
                "args_schema": tool.args_schema,
                "requires_note": tool.requires_note,
            }
        )
    return specs


def resolve_tool(name: str) -> Optional[AgentTool]:
    return TOOL_REGISTRY.get(name)
