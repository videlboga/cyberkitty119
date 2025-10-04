"""Background job to synchronize notes with Google Drive when initial upload fails."""

from __future__ import annotations

import json
from datetime import datetime

from telegram.ext import Application

from transkribator_modules.config import logger
from transkribator_modules.db.database import EventService, NoteService, SessionLocal
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.google_api import (
    GoogleCredentialService,
    ensure_tree_cached,
    upload_markdown,
    upsert_index,
)
from transkribator_modules.beta.content_processor import _front_matter, _ensure_signature, FOLDER_MAP
from transkribator_modules.transcribe.transcriber_v4 import _basic_local_format

EVENT_KIND = 'drive_sync_pending'
BATCH_SIZE = 5
SYNC_INTERVAL_SECONDS = 600


def _load_json(payload: str) -> dict:
    try:
        return json.loads(payload or '{}')
    except json.JSONDecodeError:
        return {}


def _prepare_markdown(type_hint: str, tags: list[str], rendered_output: str) -> tuple[str, str]:
    summary_line = (rendered_output or '').split('\n')[0][:280]
    front_matter = _front_matter(type_hint, tags, summary_line)
    return summary_line, front_matter + '\n' + rendered_output


def _sync_raw_note(note: Note, user, credentials, folders: dict, note_service: NoteService,
                   payload: dict) -> bool:
    raw_markdown = payload.get('raw_markdown') or _ensure_signature(note.text or '')
    inbox_id = folders.get('Inbox') or folders.get('user')
    if not inbox_id:
        return False

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"{timestamp}_{note.id}_raw.md"
    file = upload_markdown(credentials, inbox_id, filename, raw_markdown)

    note_service.update_note_metadata(
        note,
        summary=(note.summary or (note.text or '')[:140]),
        tags=None,
        drive_file_id=file.get('id'),
        status=note.status,
        links={'drive_url': file.get('webViewLink')},
    )

    sheet_id = folders.get('IndexSheet')
    if sheet_id:
        sheet_row = {
            'id': str(note.id),
            'date': datetime.utcnow().isoformat(),
            'type': note.type_hint or 'other',
            'title': filename,
            'tags': [],
            'drive_path': f"Inbox/{filename}",
            'drive_url': file.get('webViewLink'),
            'doc_url': '',
            'extra': 'raw',
        }
        upsert_index(credentials, sheet_id, sheet_row)
    return True


def _sync_processed_note(note: Note, user, credentials, folders: dict, note_service: NoteService,
                         payload: dict, tags: list[str]) -> bool:
    rendered_output = payload.get('rendered_output') or _basic_local_format(note.text or '')
    type_hint = payload.get('type_hint') or note.type_hint or 'other'
    summary_line, markdown = _prepare_markdown(type_hint, tags, rendered_output)

    folder_label = FOLDER_MAP.get(type_hint, 'Inbox')
    target_folder = folders.get(folder_label, folders.get('Inbox'))
    if not target_folder:
        return False

    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    preset_label = (payload.get('preset_id') or type_hint or 'note').replace('.', '_')
    filename = f"{timestamp}_{preset_label}.md"
    file = upload_markdown(credentials, target_folder, filename, markdown)

    links_payload = {'drive_url': file.get('webViewLink')}
    try:
        existing_links = json.loads(note.links or '{}') if note.links else {}
        if isinstance(existing_links, dict) and existing_links.get('raw_drive_url'):
            links_payload['raw_drive_url'] = existing_links['raw_drive_url']
    except Exception:  # pragma: no cover - защитный
        pass

    note_service.update_note_metadata(
        note,
        summary=summary_line,
        tags=tags,
        drive_file_id=file.get('id'),
        status=note.status,
        links=links_payload,
    )

    sheet_id = folders.get('IndexSheet')
    if sheet_id:
        sheet_row = {
            'id': str(note.id),
            'date': datetime.utcnow().isoformat(),
            'type': type_hint,
            'title': filename,
            'tags': tags,
            'drive_path': f"{folder_label}/{filename}",
            'drive_url': file.get('webViewLink'),
            'doc_url': '',
            'extra': payload.get('preset_id'),
        }
        upsert_index(credentials, sheet_id, sheet_row)
    return True


def _sync_event(session, event, payload: dict) -> bool:
    note_id = payload.get('note_id')
    if not note_id:
        return True

    note = session.query(Note).filter(Note.id == note_id).one_or_none()
    if not note:
        return True

    user = note.user
    cred_service = GoogleCredentialService(session)
    try:
        credentials = cred_service.get_credentials(user.id)
    except Exception as exc:
        logger.warning("Drive sync: credentials unavailable", extra={'user_id': user.id, 'error': str(exc)})
        return False

    if not credentials:
        return False

    try:
        folders = ensure_tree_cached(credentials, user.id, user.username or str(user.telegram_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Drive sync: ensure_tree failed", extra={'user_id': user.id, 'error': str(exc)})
        return False

    note_service = NoteService(session)
    tags = payload.get('tags') or []

    try:
        if payload.get('status') == NoteStatus.PROCESSED_RAW.value:
            return _sync_raw_note(note, user, credentials, folders, note_service, payload)
        return _sync_processed_note(note, user, credentials, folders, note_service, payload, tags)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Drive sync: upload failed",
            extra={'error': str(exc), 'user_id': user.id, 'note_id': note.id},
        )
        return False


async def process_drive_sync(application: Application) -> None:
    session = SessionLocal()
    try:
        event_service = EventService(session)

        events = event_service.list_events(EVENT_KIND, limit=BATCH_SIZE)
        if not events:
            return

        for event in events:
            payload = _load_json(event.payload)
            note_id = payload.get('note_id')
            if not note_id:
                event_service.delete_event(event)
                continue

            note = session.query(Note).filter(Note.id == note_id).one_or_none()
            if not note:
                event_service.delete_event(event)
                continue

            success = _sync_event(session, event, payload)
            if success:
                event_service.delete_event(event)
    finally:
        session.close()


def schedule_drive_sync_jobs(application: Application) -> None:
    async def _job_callback(context):
        await process_drive_sync(application)

    application.job_queue.run_repeating(
        _job_callback,
        interval=SYNC_INTERVAL_SECONDS,
        first=120,
        name="beta_drive_sync",
    )
