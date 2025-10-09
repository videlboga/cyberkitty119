"""Command execution pipeline for beta-mode commands."""

from __future__ import annotations

import datetime
import json
from datetime import timedelta, timezone
from collections import defaultdict, OrderedDict

from transkribator_modules.config import logger, FEATURE_GOOGLE_CALENDAR
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.search import IndexService
from transkribator_modules.google_api import (
    GoogleCredentialService,
    ensure_tree,
    upload_markdown,
    upsert_index,
    create_doc,
    calendar_read_changes,
    calendar_create_timebox,
    move_file,
)
from transkribator_modules.transcribe.transcriber_v4 import _basic_local_format
from .content_processor import ContentProcessor
from .presets import get_default_preset_for_action, get_free_prompt
from .timezone import timezone_required_message

_index = IndexService()
_content_processor = ContentProcessor()

FOLDER_MAP = {
    'meeting': 'Meetings',
    'idea': 'Ideas',
    'task': 'Tasks',
    'media': 'Resources',
    'recipe': 'Resources',
    'journal': 'Journal',
}
DEFAULT_FOLDER = 'Inbox'


def _render_note(note: Note | dict) -> str:
    if isinstance(note, dict):
        tags = ', '.join(note.get('tags') or [])
        links = note.get('links') or {}
        ts = note.get('ts')
        if isinstance(ts, str):
            ts_display = ts.replace('T', ' ')[:16]
        elif ts:
            ts_display = ts
        else:
            ts_display = '—'
        base = note.get('summary') or (note.get('text') or '')[:120]
        note_type = note.get('type_hint') or 'other'
    else:
        tags = ', '.join(json.loads(note.tags or '[]'))
        links = _load_links(note)
        ts_display = f"{note.ts:%Y-%m-%d %H:%M}" if note.ts else '—'
        base = note.summary or (note.text or '')[:120]
        note_type = note.type_hint or 'other'

    link_parts = []
    if links.get('drive_url'):
        link_parts.append(f"[Drive]({links['drive_url']})")
    if links.get('doc_url'):
        link_parts.append(f"[Doc]({links['doc_url']})")
    if links.get('transcript_doc'):
        link_parts.append(f"[Transcript]({links['transcript_doc']})")
    link_text = ' '.join(link_parts)
    line = f"• {ts_display} [{note_type}] {base}"
    if tags:
        line += f" (tags: {tags})"
    if link_text:
        line += f" {link_text}"
    return line


def _load_tags(note: Note) -> list[str]:
    try:
        result = json.loads(note.tags or '[]')
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def _load_links(note: Note) -> dict:
    try:
        data = json.loads(note.links or '{}')
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _folder_label(note_type: str | None) -> str:
    return FOLDER_MAP.get((note_type or 'other'), DEFAULT_FOLDER)


def _compose_markdown(note_type: str, tags: list[str], summary: str) -> str:
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    tags_fmt = '[' + ', '.join(tags) + ']' if tags else '[]'
    summary_line = (summary or '').split('\n')[0].replace('"', '\"')
    front_matter = (
        f"---\ncreated: {now}\ntype: {note_type}\ntags: {tags_fmt}\nsummary: \"{summary_line}\"\n---\n"
    )
    return front_matter + '\n' + summary


def _build_sheet_row(note: Note, tags: list[str], folder_label: str, *, drive_url: str = '', doc_url: str = '', extra: str = '') -> dict:
    title_source = (note.summary or note.text or '').strip()
    if not title_source:
        title_source = f"Note {note.id}"
    title_line = title_source.split('\n')[0].strip()
    if len(title_line) > 120:
        title_line = title_line[:117] + '…'
    return {
        'id': str(note.id),
        'date': (note.ts or datetime.datetime.utcnow()).isoformat(),
        'type': note.type_hint or 'other',
        'title': title_line,
        'tags': tags,
        'drive_path': f"{folder_label}/{title_line}",
        'drive_url': drive_url,
        'doc_url': doc_url,
        'extra': extra,
    }


def _split_doc_blocks(summary: str) -> list[str]:
    parts = [part.strip() for part in (summary or '').split('\n\n')]
    return [part for part in parts if part]


