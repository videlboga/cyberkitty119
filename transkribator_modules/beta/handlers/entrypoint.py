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

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from transkribator_modules.config import (
    MINIAPP_NOTE_LINK_TEMPLATE,
    MINIAPP_PROXY_QUERY_PARAM,
    MINIAPP_PROXY_URL,
    logger,
)
from transkribator_modules.db.database import SessionLocal, UserService, NoteService, log_event
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.google_api import GoogleCredentialService, ensure_tree, upload_docx
from docx import Document

from ..agent_runtime import AGENT_MANAGER
from ..note_utils import auto_finalize_note, build_note_artifact_content
from ..tools import (
    _ensure_google_credentials,
    _looks_like_question,
    _build_miniapp_note_link as _tools_build_note_link,
    format_note_saved_message,
    get_note_display_title,
)


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
_PENDING_NOTE_KEY = "pending_note"
_PENDING_CONFIRM = "beta:note_confirm"
_PENDING_DECLINE = "beta:note_decline"
_RESULT_CAPTION_HTML = '<a href="https://t.me/CyberKitty19_bot">CyberKitty119 Транскрибатор</a>'
_FILENAME_FORBIDDEN_RE = re.compile(r'[\\/:*?"<>|\r\n]+')


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

    try:
        logger.info(
            "beta.process_text: start",
            extra={
                "update_id": getattr(update, "update_id", None),
                "user_id": getattr(getattr(update, "effective_user", None), "id", None),
                "source": source,
            },
        )
    except Exception:
        pass
    user = update.effective_user
    if not user:
        return

    if not text or not text.strip():
        await _respond(update, context, "Не нашёл текста в сообщении. Попробуй ещё раз.")
        return

    session = AGENT_MANAGER.get_session(user)
    beta_state = context.user_data.setdefault("beta", {})
    snapshot: Optional[_NoteSnapshot] = None
    question = await _looks_like_question(text)

    ingest_context = source in {"audio", "video", "voice", "media", "backlog"}
    ingest_context = ingest_context or force_mode == "content"
    active_note_id = beta_state.get("active_note_id")

    if not ingest_context and not active_note_id and not question:
        lowered = text.strip().lower()
        is_command = any(lowered.startswith(prefix + " ") or lowered == prefix for prefix in COMMAND_PREFIXES)
        if not is_command:
            beta_state[_PENDING_NOTE_KEY] = {
                "text": text,
                "source": source,
                "created_at": datetime.datetime.utcnow().isoformat(),
            }
            snippet = text.strip()
            if len(snippet) > 280:
                snippet = snippet[:277] + "…"
            message = "Создать новую заметку из этого текста?"
            if snippet:
                message += f"\n\n{snippet}"
            await _respond(
                update,
                context,
                message,
                reply_markup=_build_pending_keyboard(),
            )
            return

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
            # Debug: log snapshot / active note context to help trace why later queries may not match
            try:
                logger.info(
                    "DEBUG: process_text created/updated note",
                    extra={
                        "user_id": user.id,
                        "note_id": getattr(snapshot.note, "id", None),
                        "created": bool(snapshot.created),
                        "source": source,
                        "note_ts": getattr(snapshot.note, "ts", None).isoformat() if getattr(snapshot.note, "ts", None) else None,
                        "note_summary_len": len((snapshot.note.summary or "")[:200]),
                    },
                )
            except Exception:
                logger.debug("Failed to log process_text snapshot info", exc_info=True)
            if snapshot.note and (snapshot.created or not (snapshot.note.summary and snapshot.note.summary.strip())):
                updated_note = await auto_finalize_note(snapshot.note.id)
                if updated_note:
                    snapshot.note = updated_note
            session.set_active_note(snapshot.note, local_artifact=bool(snapshot.local_file))
            beta_state["active_note_id"] = snapshot.note.id
            beta_state["source"] = source
            
            # Для медиа (audio/video) - показываем заметку напрямую без агента
            if source in {"audio", "video", "voice"}:
                from transkribator_modules.beta.tools import format_note_saved_message
                final_text = format_note_saved_message(note=snapshot.note)
                response = None
            else:
                # Для остальных источников - запускаем агента
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

        # Обрабатываем ответ если он есть
        if response:
            cleaned_response = _dedupe_response_text(response.text)
        else:
            cleaned_response = ""

        if snapshot:
            # Для медиа уже есть final_text из format_note_saved_message
            if source not in {"audio", "video", "voice"}:
                final_text = _merge_artifact_hint(cleaned_response, snapshot)
            # else: final_text уже установлен выше
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
            await _send_local_artifact(update, context, snapshot.local_file, snapshot.note)

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
    try:
        logger.info(
            "beta.handle_update: route",
            extra={
                "update_id": getattr(update, "update_id", None),
                "user_id": getattr(getattr(update, "effective_user", None), "id", None),
            },
        )
    except Exception:
        pass
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
        try:
            logger.info(
                "beta.progress: created",
                extra={
                    "update_id": getattr(update, "update_id", None),
                    "msg_id": getattr(message, "message_id", None),
                    "chat_id": getattr(getattr(message, "chat", None), "id", None),
                },
            )
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to send progress message", extra={"error": str(exc)})
        return None
    return _ProgressMessage(message, text)


