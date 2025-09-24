"""Content processing pipeline: markdown generation, Google Drive, Sheets, index."""

from __future__ import annotations

import datetime
import json
import os
import textwrap
from typing import Optional

import aiohttp

from googleapiclient.errors import HttpError

from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL
from transkribator_modules.transcribe.transcriber_v4 import format_transcript_with_llm, _basic_local_format
from transkribator_modules.db.database import NoteService, SessionLocal
from transkribator_modules.db.models import NoteStatus
from transkribator_modules.search import IndexService
from .presets import Preset, get_presets
from transkribator_modules.google_api import (
    GoogleCredentialService,
    ensure_tree,
    upload_markdown,
    upsert_index,
)


def _front_matter(note_type: str, tags: list[str], summary: str) -> str:
    now = datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')
    tags_fmt = '[' + ', '.join(tags) + ']' if tags else '[]'
    summary_line = summary.replace('"', '\"')
    return textwrap.dedent(
        f"""---
created: {now}
type: {note_type}
tags: {tags_fmt}
summary: "{summary_line}"
---
"""
    )


def _ensure_signature(text: str) -> str:
    base = (text or '').rstrip()
    signature = '@CyberKitty19_bot'
    if not base:
        return signature
    if signature in base.splitlines()[-1]:
        return base
    return f"{base}\n\n{signature}"


async def _call_preset_llm(note_text: str, instruction: str) -> Optional[str]:
    if not instruction or not OPENROUTER_API_KEY:
        return None

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': os.getenv('OPENROUTER_REFERER', 'https://transkribator.local'),
        'X-Title': os.getenv('OPENROUTER_APP_NAME', 'CyberKitty'),
    }
    system_prompt = (
        "Ты — ассистент, который преобразует заметки в Markdown. "
        "Строго следуй инструкции, не добавляй пояснений от себя и не повторяй формулировку запроса."
    )
    user_prompt = (
        f"Инструкция: {instruction}\n\n"
        f"Текст: <<<\n{note_text}\n>>>\n\n"
        "Верни только финальный результат в Markdown."
    )

    payload = {
        'model': OPENROUTER_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.0,
        'top_p': 0.1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=25),
            ) as response:
                response.raise_for_status()
                data = await response.json()
        choices = data.get('choices') or []
        if not choices:
            return None
        content = choices[0].get('message', {}).get('content')
        return content.strip() if content else None
    except Exception as exc:  # noqa: BLE001
        logger.warning('Preset LLM call failed', extra={'error': str(exc)})
        return None


async def _generate_summary(note_text: str, preset: Preset) -> str:
    prompt_map = {
        'meeting_protocol': (
            "Сделай протокол встречи. Добавь разделы Agenda, Decisions, Action Items, Risks."
        ),
        'meeting_who_what': "Кратко распиши кто что делает и сроки.",
        'idea_outline': "Выдели 5-8 тезисов и 3 next steps по идее.",
        'task_breakdown': "Составь список задач с асignee и дедлайнами.",
        'media_summary': "Сделай конспект с таймкодами [мм:сс] и 5-7 идей.",
        'recipe_steps': "Опиши ингредиенты и пошаговый рецепт.",
        'journal_reflect': "Сформируй 3-5 тезисов о состоянии и вывод,",
        'other_outline': "Сделай структурированные пункты и действия.",
    }
    prompt = prompt_map.get(preset.id)
    if not prompt:
        return note_text[:200]
    try:
        llm_text = await _call_preset_llm(note_text, prompt)
        if llm_text:
            return llm_text
    except Exception as exc:
        logger.warning("LLM summary failed", extra={"error": str(exc)})
    return _basic_local_format(note_text)