def _format_generation_response(action: str, result: dict) -> str:
    note_id = result.get('note_id')
    drive_info = result.get('drive') or {}
    raw_info = result.get('raw_drive') or {}
    snippet = (result.get('rendered_output') or '').strip()
    if len(snippet) > 3500:
        snippet = snippet[:3497] + '…'

    lines = [f"🛠 Действие `{action}` выполнено."]
    if note_id:
        lines.append(f"Создана заметка #{note_id}.")
    if drive_info.get('webViewLink'):
        lines.append(f"Drive: {drive_info['webViewLink']}")
    if raw_info.get('webViewLink') and raw_info.get('webViewLink') != drive_info.get('webViewLink'):
        lines.append(f"Raw: {raw_info['webViewLink']}")
    if result.get('sync_queued'):
        lines.append('☁️ Загрузка в Google Drive повторится в фоне.')
    if snippet:
        if lines:
            lines.append('')
        lines.append(snippet)
    return "\n".join(lines).strip()


def _reindex_note(note: Note) -> None:
    tags = _load_tags(note)
    links = _load_links(note)
    _index.add(
        note.id,
        note.user_id,
        note.text or '',
        summary=note.summary or '',
        type_hint=note.type_hint or 'other',
        tags=tags,
        links=links,
    )


def _ensure_google_context(session, user, action: str, require_tree: bool = True):
    service = GoogleCredentialService(session)
    try:
        credentials = service.get_credentials(user.id)
    except RuntimeError:
        return None, None, 'Нужно подключить Google Drive в личном кабинете.'
    except Exception as exc:
        logger.error('Не удалось получить Google креды', extra={'user_id': user.id, 'error': str(exc)})
        return None, None, 'Google Drive временно недоступен. Попробуй позже.'

    if not credentials:
        return None, None, 'Сначала подключи Google Drive в личном кабинете.'

    tree = None
    if require_tree:
        try:
            tree = ensure_tree(credentials, user.username or str(user.telegram_id))
        except Exception as exc:
            logger.error('ensure_tree failed', extra={'user_id': user.id, 'error': str(exc), 'action': action})
            return None, None, 'Не удалось открыть папки Google Drive. Попробуй позже.'

    return credentials, tree, None


def _safe_upsert(credentials, sheet_id: str | None, row: dict) -> None:
    if not credentials or not sheet_id:
        return
    try:
        upsert_index(credentials, sheet_id, row)
    except Exception as exc:
        logger.warning('Не удалось обновить Google Sheet', extra={'error': str(exc), 'row': row})


async def execute_command(tg_user, command_payload: dict) -> str:
    command = command_payload.get('command', {}) if command_payload else {}
    intent = command.get('intent') or 'help'
    args = command.get('args') or {}

    with SessionLocal() as session:
        user_service = UserService(session)
        db_user = user_service.get_or_create_user(
            telegram_id=tg_user.id,
            username=getattr(tg_user, 'username', None),
            first_name=getattr(tg_user, 'first_name', None),
            last_name=getattr(tg_user, 'last_name', None),
        )
        if intent == 'qa':
            return _handle_qa(session, db_user.id, args)
        if intent == 'filter':
            return _handle_filter(session, db_user.id, args)
        if intent == 'digest':
            return _handle_digest(session, db_user.id, args)
        if intent == 'action':
            return await _handle_action(session, db_user, args)
        if intent == 'calendar':
            return await _handle_calendar(session, db_user, args)
        if intent == 'help':
            return (
                "Могу сохранить заметку, открыть меню пресетов или помочь с поиском."
                " Напиши что хочешь сделать, и я подскажу команды."
            )
        return "Командный режим ещё обучается. Попробуй позже или переформулируй запрос."


def _handle_qa(session, user_id: int, args: dict) -> str:
    query = args.get('query') or ''
    if not query:
        return "Нужен конкретный вопрос для поиска."

    matches = _index.search(user_id, query, k=args.get('k', 5))
    if not matches:
        return "Ничего не нашёл в заметках."

    grouped: OrderedDict[int, dict] = OrderedDict()
    for match in matches:
        note_id = match['note_id']
        entry = grouped.setdefault(
            note_id,
            {'note': match['note'], 'chunks': [], 'score': match.get('score', 0.0)},
        )
        entry['chunks'].append(match['chunk'])
        entry['score'] = min(entry['score'], match.get('score', entry['score']))

    lines = ["🔍 Нашёл следующее:"]
    for entry in grouped.values():
        lines.append(_render_note(entry['note']))
        for chunk in entry['chunks']:
            snippet = chunk.strip()
            if len(snippet) > 220:
                snippet = snippet[:217] + '…'
            lines.append(f"  └ {snippet}")
    return "\n".join(lines)