async def _respond(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    rendered, parse_mode = _prepare_telegram_message(text)
    if len(rendered) <= TELEGRAM_MESSAGE_LIMIT:
        await _send_formatted_text(
            update,
            context,
            rendered,
            parse_mode,
            reply_markup=reply_markup,
        )
        return

    await _send_long_response(update, context, text)


async def _send_formatted_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    rendered: str,
    parse_mode: Optional[str],
    *,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    kwargs = {"disable_web_page_preview": True}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    if reply_markup:
        kwargs["reply_markup"] = reply_markup

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

    # Если Drive недоступен, шлём ответ батчами сообщений, а не файлом
    async def _send_text_in_chunks(text: str) -> None:
        MAX = 3800  # запас до лимита Telegram 4096
        # 1) Пытаемся разделить по смысловым блокам: строка-заголовок + тело
        lines = text.splitlines()
        blocks: list[str] = []
        cur: list[str] = []
        def is_heading(line: str) -> bool:
            l = line.strip()
            return bool(l) and (l.startswith('🔹') or l.startswith('⭐') or l.startswith('###') or (l.startswith('**') and l.endswith('**') and len(l) <= 80))
        for ln in lines:
            if is_heading(ln) and cur:
                blocks.append("\n".join(cur).strip())
                cur = [ln]
            else:
                cur.append(ln)
        if cur:
            blocks.append("\n".join(cur).strip())

        # Если не удалось распознать блоки — делим по длине/абзацам
        if len(blocks) <= 1:
            blocks = []
            buf = text
            while buf:
                if len(buf) <= MAX:
                    blocks.append(buf)
                    break
                cut = buf.rfind('\n\n', 0, MAX)
                if cut == -1:
                    cut = buf.rfind('\n', 0, MAX)
                if cut == -1:
                    cut = MAX
                blocks.append(buf[:cut])
                buf = buf[cut:].lstrip()

        # 2) Гарантируем, что каждый блок влезает в одно сообщение
        out_parts: list[str] = []
        for b in blocks:
            if len(b) <= MAX:
                out_parts.append(b)
                continue
            # Перерезаем крупный блок по абзацам
            buf = b
            while buf:
                if len(buf) <= MAX:
                    out_parts.append(buf)
                    break
                cut = buf.rfind('\n\n', 0, MAX)
                if cut == -1:
                    cut = buf.rfind('\n', 0, MAX)
                if cut == -1:
                    cut = MAX
                out_parts.append(buf[:cut])
                buf = buf[cut:].lstrip()

        for chunk in out_parts:
            rendered, parse_mode = _prepare_telegram_message(chunk)
            await _send_formatted_text(update, context, rendered, parse_mode)

    await _send_text_in_chunks(raw_text)
    return

    fallback = "Ответ получился слишком большим и не удалось подготовить файл. Попробуй переформулировать запрос."  # noqa: E501
    rendered, parse_mode = _prepare_telegram_message(fallback)
    await _send_formatted_text(update, context, rendered, parse_mode)


def _build_pending_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Создать", callback_data=_PENDING_CONFIRM),
                InlineKeyboardButton("❌ Не сохранять", callback_data=_PENDING_DECLINE),
            ]
        ]
    )


def _ensure_note_artifact(
    google_service: GoogleCredentialService,
    note_service: NoteService,
    user,
    note: Note,
    text: str,
) -> tuple[Optional[str], Optional[str]]:
    artifact_text = build_note_artifact_content(note, text)
    drive_link = _upload_note_to_drive(google_service, note_service, user, note, artifact_text)
    if drive_link:
        return drive_link, None
    local_file = _export_note_locally(note, artifact_text)
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
    content = (text or "").strip() or "(пустая заметка)"
    try:
        fd, path = tempfile.mkstemp(prefix=f"note_{note.id}_", suffix=".txt")
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")
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
    text = (content or "").strip()
    try:
        fd, path = tempfile.mkstemp(prefix="response_", suffix=".txt")
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            if text and not text.endswith("\n"):
                handle.write("\n")
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



def _normalize_block_for_dedupe(text: Optional[str]) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _escape_html(text: str) -> str:
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _escape_attr(value: str) -> str:
    return (
        value or ''
    ).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')


