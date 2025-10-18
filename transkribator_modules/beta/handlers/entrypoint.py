"""Entry point for the updated beta agent flow."""

from __future__ import annotations

import datetime
import io
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    MINIAPP_NOTE_LINK_TEMPLATE,
    MINIAPP_PROXY_QUERY_PARAM,
    MINIAPP_PROXY_URL,
    logger,
)
from transkribator_modules.db.database import SessionLocal, UserService, NoteService
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.google_api import GoogleCredentialService, ensure_tree, upload_docx
from docx import Document

from ..agent_runtime import AGENT_MANAGER
from ..note_utils import auto_finalize_note
from ..tools import _ensure_google_credentials, _looks_like_question, _build_miniapp_note_link as _tools_build_note_link


COMMAND_PREFIXES = (
    'создай',
    'создать',
    'перенеси',
    'перенести',
    'сделай',
    'покажи',
    'напомни',
    'скажи',
    'удали',
    'оформи',
    'открой',
    'загрузи',
    'обнови',
)


TELEGRAM_MESSAGE_LIMIT = 3900


@dataclass
class _NoteSnapshot:
    note: Note
    created: bool
    drive_link: Optional[str] = None
    local_file: Optional[str] = None


class _ProgressMessage:
    """Helper that maintains a single Telegram message for progress updates."""

    def __init__(self, message, initial_text: str):
        self._message = message
        self._last_text = initial_text
        self._had_error = False

    async def update(
        self,
        text: str,
        *,
        mark_error: bool = False,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True,
    ) -> None:
        if not self._message or not text:
            return
        if mark_error:
            self._had_error = True
        if text == self._last_text:
            return
        try:
            await self._message.edit_text(
                text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_preview,
            )
            self._last_text = text
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to edit progress message", extra={"error": str(exc)})

    async def finalize(
        self,
        text: str,
        *,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True,
    ) -> None:
        if self._had_error:
            return
        await self.update(text, parse_mode=parse_mode, disable_preview=disable_preview)


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
    question = _looks_like_question(text)

    ingest_context = source in {"audio", "video", "voice", "media", "backlog"}
    ingest_context = ingest_context or force_mode == "content"
    active_note_id = beta_state.get("active_note_id")

    progress = await _start_progress_message(update, context, "🤖 Обрабатываю запрос…")

    try:
        create_artifacts = ingest_context or (not active_note_id and _should_create_artifact(text))

        if ingest_context or (not active_note_id and not question):
            if progress:
                await progress.update("📥 Подготавливаю заметку…")
            snapshot = _create_or_update_note(
                user,
                text,
                source,
                existing_note,
                create_artifacts=create_artifacts,
            )
            if snapshot.note and (snapshot.created or not (snapshot.note.summary and snapshot.note.summary.strip())):
                updated_note = await auto_finalize_note(snapshot.note.id)
                if updated_note:
                    snapshot.note = updated_note
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
            if progress:
                await progress.update(f"🗂 Заметка #{snapshot.note.id} подготовлена. Думаю над ответом…")
            response = await session.handle_ingest(payload, progress=progress)
        else:
            if progress:
                if active_note_id:
                    await progress.update(f"🧠 Работаю с заметкой #{active_note_id}…")
                else:
                    await progress.update("🔍 Ищу ответ в заметках…")
            response = await session.handle_user_message(text, progress=progress)

        cleaned_response = _dedupe_response_text(response.text)

        if snapshot:
            final_text = _merge_artifact_hint(cleaned_response, snapshot)
        else:
            final_text = cleaned_response

        sent_separately = False
        if final_text:
            rendered, parse_mode = _prepare_telegram_message(final_text)
            if progress and len(rendered) <= TELEGRAM_MESSAGE_LIMIT:
                await progress.finalize(rendered, parse_mode=parse_mode)
            else:
                if progress:
                    await progress.update("📄 Ответ отправлю отдельным сообщением…")
                await _respond(update, context, final_text)
                sent_separately = True

        if snapshot and snapshot.local_file:
            await _send_local_artifact(update, context, snapshot.local_file, snapshot.note.id)

        if progress and not sent_separately and not final_text:
            await progress.finalize("✅ Готово.")
        elif progress and sent_separately:
            await progress.finalize("✅ Ответ отправил.")
    except Exception:
        if progress:
            await progress.update("⚠️ Не удалось обработать запрос.", mark_error=True)
        raise


async def handle_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message:
        return
    text = message.text or message.caption
    if not text:
        return

    await process_text(update, context, text, source="message")


def _create_or_update_note(
    telegram_user,
    text: str,
    source: str,
    existing_note: Optional[Note],
    *,
    create_artifacts: bool,
) -> _NoteSnapshot:
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

        if created and create_artifacts:
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