def _handle_filter(session, user_id: int, args: dict) -> str:
    query = session.query(Note).filter(Note.user_id == user_id)
    if args.get('type') and args['type'] != 'any':
        query = query.filter(Note.type_hint == args['type'])
    tags = args.get('tags') or []
    if tags:
        for tag in tags:
            query = query.filter(Note.tags.contains(tag))
    time_range = args.get('time_range') or {}
    if time_range.get('from'):
        query = query.filter(Note.ts >= datetime.datetime.fromisoformat(time_range['from']))
    if time_range.get('to'):
        query = query.filter(Note.ts <= datetime.datetime.fromisoformat(time_range['to']))

    notes = query.order_by(Note.ts.desc()).limit(args.get('k', 8)).all()
    if not notes:
        return "Под подходящий фильтр заметок не нашлось."
    lines = ["📂 Подходящие заметки:"]
    lines.extend(_render_note(note) for note in notes)
    return "\n".join(lines)


def _handle_digest(session, user_id: int, args: dict) -> str:
    time_range = args.get('time_range') or {}
    if not time_range.get('from') or not time_range.get('to'):
        return "Для дайджеста нужны даты начала и конца периода."
    start = datetime.datetime.fromisoformat(time_range['from'])
    end = datetime.datetime.fromisoformat(time_range['to'])
    notes = (
        session.query(Note)
        .filter(Note.user_id == user_id, Note.ts >= start, Note.ts <= end)
        .order_by(Note.ts.asc())
        .all()
    )
    if not notes:
        return "За выбранный период заметок не нашлось."
    grouped = defaultdict(list)
    for note in notes:
        grouped[note.type_hint or 'other'].append(note)
    lines = [f"🗓 Дайджест {start:%Y-%m-%d} – {end:%Y-%m-%d}:"]
    for type_hint, group in grouped.items():
        lines.append(f"\n**{type_hint.upper()}**")
        for note in group:
            lines.append(_render_note(note))
    return "\n".join(lines)


