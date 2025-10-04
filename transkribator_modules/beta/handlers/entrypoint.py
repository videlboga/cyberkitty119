"""Entry point for the updated beta agent flow."""

from __future__ import annotations

import datetime
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.config import logger
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.google_api import GoogleCredentialService, ensure_tree, upload_markdown

from ..agent_runtime import AGENT_MANAGER


@dataclass
class _NoteSnapshot:
    note: Note
    created: bool
    drive_link: Optional[str] = None
    local_file: Optional[str] = None


async def process_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    source: str = "message",
    *,
    existing_note: Optional[Note] = None,
    force_mode: Optional[str] = None,
) -> None:
    """Process incoming text with the conversational agent."""

    user = update.effective_user
    if not user:
        return

    if not text or not text.strip():
        await _respond(update, context, "Не нашёл текста в сообщении. Попробуй ещё раз.")
        return

    session = AGENT_MANAGER.get_session(user)
    beta_state = context.user_data.setdefault("beta", {})
    snapshot: Optional[_NoteSnapshot] = None

    ingest_context = source in {"audio", "video", "voice", "media", "backlog"}
    ingest_context = ingest_context or force_mode == "content"
    active_note_id = beta_state.get("active_note_id")

    if ingest_context or not active_note_id:
        snapshot = _create_or_update_note(user, text, source, existing_note)
        session.set_active_note(snapshot.note, local_artifact=bool(snapshot.local_file))
        beta_state["active_note_id"] = snapshot.note.id
        beta_state["source"] = source
        payload = {
            "note_id": snapshot.note.id,
            "text": text,
            "summary": snapshot.note.summary,
            "source": source,
            "created_at": snapshot.note.ts.isoformat() if snapshot.note.ts else datetime.datetime.utcnow().isoformat(),
            "created": snapshot.created,
        }
        response = await session.handle_ingest(payload)
    else:
        response = await session.handle_user_message(text)

    if snapshot:
        final_text = _merge_artifact_hint(response.text, snapshot)
    else:
        final_text = response.text

    if final_text:
        await _respond(update, context, final_text)

    if snapshot and snapshot.local_file:
        await _send_local_artifact(update, context, snapshot.local_file, snapshot.note.id)


async def handle_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    text = message.text or message.caption
    if not text:
        return

    await process_text(update, context, text, source="message")


def _create_or_update_note(telegram_user, text: str, source: str, existing_note: Optional[Note]) -> _NoteSnapshot:
    db = SessionLocal()
    try:
        user_service = UserService(db)
        note_service = NoteService(db)
        google_service = GoogleCredentialService(db)

        user = user_service.get_or_create_user(
            telegram_id=telegram_user.id,
            username=getattr(telegram_user, "username", None),
            first_name=getattr(telegram_user, "first_name", None),
            last_name=getattr(telegram_user, "last_name", None),
        )

        created = False
        drive_link: Optional[str] = None
        local_file: Optional[str] = None
        if existing_note is not None:
            note = note_service.get_note(existing_note.id)
            if note and note.user_id == user.id:
                note.text = text
                note.status = NoteStatus.DRAFT.value
                note.updated_at = datetime.datetime.utcnow()
                db.commit()
                db.refresh(note)
            else:
                note = note_service.create_note(
                    user=user,
                    text=text,
                    source=source,
                    status=NoteStatus.INGESTED.value,
                )
                created = True
        else:
            note = note_service.create_note(
                user=user,
                text=text,
                source=source,
                status=NoteStatus.INGESTED.value,
            )
            created = True

        if created:
            drive_link, local_file = _ensure_note_artifact(
                google_service,
                note_service,
                user,
                note,
                text,
            )
    finally:
        db.close()

    return _NoteSnapshot(note=note, created=created, drive_link=drive_link, local_file=local_file)


async def _respond(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if update.message:
        await update.message.reply_text(text)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text)
    else:
        user = update.effective_user
        if user:
            await context.bot.send_message(chat_id=user.id, text=text)


def _ensure_note_artifact(
    google_service: GoogleCredentialService,
    note_service: NoteService,
    user,
    note: Note,
    text: str,
) -> tuple[Optional[str], Optional[str]]:
    drive_link = _upload_note_to_drive(google_service, note_service, user, note, text)
    if drive_link:
        return drive_link, None
    local_file = _export_note_locally(note, text)
    return None, local_file


def _upload_note_to_drive(
    google_service: GoogleCredentialService,
    note_service: NoteService,
    user,
    note: Note,
    text: str,
) -> Optional[str]:
    try:
        credentials = google_service.get_credentials(user.id)
    except RuntimeError:
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google credentials fetch failed", extra={"user_id": user.id, "error": str(exc)})
        return None

    if not credentials:
        return None

    try:
        tree = ensure_tree(credentials, user.username or str(user.telegram_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_tree failed", extra={"user_id": user.id, "error": str(exc)})
        return None

    target_folder = (
        tree.get('Inbox')
        or tree.get('Notes')
        or next((tree[val] for val in ('Meetings', 'Ideas', 'Tasks') if val in tree), None)
    )
    if not target_folder:
        return None

    markdown = text.strip()
    if not markdown:
        markdown = "(пустая заметка)"

    filename = f"note_{note.id}_{datetime.datetime.utcnow():%Y%m%d_%H%M%S}.md"
    try:
        file = upload_markdown(credentials, target_folder, filename, markdown)
    except Exception as exc:  # noqa: BLE001
        logger.warning("upload_markdown failed", extra={"user_id": user.id, "error": str(exc)})
        return None

    link = (file or {}).get('webViewLink')
    if link:
        note_service.update_note_metadata(
            note,
            links={'drive_url': link},
            drive_file_id=(file or {}).get('id'),
        )
        return link
    return None


def _export_note_locally(note: Note, text: str) -> Optional[str]:
    content = (text or '').strip()
    if not content:
        return None

    try:
        fd, path = tempfile.mkstemp(prefix=f"note_{note.id}_", suffix=".md")
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create local artifact", extra={"note_id": note.id, "error": str(exc)})
        return None


def _merge_artifact_hint(base_text: Optional[str], snapshot: _NoteSnapshot) -> str:
    parts: list[str] = []
    if base_text and base_text.strip():
        parts.append(base_text.strip())
    if snapshot.drive_link and (not base_text or snapshot.drive_link not in base_text):
        parts.append(f"Drive: {snapshot.drive_link}")
    if snapshot.local_file and (not base_text or 'файл' not in base_text.lower()):
        parts.append("📎 Файл заметки прикрепил отдельным сообщением.")
    return "\n\n".join(parts).strip()


async def _send_local_artifact(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, note_id: int) -> None:
    caption = f"Заметка #{note_id}."
    filename = Path(file_path).name
    try:
        if update.message:
            with open(file_path, 'rb') as handle:
                await update.message.reply_document(handle, filename=filename, caption=caption)
        elif update.callback_query and update.callback_query.message:
            with open(file_path, 'rb') as handle:
                await update.callback_query.message.reply_document(handle, filename=filename, caption=caption)
        else:
            user = update.effective_user
            if user:
                with open(file_path, 'rb') as handle:
                    await context.bot.send_document(chat_id=user.id, document=handle, filename=filename, caption=caption)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send local artifact", extra={"note_id": note_id, "error": str(exc)})
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception as clear_exc:  # noqa: BLE001
            logger.debug("Failed to remove temp artifact", extra={"path": file_path, "error": str(clear_exc)})