def _merge_artifact_hint(base_text: Optional[str], snapshot: _NoteSnapshot) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    def _append(candidate: Optional[str]) -> None:
        if not candidate:
            return
        stripped = candidate.strip()
        if not stripped:
            return
        key = _normalize_block_for_dedupe(stripped)
        if not key or key in seen:
            return
        seen.add(key)
        parts.append(stripped)

    normalized_base = base_text.strip() if base_text and base_text.strip() else ""
    _append(normalized_base)

    note_block = ""
    if snapshot.note:
        note_block = (format_note_saved_message(note=snapshot.note) or "").strip()
        _append(note_block)

    if snapshot.drive_link:
        drive_hint = f"Drive: {snapshot.drive_link}"
        if not normalized_base or snapshot.drive_link not in normalized_base:
            _append(drive_hint)

    if snapshot.local_file and (not normalized_base or 'файл' not in normalized_base.lower()):
        _append("📎 Файл заметки прикрепил отдельным сообщением.")

    # Если ничего не набралось (неожиданный кейс) — вернём отформатированную заметку
    if not parts and note_block:
        parts.append(note_block)

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


def _build_result_filename(note: Optional[Note], file_path: str) -> str:
    suffix = Path(file_path).suffix or ".txt"
    base_title = get_note_display_title(note) if note else ""
    if not base_title:
        base_title = f"note_{note.id if note and note.id else 'result'}"

    normalized = _FILENAME_FORBIDDEN_RE.sub(" ", base_title).strip()
    normalized = re.sub(r"\s+", "_", normalized, flags=re.UNICODE).strip("_")
    if not normalized:
        base_title = f"note_{note.id if note and note.id else 'result'}"
        normalized = base_title
    if len(normalized) > 80:
        normalized = normalized[:80].rstrip("_-.") or normalized[:80]
    return f"{normalized}{suffix}"


async def _send_local_artifact(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: str, note: Note) -> None:
    caption_rendered = _RESULT_CAPTION_HTML
    parse_mode = ParseMode.HTML
    filename = _build_result_filename(note, file_path)
    try:
        if update.message:
            with open(file_path, 'rb') as handle:
                await update.message.reply_document(
                    handle,
                    filename=filename,
                    caption=caption_rendered,
                    parse_mode=parse_mode,
                )
        elif update.callback_query and update.callback_query.message:
            with open(file_path, 'rb') as handle:
                await update.callback_query.message.reply_document(
                    handle,
                    filename=filename,
                    caption=caption_rendered,
                    parse_mode=parse_mode,
                )
        else:
            user = update.effective_user
            if user:
                with open(file_path, 'rb') as handle:
                    await context.bot.send_document(
                        chat_id=user.id,
                        document=handle,
                        filename=filename,
                        caption=caption_rendered,
                        parse_mode=parse_mode,
                    )
        
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to send local artifact",
            extra={"note_id": note.id if note else None, "error": str(exc)},
        )
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception as clear_exc:  # noqa: BLE001
            logger.debug("Failed to remove temp artifact", extra={"path": file_path, "error": str(clear_exc)})


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    data = (query.data or "").strip()
    if data == _PENDING_CONFIRM:
        try:
            log_event(update.effective_user.id, "bot_beta_note_confirm", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log beta callback event", exc_info=True)
        await _handle_pending_confirmation(update, context, accept=True)
    elif data == _PENDING_DECLINE:
        try:
            log_event(update.effective_user.id, "bot_beta_note_decline", {
                "callback_data": data
            })
        except Exception:
            logger.debug("Failed to log beta callback event", exc_info=True)
        await _handle_pending_confirmation(update, context, accept=False)


async def _handle_pending_confirmation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    accept: bool,
) -> None:
    query = update.callback_query
    if not query:
        return

    beta_state = context.user_data.setdefault("beta", {})
    pending = beta_state.pop(_PENDING_NOTE_KEY, None)

    if not pending:
        await query.edit_message_text("Нет текста для сохранения.")
        return

    if not accept:
        await query.edit_message_text("Ок, не сохраняю.")
        return

    text = (pending.get("text") or "").strip()
    if not text:
        await query.edit_message_text("Текст пустой, нечего сохранять.")
        return

    user = update.effective_user
    if not user:
        await query.edit_message_text("Не удалось определить пользователя.")
        return

    await query.edit_message_text("📝 Создаю заметку…")

    session = AGENT_MANAGER.get_session(user)
    source = pending.get("source") or "message"
    create_artifacts = _should_create_artifact(text)

    snapshot = _create_or_update_note(
        user,
        text,
        source,
        existing_note=None,
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

    response = await session.handle_ingest(payload, progress=None)
    final_text = _merge_artifact_hint(_dedupe_response_text(response.text), snapshot)

    if snapshot.local_file:
        await _send_local_artifact(update, context, snapshot.local_file, snapshot.note)

    summary_text = final_text or f"Создал заметку #{snapshot.note.id}."
    await query.edit_message_text("✅ Заметка создана.")
    await _respond(update, context, summary_text)