async def _handle_action(session, user, args: dict) -> str:
    note_id = args.get('note_id')
    action = args.get('action')
    if not note_id or not action:
        return "Для действия нужна конкретная заметка и тип действия."

    note_service = NoteService(session)
    note = session.query(Note).filter(Note.user_id == user.id, Note.id == note_id).one_or_none()
    if not note:
        return "Не нашёл такую заметку."

    action = action.lower()
    tags = _load_tags(note)
    summary_text = note.summary or _basic_local_format(note.text or '')
    folder_label = _folder_label(note.type_hint)
    preset_id = args.get('preset_id')

    generation_actions = {
        'summary',
        'protocol',
        'bullets',
        'tasks_split',
        'post',
        'quotes',
        'timed_outline',
        'task_from_note',
    }

    if action in generation_actions:
        type_hint_override = note.type_hint or 'other'
        generation_tags = tags
        if action == 'task_from_note':
            type_hint_override = 'task'
            generation_tags = sorted(set(list(tags) + ['task']))

        preset = get_default_preset_for_action(action, type_hint_override, preferred_id=preset_id)
        if not preset:
            return "Не нашёл подходящий пресет для этого действия."

        try:
            result = await _content_processor.process(
                user,
                note.text,
                type_hint_override,
                preset,
                NoteStatus.PROCESSED.value,
                tags=generation_tags,
                type_confidence=note.type_confidence,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                'Preset action failed',
                extra={'note_id': note.id, 'action': action, 'error': str(exc)},
            )
            return "Не удалось выполнить действие. Попробуй позже."

        response = _format_generation_response(action, result)
        if action == 'task_from_note' and args.get('task_due'):
            response += f"\n📅 Дедлайн: {args['task_due']}"
        return response

    if action == 'free_prompt':
        prompt = (args.get('prompt') or '').strip()
        if not prompt:
            return "Нужно указать текст промпта."
        preset = get_free_prompt()
        if not preset:
            return "Свободный промпт сейчас недоступен."
        try:
            result = await _content_processor.process(
                user,
                note.text,
                note.type_hint or 'other',
                preset,
                NoteStatus.PROCESSED.value,
                custom_prompt=prompt,
                tags=tags,
                type_confidence=note.type_confidence,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error('Free prompt action failed', extra={'note_id': note.id, 'error': str(exc)})
            return "Не удалось выполнить свободный промпт. Попробуй позже."
        return _format_generation_response(action, result)

    if action == 'move':
        target_type = (args.get('target_type') or '').strip().lower()
        if target_type == 'any':
            target_type = 'other'
        target_status = args.get('target_status')

        if not target_type and not target_status:
            return "Укажи новый тип или статус, чтобы переместить заметку."

        changed = False
        if target_type and target_type != (note.type_hint or ''):
            note.type_hint = target_type
            note.type_confidence = max(note.type_confidence or 0.0, 0.95)
            changed = True
        if target_status and target_status != note.status:
            note.status = target_status
            changed = True

        if not changed:
            return "Тип и статус не изменились — перемещать нечего."

        note.updated_at = datetime.datetime.utcnow()
        session.commit()
        session.refresh(note)

        move_messages: list[str] = []
        credentials, tree, error = _ensure_google_context(session, user, action)
        links = _load_links(note)
        if error:
            move_messages.append(error)
            credentials = None
            tree = None

        if credentials and tree and note.drive_file_id:
            target_folder_id = tree.get(_folder_label(note.type_hint), tree.get(DEFAULT_FOLDER))
            if target_folder_id:
                try:
                    file = move_file(credentials, note.drive_file_id, target_folder_id)
                    if file.get('webViewLink'):
                        note_service.update_note_metadata(note, links={'drive_url': file.get('webViewLink')})
                        links = _load_links(note)
                        move_messages.append(f"Файл перемещён в {_folder_label(note.type_hint)}.")
                except Exception as exc:  # noqa: BLE001
                    logger.warning('Не удалось переместить файл в Drive', extra={'note_id': note.id, 'error': str(exc)})
                    move_messages.append('Не удалось переместить файл в Google Drive, попробуй вручную.')

        sheet_id = tree.get('IndexSheet') if tree else None
        if credentials and sheet_id:
            _safe_upsert(
                credentials,
                sheet_id,
                _build_sheet_row(
                    note,
                    _load_tags(note),
                    _folder_label(note.type_hint),
                    drive_url=links.get('drive_url', ''),
                    doc_url=links.get('doc_url', ''),
                    extra='move',
                ),
            )

        _reindex_note(note)

        status_names = {
            NoteStatus.PROCESSED.value: 'processed',
            NoteStatus.BACKLOG.value: 'backlog',
            NoteStatus.PROCESSED_RAW.value: 'raw',
        }
        lines = [
            "🗂 Заметка обновлена.",
            f"Тип: {note.type_hint or 'other'}",
            f"Статус: {status_names.get(note.status, note.status)}",
        ]
        lines.extend(move_messages)
        if credentials is None and not move_messages:
            lines.append('Google Drive недоступен, файл нужно переместить вручную.')
        lines.append('Индекс обновлён.')
        return "\n".join(line for line in lines if line)

    if action == 'retag':
        new_tags = args.get('new_tags')
        remove_tags = args.get('remove_tags') or []
        if new_tags is None and not remove_tags:
            return "Укажи новые теги или какие удалить."

        current_tags = _load_tags(note)
        if new_tags is not None:
            target_tags = new_tags
        else:
            target_tags = [tag for tag in current_tags if tag not in remove_tags]

        note = note_service.update_note_metadata(note, tags=target_tags)
        links = _load_links(note)

        credentials, tree, error = _ensure_google_context(session, user, action)
        warnings: list[str] = []
        if error:
            warnings.append(error)
            credentials = None
            tree = None

        if credentials and tree:
            sheet_id = tree.get('IndexSheet')
            _safe_upsert(
                credentials,
                sheet_id,
                _build_sheet_row(
                    note,
                    target_tags,
                    _folder_label(note.type_hint),
                    drive_url=links.get('drive_url', ''),
                    doc_url=links.get('doc_url', ''),
                    extra='retag',
                ),
            )

        _reindex_note(note)

        tags_label = ', '.join(target_tags) if target_tags else 'тегов нет'
        lines = [f"🏷 Теги обновлены: {tags_label}", 'Индекс обновлён.']
        lines.extend(warnings)
        return "\n".join(lines)

    credentials, tree, error = _ensure_google_context(session, user, action)
    if error:
        return error

    sheet_id = tree.get('IndexSheet') if tree else None
    target_folder_id = tree.get(folder_label, tree.get(DEFAULT_FOLDER)) if tree else None

    if action == 'save_drive':
        if not target_folder_id:
            return "Не удалось определить папку в Google Drive."
        markdown = _compose_markdown(note.type_hint or 'other', tags, summary_text)
        filename = f"{datetime.datetime.utcnow():%Y%m%d_%H%M%S}_{note.type_hint or 'note'}.md"
        try:
            file = upload_markdown(credentials, target_folder_id, filename, markdown)
        except Exception as exc:  # noqa: BLE001
            logger.error('Не удалось сохранить заметку в Drive', extra={'error': str(exc)})
            return "Не получилось сохранить файл в Google Drive. Попробуй позже."

        note = note_service.update_note_metadata(
            note,
            summary=summary_text,
            tags=tags,
            drive_file_id=file.get('id'),
            links={'drive_url': file.get('webViewLink')},
        )
        _safe_upsert(
            credentials,
            sheet_id,
            _build_sheet_row(
                note,
                tags,
                folder_label,
                drive_url=file.get('webViewLink'),
                doc_url=_load_links(note).get('doc_url', ''),
                extra='save_drive',
            ),
        )
        return f"📂 Файл сохранён в Google Drive: {file.get('webViewLink')}"

    if action == 'create_doc':
        if not target_folder_id:
            return "Не удалось определить папку в Google Drive."
        title = f"{note.type_hint or 'note'} {datetime.datetime.utcnow():%Y-%m-%d %H:%M}".strip()
        blocks = _split_doc_blocks(summary_text)
        if not blocks:
            blocks = [summary_text]
        try:
            doc = create_doc(credentials, target_folder_id, title, blocks)
        except Exception as exc:  # noqa: BLE001
            logger.error('Не удалось создать Google Doc', extra={'error': str(exc)})
            return "Google Docs временно недоступен. Попробуй позже."

        note = note_service.update_note_metadata(
            note,
            links={'doc_url': doc.get('link')},
        )
        links = _load_links(note)
        _safe_upsert(
            credentials,
            sheet_id,
            _build_sheet_row(
                note,
                tags,
                folder_label,
                drive_url=links.get('drive_url', ''),
                doc_url=doc.get('link'),
                extra='create_doc',
            ),
        )
        return f"📄 Документ создан: {doc.get('link')}"

    if action == 'update_index':
        links = _load_links(note)
        _safe_upsert(
            credentials,
            sheet_id,
            _build_sheet_row(
                note,
                tags,
                folder_label,
                drive_url=links.get('drive_url', ''),
                doc_url=links.get('doc_url', ''),
                extra='update_index',
            ),
        )
        return "🗂 Индекс Google Sheets обновлён."

    return "Это действие пока не поддерживается."


def _ensure_rfc3339_from_string(value: str | None, fallback: datetime.datetime | None = None) -> str:
    if value:
        raw = value.strip()
        iso_candidate = raw.replace(' ', 'T')
        if len(iso_candidate) == 10:
            iso_candidate += 'T00:00:00'
        if iso_candidate.endswith('Z'):
            fixed = iso_candidate
        elif iso_candidate.endswith('+00:00'):
            fixed = iso_candidate
        else:
            fixed = iso_candidate + 'Z'
        try:
            dt = datetime.datetime.fromisoformat(fixed.replace('Z', '+00:00'))
        except ValueError:
            dt = datetime.datetime.utcnow()
        return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    if not fallback:
        fallback = datetime.datetime.utcnow()
    return fallback.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _parse_manual_datetime(value: str) -> datetime.datetime:
    candidate = value.strip().replace(' ', 'T')
    if len(candidate) == 10:
        candidate += 'T00:00:00'
    elif len(candidate) == 16:
        candidate += ':00'
    dt = datetime.datetime.fromisoformat(candidate)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _rfc3339(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace('+00:00', 'Z')


def _format_event_time(payload: dict) -> str:
    value = payload.get('dateTime') or payload.get('date')
    if not value:
        return 'без времени'
    iso = value.replace('Z', '+00:00') if value.endswith('Z') else value
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return value
    if payload.get('date') and 'T' not in value:
        return f"{dt:%Y-%m-%d}"
    return f"{dt:%Y-%m-%d %H:%M}"


async def _handle_calendar(session, user, args: dict) -> str:
    if not FEATURE_GOOGLE_CALENDAR:
        return "Интеграция с календарём выключена."

    tz_message = timezone_required_message(user)
    if tz_message:
        return tz_message

    mode = (args.get('mode') or 'changes').lower()
    credentials, _, error = _ensure_google_context(session, user, 'calendar', require_tree=False)
    if error:
        return error
    if not credentials:
        return "Сначала подключи Google Calendar в личном кабинете."

    if mode == 'changes':
        now = datetime.datetime.utcnow()
        start_iso = _ensure_rfc3339_from_string(args.get('time_from'), now)
        end_default = now + datetime.timedelta(days=1)
        end_iso = _ensure_rfc3339_from_string(args.get('time_to'), end_default)
        if end_iso <= start_iso:
            end_iso = _rfc3339(datetime.datetime.utcnow() + datetime.timedelta(days=1))
        max_results = args.get('k') or 10
        try:
            events = calendar_read_changes(credentials, start_iso, end_iso, max_results=max_results)
        except Exception:
            return "Не удалось получить события из календаря. Попробуй позже."
        if not events:
            return "В календаре нет событий на выбранный период."
        lines = ["🗓 События в календаре:"]
        for event in events:
            start_label = _format_event_time(event.get('start', {}))
            end_label = _format_event_time(event.get('end', {}))
            summary = event.get('summary') or 'Без названия'
            link = event.get('htmlLink')
            location = event.get('location')
            line = f"- {start_label} → {end_label}: {summary}"
            if location:
                line += f" ({location})"
            if link:
                line += f"\n  {link}"
            lines.append(line)
        return "\n".join(lines)

    if mode == 'timebox':
        title = (args.get('title') or 'Timebox').strip()
        start_at = args.get('start_at')
        if not start_at:
            return "Нужно указать дату и время начала таймбокса."
        try:
            start_dt = datetime.datetime.fromisoformat(start_at.replace('Z', '+00:00'))
        except ValueError:
            try:
                start_dt = _parse_manual_datetime(start_at)
            except ValueError:
                return "Используй формат даты и времени ГГГГ-ММ-ДД HH:MM."
        duration = args.get('duration_minutes') or 60
        try:
            duration = int(duration)
            if duration <= 0:
                raise ValueError
        except ValueError:
            return "Длительность должна быть положительным числом."
        end_dt = start_dt + datetime.timedelta(minutes=duration)
        description = (args.get('description') or '').strip()
        note_id = args.get('note_id')
        if note_id:
            note = session.query(Note).filter(Note.user_id == user.id, Note.id == note_id).one_or_none()
            if note:
                snippet = (note.summary or note.text or '').strip()
                if snippet:
                    if description:
                        description += "\n\n"
                    description += f"Из заметки #{note.id}:\n{snippet[:400]}"
        try:
            event = calendar_create_timebox(
                credentials,
                title,
                _rfc3339(start_dt),
                _rfc3339(end_dt),
                description,
            )
        except Exception:
            return "Не удалось создать событие в календаре. Попробуй позже."

        link = event.get('htmlLink')
        if note_id and link:
            note = session.query(Note).filter(Note.user_id == user.id, Note.id == note_id).one_or_none()
            if note:
                note_service = NoteService(session)
                note_service.update_note_metadata(note, links={'calendar_url': link})
        return f"🗓 Таймбокс создан: {link or title}"

    return "Неизвестный режим календаря. Доступны changes или timebox."