async def _start_progress_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> Optional[_ProgressMessage]:
    try:
        if update.message:
            message = await update.message.reply_text(text, disable_notification=True)
        elif update.callback_query and update.callback_query.message:
            message = await update.callback_query.message.reply_text(text, disable_notification=True)
        else:
            user = update.effective_user
            if not user:
                return None
            message = await context.bot.send_message(chat_id=user.id, text=text, disable_notification=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to send progress message", extra={"error": str(exc)})
        return None
    return _ProgressMessage(message, text)


async def _respond(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    rendered, parse_mode = _prepare_telegram_message(text)
    if len(rendered) <= TELEGRAM_MESSAGE_LIMIT:
        await _send_formatted_text(update, context, rendered, parse_mode)
        return

    await _send_long_response(update, context, text)


async def _send_formatted_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    rendered: str,
    parse_mode: Optional[str],
) -> None:
    kwargs = {"disable_web_page_preview": True}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode

    if update.message:
        await update.message.reply_text(rendered, **kwargs)
    elif update.callback_query:
        await update.callback_query.message.reply_text(rendered, **kwargs)
    else:
        user = update.effective_user
        if user:
            await context.bot.send_message(chat_id=user.id, text=rendered, **kwargs)


async def _send_long_response(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_text: str) -> None:
    user = update.effective_user
    drive_link: Optional[str] = None

    if user:
        db = SessionLocal()
        try:
            user_service = UserService(db)
            db_user = user_service.get_or_create_user(
                telegram_id=user.id,
                username=getattr(user, "username", None),
                first_name=getattr(user, "first_name", None),
                last_name=getattr(user, "last_name", None),
            )
            credentials, error = _ensure_google_credentials(db, db_user, 'long_response_upload')
            if credentials and not error:
                drive_link = _upload_text_blob_to_drive(credentials, db_user, raw_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to upload long response to Drive", extra={"user_id": user.id, "error": str(exc)})
        finally:
            db.close()

    if drive_link:
        message = f"Ответ слишком объёмный для Telegram, загрузил его в Google Drive:\n{drive_link}"
        rendered, parse_mode = _prepare_telegram_message(message)
        await _send_formatted_text(update, context, rendered, parse_mode)
        return

    file_path = _export_text_temp(raw_text)
    if file_path:
        note = "Ответ слишком объёмный для Telegram, отправил файл во вложении."
        rendered, parse_mode = _prepare_telegram_message(note)
        await _send_formatted_text(update, context, rendered, parse_mode)
        await _send_generic_document(update, context, file_path, "long_response.docx", "Ответ во вложении.")
        return

    fallback = "Ответ получился слишком большим и не удалось подготовить файл. Попробуй переформулировать запрос."  # noqa: E501
    rendered, parse_mode = _prepare_telegram_message(fallback)
    await _send_formatted_text(update, context, rendered, parse_mode)


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


def _note_to_docx_bytes(text: str) -> bytes:
    cleaned = (text or '').strip()
    if not cleaned:
        cleaned = "(пустая заметка)"
    document = Document()
    for line in cleaned.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


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

    docx_bytes = _note_to_docx_bytes(text)
    filename = f"note_{note.id}_{datetime.datetime.utcnow():%Y%m%d_%H%M%S}.docx"
    try:
        file = upload_docx(credentials, target_folder, filename, docx_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("upload_docx failed", extra={"user_id": user.id, "error": str(exc)})
        return None

    link = (file or {}).get('webViewLink')
    if link:
        note_service.update_note_metadata(
            note,
            links={'drive_url': link},
            drive_file_id=(file or {}).get('id'),
        )
        return link


def _export_note_locally(note: Note, text: str) -> Optional[str]:
    docx_bytes = _note_to_docx_bytes(text)

    try:
        fd, path = tempfile.mkstemp(prefix=f"note_{note.id}_", suffix=".docx")
        with os.fdopen(fd, 'wb') as handle:
            handle.write(docx_bytes)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create local artifact", extra={"note_id": note.id, "error": str(exc)})
        return None


def _upload_text_blob_to_drive(credentials, user, content: str) -> Optional[str]:
    try:
        tree = ensure_tree(credentials, user.username or str(user.telegram_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_tree failed long response", extra={"user_id": user.id, "error": str(exc)})
        return None

    target_folder = (
        tree.get('Responses')
        or tree.get('Notes')
        or tree.get('Inbox')
        or next((tree[val] for val in ('LongTexts', 'Documents', 'Meeting notes') if val in tree), None)
    )
    if not target_folder:
        return None

    docx_bytes = _note_to_docx_bytes(content)
    filename = f"response_{datetime.datetime.utcnow():%Y%m%d_%H%M%S}.docx"
    try:
        file = upload_docx(credentials, target_folder, filename, docx_bytes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("upload_docx failed long response", extra={"user_id": user.id, "error": str(exc)})
        return None

    return (file or {}).get('webViewLink')


def _export_text_temp(content: str) -> Optional[str]:
    docx_bytes = _note_to_docx_bytes(content)
    try:
        fd, path = tempfile.mkstemp(prefix="response_", suffix=".docx")
        with os.fdopen(fd, 'wb') as handle:
            handle.write(docx_bytes)
        return path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to create temp response file", extra={"error": str(exc)})
        return None


async def _send_generic_document(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_path: str,
    filename: str,
    caption: str,
) -> None:
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
        logger.warning("Failed to send long response file", extra={"error": str(exc)})
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception as clear_exc:  # noqa: BLE001
            logger.debug("Failed to cleanup long response file", extra={"path": file_path, "error": str(clear_exc)})


def _should_create_artifact(text: str) -> bool:
    cleaned = (text or '').strip()
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(lowered.startswith(prefix) for prefix in COMMAND_PREFIXES):
        return False
    if cleaned.endswith('?'):
        return False
    if len(cleaned) <= 40 and len(cleaned.split()) <= 6 and not any(ch in cleaned for ch in '.!;:\n'):
        return False
    return True


_MD_BULLET_RE = re.compile(r'^\s*[-*]\s+')
_MD_ORDERED_RE = re.compile(r'^\s*(\d+)\.\s+')
_NOTE_HASH_RE = re.compile(r'(?<![<\w/])#(\d{1,8})\b')


def _build_miniapp_note_link(note_id: int) -> str:
    return _tools_build_note_link(note_id)


def _prepare_telegram_message(text: str) -> tuple[str, Optional[str]]:
    rendered = _render_markdown_like(text)
    parse_mode = ParseMode.HTML if "<" in rendered and ">" in rendered else None
    return rendered, parse_mode


def _render_markdown_like(text: str) -> str:
    lines: list[str] = []
    for raw_line in (text or '').splitlines():
        stripped = raw_line.rstrip()
        plain = stripped.strip()
        if not plain:
            lines.append('')
            continue

        heading = None
        if plain.startswith('### '):
            heading = plain[4:].strip()
        elif plain.startswith('## '):
            heading = plain[3:].strip()
        elif plain.startswith('# '):
            heading = plain[2:].strip()

        if heading is not None:
            lines.append(f"<b>{_render_inline_markdown(heading)}</b>")
            continue

        bullet_match = _MD_BULLET_RE.match(plain)
        if bullet_match:
            content = plain[bullet_match.end():].strip()
            lines.append(f"• {_render_inline_markdown(content)}")
            continue

        ordered_match = _MD_ORDERED_RE.match(plain)
        if ordered_match:
            number = ordered_match.group(1)
            content = plain[ordered_match.end():].strip()
            lines.append(f"{number}. {_render_inline_markdown(content)}")
            continue

        lines.append(_render_inline_markdown(plain))

    return "\n".join(lines)


def _render_inline_markdown(text: str) -> str:
    escaped = _escape_html(text)

    def replace_links(match: re.Match[str]) -> str:
        label = match.group(1)
        url = _escape_attr(match.group(2))
        return f'<a href="{url}">{label}</a>'

    rendered = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_links, escaped)
    rendered = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', rendered)
    rendered = re.sub(r'__(.+?)__', r'<b>\1</b>', rendered)
    rendered = re.sub(r'\*(.+?)\*', r'<i>\1</i>', rendered)
    rendered = re.sub(r'_(.+?)_', r'<i>\1</i>', rendered)
    rendered = re.sub(r'`(.+?)`', r'<code>\1</code>', rendered)
    rendered = _NOTE_HASH_RE.sub(
        lambda match: f'<a href="{_escape_attr(_build_miniapp_note_link(int(match.group(1))))}">#{match.group(1)}</a>',
        rendered,
    )
    return rendered



def _escape_html(text: str) -> str:
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _escape_attr(value: str) -> str:
    return (
        value or ''
    ).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')


def _merge_artifact_hint(base_text: Optional[str], snapshot: _NoteSnapshot) -> str:
    parts: list[str] = []
    if base_text and base_text.strip():
        parts.append(base_text.strip())
    if snapshot.drive_link and (not base_text or snapshot.drive_link not in base_text):
        parts.append(f"Drive: {snapshot.drive_link}")
    if snapshot.local_file and (not base_text or 'файл' not in base_text.lower()):
        parts.append("📎 Файл заметки прикрепил отдельным сообщением.")
    return "\n\n".join(parts).strip()


def _dedupe_response_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return text

    seen: set[str] = set()
    result_lines: list[str] = []

    for line in text.splitlines():
        normalized = line.strip()
        if not normalized:
            if result_lines and result_lines[-1] != "":
                result_lines.append("")
            elif not result_lines:
                result_lines.append("")
            continue

        key = normalized.casefold()
        if key in seen:
            continue

        seen.add(key)
        result_lines.append(line.rstrip())

    # Удаляем ведущие/замыкающие пустые строки, чтобы не плодить разрывов
    while result_lines and result_lines[0] == "":
        result_lines.pop(0)
    while result_lines and result_lines[-1] == "":
        result_lines.pop()

    return "\n".join(result_lines)


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