class ContentProcessor:
    def __init__(self):
        self.index = IndexService()

    async def process(
        self,
        user,
        text: str,
        type_hint: str,
        preset: Optional[Preset],
        status: str,
        tags: Optional[list[str]] = None,
        summary: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> dict:
        db = SessionLocal()
        errors: list[str] = []
        try:
            note_service = NoteService(db)
            note = note_service.create_note(
                user=user,
                text=text,
                type_hint=type_hint,
                status=status,
            )

            google_credentials = None
            credentials = None
            google_error_code = None
            try:
                google_credentials = GoogleCredentialService(db)
                credentials = google_credentials.get_credentials(user.id)
                if not credentials and google_error_code is None:
                    google_error_code = 'google_auth_required'
            except RuntimeError as exc:
                logger.info(
                    "Google integration disabled",
                    extra={"reason": str(exc), "user_id": user.id},
                )
                google_error_code = 'google_config_missing'
            except Exception as exc:
                logger.warning(
                    "Failed to load Google credentials",
                    extra={"error": str(exc), "user_id": user.id},
                )
                google_error_code = 'google_credentials_error'

            drive_payload = {}
            sheet_payload = {}
            raw_drive_payload = {}

            tree = None
            if credentials:
                try:
                    tree = ensure_tree(credentials, user.username or str(user.telegram_id))
                except HttpError as exc:
                    logger.error("ensure_tree failed", extra={"error": str(exc)})
                    errors.append('google_drive_tree_failed')
                    tree = None

            if preset and preset.id.endswith('_free') and custom_prompt:
                try:
                    llm_text = await _call_preset_llm(text, custom_prompt)
                    summary = llm_text or _basic_local_format(text)
                except Exception as exc:
                    logger.warning("Custom prompt processing failed", extra={"error": str(exc)})
                    summary = _basic_local_format(text)

            if tree and status != NoteStatus.BACKLOG.value:
                inbox_id = tree.get('Inbox')
                if not inbox_id:
                    errors.append('google_inbox_missing')
                else:
                    try:
                        timestamp = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                        raw_filename = f"{timestamp}_{note.id}_raw.md"
                        raw_markdown = _ensure_signature(text)
                        raw_file = upload_markdown(credentials, inbox_id, raw_filename, raw_markdown)
                        raw_drive_payload = {'webViewLink': raw_file.get('webViewLink'), 'id': raw_file.get('id'), 'name': raw_filename}
                        note_service.update_note_metadata(
                            note,
                            links={'raw_drive_url': raw_file.get('webViewLink')},
                        )

                        if status == NoteStatus.PROCESSED_RAW.value:
                            note_service.update_note_metadata(
                                note,
                                summary=text[:140],
                                drive_file_id=raw_file.get('id'),
                                status=status,
                                links={'drive_url': raw_file.get('webViewLink')},
                            )
                            sheet_id = tree.get('IndexSheet')
                            if sheet_id:
                                sheet_row = {
                                    'id': str(note.id),
                                    'date': datetime.datetime.utcnow().isoformat(),
                                    'type': type_hint,
                                    'title': raw_filename,
                                    'tags': [],
                                    'drive_path': f"Inbox/{raw_filename}",
                                    'drive_url': raw_file.get('webViewLink'),
                                    'doc_url': '',
                                    'extra': 'raw',
                                }
                                upsert_index(credentials, sheet_id, sheet_row)
                                sheet_payload = sheet_row
                            drive_payload = raw_drive_payload
                    except HttpError as exc:
                        logger.error("Raw upload failed", extra={"error": str(exc)})
                        errors.append('google_raw_upload_failed')
            elif status in {NoteStatus.PROCESSED.value, NoteStatus.PROCESSED_RAW.value} and google_error_code:
                errors.append(google_error_code)

            if preset and status != NoteStatus.BACKLOG.value and credentials:
                if not tree:
                    errors.append('google_drive_tree_failed')
                else:
                    folder_map = {
                        'meeting': 'Meetings',
                        'idea': 'Ideas',
                        'task': 'Tasks',
                        'media': 'Resources',
                        'recipe': 'Resources',
                        'journal': 'Journal',
                    }
                    target_folder = tree.get(folder_map.get(type_hint, 'Inbox'), tree.get('Inbox')) if tree else None
                    final_summary = summary or await _generate_summary(text, preset)
                    fm = _front_matter(type_hint, tags or [], final_summary.split('\n')[0])
                    markdown = fm + '\n' + final_summary
                    filename = f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{preset.id}.md"
                    if target_folder:
                        try:
                            file = upload_markdown(credentials, target_folder, filename, markdown)
                            drive_payload = {'webViewLink': file.get('webViewLink'), 'id': file.get('id'), 'name': filename}
                            links_payload = {'drive_url': file.get('webViewLink')}
                            if raw_drive_payload.get('webViewLink'):
                                links_payload['raw_drive_url'] = raw_drive_payload['webViewLink']
                            note_service.update_note_metadata(
                                note,
                                summary=final_summary,
                                tags=tags or [],
                                drive_file_id=file.get('id'),
                                status=status,
                                links=links_payload,
                            )

                            sheet_row = {
                                'id': str(note.id),
                                'date': datetime.datetime.utcnow().isoformat(),
                                'type': type_hint,
                                'title': filename,
                                'tags': tags or [],
                                'drive_path': f"{folder_map.get(type_hint, 'Inbox')}/{filename}",
                                'drive_url': file.get('webViewLink'),
                                'doc_url': '',
                                'extra': preset.description,
                            }
                            sheet_id = tree.get('IndexSheet') if tree else None
                            if sheet_id:
                                upsert_index(credentials, sheet_id, sheet_row)
                            sheet_payload = sheet_row
                        except HttpError as exc:
                            logger.error("Preset upload failed", extra={"error": str(exc)})
                            errors.append('google_drive_upload_failed')
                    else:
                        errors.append('google_drive_folder_missing')
            elif preset and status != NoteStatus.BACKLOG.value and google_error_code:
                errors.append(google_error_code)

            # index regardless of Google availability
            try:
                note_tags = json.loads(note.tags or '[]') if note.tags else []
                if not isinstance(note_tags, list):
                    note_tags = []
            except Exception:
                note_tags = tags or [] or []
            try:
                link_payload = json.loads(note.links or '{}') if note.links else {}
                if not isinstance(link_payload, dict):
                    link_payload = {}
            except Exception:
                link_payload = {}

            self.index.add(
                note.id,
                user.id,
                text,
                summary=note.summary,
                type_hint=note.type_hint,
                tags=note_tags,
                links=link_payload,
            )
            return {
                'note': note,
                'drive': drive_payload,
                'raw_drive': raw_drive_payload,
                'sheet': sheet_payload,
                'errors': errors,
            }
        finally:
            db.close()
