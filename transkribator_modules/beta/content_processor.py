"""Content processing pipeline: markdown generation, Google Drive, Sheets, index."""

from __future__ import annotations

import datetime
import json
import os
import re
import textwrap
from typing import Optional, Callable, Awaitable, Iterable

import aiohttp

from googleapiclient.errors import HttpError

from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL
from transkribator_modules.transcribe.transcriber_v4 import _basic_local_format
from transkribator_modules.db.database import EventService, NoteService, SessionLocal
from transkribator_modules.db.models import NoteStatus
from transkribator_modules.search import IndexService
from .presets import Preset, render_user_prompt
from transkribator_modules.google_api import (
    GoogleCredentialService,
    ensure_tree_cached,
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


FOLDER_MAP = {
    'meeting': 'Meetings',
    'idea': 'Ideas',
    'task': 'Tasks',
    'media': 'Resources',
    'recipe': 'Resources',
    'journal': 'Journal',
}

DRIVE_SYNC_EVENT_KIND = 'drive_sync_pending'


async def _call_preset_llm(system_prompt: str, user_prompt: str) -> Optional[str]:
    if not user_prompt or not OPENROUTER_API_KEY:
        return None

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': os.getenv('OPENROUTER_REFERER', 'https://transkribator.local'),
        'X-Title': os.getenv('OPENROUTER_APP_NAME', 'CyberKitty'),
    }
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


async def _render_with_preset(
    note_text: str,
    preset: Preset,
    *,
    custom_prompt: Optional[str] = None,
    progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
) -> tuple[str, bool]:
    system_prompt = preset.system_prompt or (
        "Ты — ассистент, который преобразует заметки. Следуй инструкции без комментариев от себя."
    )
    user_prompt = render_user_prompt(preset, note_text=note_text, user_prompt=custom_prompt)

    if progress_callback:
        await progress_callback("🤖 Форматирую заметку…")

    try:
        llm_text = await _call_preset_llm(system_prompt, user_prompt)
    except Exception as exc:  # pragma: no cover - сетевые ошибки
        logger.warning("LLM call failed for preset %s", preset.id, extra={"error": str(exc)})
        llm_text = None

    if llm_text:
        if progress_callback:
            await progress_callback("🧾 Форматирование готово.")
        return llm_text.strip(), False

    logger.warning(
        "LLM не вернул результат для пресета %s, используется fallback",
        preset.id,
    )
    if progress_callback:
        await progress_callback("⚠️ Модель не ответила, использую базовое форматирование.")
    return _basic_local_format(note_text), True


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
        progress_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        type_confidence: Optional[float] = None,
        existing_note_id: Optional[int] = None,
    ) -> dict:
        db = SessionLocal()
        errors: list[str] = []

        async def _progress(message: str) -> None:
            if progress_callback:
                try:
                    await progress_callback(message)
                except Exception as exc:  # pragma: no cover - прогресс не должен ронять пайплайн
                    logger.debug("Progress callback failed", extra={"error": str(exc), "stage": message})

        try:
            note_service = NoteService(db)
            note = None
            if existing_note_id:
                note = note_service.get_note(existing_note_id)
                if note and note.user_id != user.id:
                    logger.warning(
                        "Попытка обработать чужую заметку",
                        extra={"existing_note_id": existing_note_id, "user_id": user.id},
                    )
                    note = None
                elif note:
                    note.text = text
                    note.type_hint = type_hint
                    note.type_confidence = type_confidence or note.type_confidence or 0.0
                    note.status = status
                    note.updated_at = datetime.datetime.utcnow()
                    db.commit()
                    db.refresh(note)

            if note is None:
                note = note_service.create_note(
                    user=user,
                    text=text,
                    type_hint=type_hint,
                    status=status,
                    type_confidence=type_confidence,
                )

            await _progress("📥 Получил заметку, готовлю обработку…")

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
                await _progress("⚠️ Не удалось получить доступ к Google. Продолжаю локально.")

            drive_payload = {}
            sheet_payload = {}
            raw_drive_payload = {}
            raw_markdown: Optional[str] = None

            tree = None
            if credentials:
                try:
                    tree = ensure_tree_cached(credentials, user.id, user.username or str(user.telegram_id))
                except HttpError as exc:
                    logger.error("ensure_tree failed", extra={"error": str(exc)})
                    errors.append('google_drive_tree_failed')
                    tree = None
                except TimeoutError as exc:
                    logger.warning("ensure_tree timeout", extra={"error": str(exc)})
                    errors.append('google_drive_tree_failed')
                    tree = None
                    await _progress("⚠️ Google Drive долго отвечает, продолжаю без него.")
                except Exception as exc:  # noqa: BLE001 - сетевые таймауты и прочее
                    logger.warning("ensure_tree exception", extra={"error": str(exc)})
                    errors.append('google_drive_tree_failed')
                    tree = None
                    await _progress("⚠️ Google Drive долго отвечает, продолжаю без него.")

            rendered_output: Optional[str] = summary
            if preset:
                try:
                    rendered_output, _ = await _render_with_preset(
                        text,
                        preset,
                        custom_prompt=custom_prompt,
                        progress_callback=_progress,
                    )
                except Exception as exc:  # pragma: no cover - безопасный fallback
                    logger.warning("Preset render failed", extra={"preset": preset.id, "error": str(exc)})
                    rendered_output = _basic_local_format(text)
                    await _progress("⚠️ Модель не ответила, использую локальное форматирование.")
            if not rendered_output:
                rendered_output = _basic_local_format(text)

            summary_text, computed_tags = await _build_summary_and_tags(
                rendered_output or '',
                text,
                existing_tags=tags,
            )

            note_service.update_note_metadata(
                note,
                summary=summary_text,
                tags=computed_tags,
            )

            if tree and status != NoteStatus.BACKLOG.value:
                inbox_id = tree.get('Inbox')
                if not inbox_id:
                    errors.append('google_inbox_missing')
                else:
                    try:
                        await _progress("☁️ Сохраняю исходную расшифровку в Google Drive…")
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
                                summary=summary_text,
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
                            await _progress("☁️ Сырая расшифровка сохранена.")
                    except HttpError as exc:
                        logger.error("Raw upload failed", extra={"error": str(exc)})
                        errors.append('google_raw_upload_failed')
                        await _progress("⚠️ Не удалось сохранить исходник в Google Drive.")
                    except TimeoutError as exc:
                        logger.warning("Raw upload timeout", extra={"error": str(exc)})
                        errors.append('google_raw_upload_failed')
                        await _progress("⚠️ Google Drive не ответил, исходник сохраню позже.")
            elif status in {NoteStatus.PROCESSED.value, NoteStatus.PROCESSED_RAW.value} and google_error_code:
                errors.append(google_error_code)

            if preset and status != NoteStatus.BACKLOG.value and credentials:
                if not tree:
                    errors.append('google_drive_tree_failed')
                else:
                    folder_label = FOLDER_MAP.get(type_hint, 'Inbox')
                    target_folder = tree.get(folder_label, tree.get('Inbox')) if tree else None
                    final_summary = rendered_output or _basic_local_format(text)
                    fm = _front_matter(type_hint, computed_tags, summary_text)
                    markdown = fm + '\n' + final_summary
                    filename = f"{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{preset.id.replace('.', '_')}.md"
                    if target_folder:
                        try:
                            await _progress("📄 Сохраняю обработанную заметку в Google Drive…")
                            file = upload_markdown(credentials, target_folder, filename, markdown)
                            drive_payload = {'webViewLink': file.get('webViewLink'), 'id': file.get('id'), 'name': filename}
                            links_payload = {'drive_url': file.get('webViewLink')}
                            if raw_drive_payload.get('webViewLink'):
                                links_payload['raw_drive_url'] = raw_drive_payload['webViewLink']
                            note_service.update_note_metadata(
                                note,
                                summary=summary_text,
                                tags=computed_tags,
                                drive_file_id=file.get('id'),
                                status=status,
                                links=links_payload,
                            )

                            sheet_row = {
                                'id': str(note.id),
                                'date': datetime.datetime.utcnow().isoformat(),
                                'type': type_hint,
                                'title': filename,
                                'tags': computed_tags,
                                'drive_path': f"{folder_label}/{filename}",
                                'drive_url': file.get('webViewLink'),
                                'doc_url': '',
                                'extra': preset.description,
                            }
                            sheet_id = tree.get('IndexSheet') if tree else None
                            if sheet_id:
                                upsert_index(credentials, sheet_id, sheet_row)
                            sheet_payload = sheet_row
                            await _progress("📄 Обработанная заметка сохранена в Google Drive.")
                        except HttpError as exc:
                            logger.error("Preset upload failed", extra={"error": str(exc)})
                            errors.append('google_drive_upload_failed')
                            await _progress("⚠️ Не удалось сохранить обработанную заметку в Google Drive.")
                        except TimeoutError as exc:
                            logger.warning("Preset upload timeout", extra={"error": str(exc)})
                            errors.append('google_drive_upload_failed')
                            await _progress("⚠️ Google Drive слишком долго отвечает, обработку сохраню позже.")
                    else:
                        errors.append('google_drive_folder_missing')
                        await _progress("⚠️ Папка Google Drive не найдена.")
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
            await _progress("🧠 Индекс обновлён.")
            result = {
                'note_id': note.id,
                'drive': drive_payload,
                'raw_drive': raw_drive_payload,
                'sheet': sheet_payload,
                'errors': errors,
                'rendered_output': rendered_output,
                'raw_markdown': raw_markdown,
                'tags': computed_tags,
                'preset_id': preset.id if preset else None,
                'sync_queued': False,
            }

            needs_sync = (
                status != NoteStatus.BACKLOG.value
                and credentials is not None
                and (
                    not drive_payload.get('webViewLink')
                    or 'google_drive_tree_failed' in errors
                    or 'google_drive_upload_failed' in errors
                    or 'google_raw_upload_failed' in errors
                    or 'google_inbox_missing' in errors
                    or 'google_drive_folder_missing' in errors
                )
            )

            if needs_sync:
                _queue_drive_sync(
                    db,
                    user.id,
                    {
                        'note_id': note.id,
                        'status': status,
                        'type_hint': type_hint,
                        'tags': computed_tags,
                        'rendered_output': rendered_output,
                        'raw_markdown': raw_markdown,
                        'preset_id': preset.id if preset else None,
                        'custom_prompt': custom_prompt,
                        'timestamp': datetime.datetime.utcnow().isoformat(),
                    },
                )
                result['sync_queued'] = True

            return result
        finally:
            db.close()


def _queue_drive_sync(db, user_id: int, payload: dict) -> None:
    if not payload.get('note_id'):
        return

    service = EventService(db)
    if service.has_event(user_id, DRIVE_SYNC_EVENT_KIND, payload['note_id']):
        return

    try:
        service.add_event(user_id, DRIVE_SYNC_EVENT_KIND, payload)
        logger.info(
            "Drive sync event queued",
            extra={'user_id': user_id, 'note_id': payload['note_id']},
        )
    except Exception as exc:  # pragma: no cover - защитный
        logger.warning(
            "Не удалось создать событие синхронизации",
            extra={'error': str(exc), 'user_id': user_id},
        )
_FRONT_MATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.S)
_TAG_LINE_RE = re.compile(r'^(?:\*\*\s*)?(?:tags?|теги)[:：]\s*(.+)$', re.IGNORECASE)
_HASHTAG_RE = re.compile(r'#(\w[\w\-]{1,30})')


def _strip_markdown_prefix(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r'^#+\s*', '', cleaned)
    cleaned = re.sub(r'^[\-\*•]\s*', '', cleaned)
    cleaned = re.sub(r'^\d+[\).]\s*', '', cleaned)
    return cleaned.strip()


def _parse_front_matter(text: str) -> tuple[Optional[str], Optional[list[str]]]:
    match = _FRONT_MATTER_RE.match(text or '')
    if not match:
        return None, None
    body = match.group(1)
    summary = None
    tags: list[str] | None = None
    for raw_line in body.splitlines():
        if ':' not in raw_line:
            continue
        key, value = raw_line.split(':', 1)
        key = key.strip().lower()
        value = value.strip().strip('"')
        if key == 'summary' and value:
            summary = value.strip()
        elif key == 'tags' and value:
            parsed: list[str] | None = None
            try:
                parsed_json = json.loads(value)
                if isinstance(parsed_json, list):
                    parsed = [str(item).strip() for item in parsed_json if str(item).strip()]
            except json.JSONDecodeError:
                pass
            if parsed is None:
                pieces = re.split(r'[;,\|]', value)
                parsed = [piece.strip() for piece in pieces if piece.strip()]
            tags = parsed or []
    return summary, tags


def _collect_tag_candidates(lines: Iterable[str]) -> list[str]:
    results: list[str] = []
    iterator = iter(enumerate(lines))
    for idx, line in iterator:
        tag_line_match = _TAG_LINE_RE.match(line)
        if tag_line_match:
            raw = tag_line_match.group(1).strip()
            if raw:
                parts = re.split(r'[;,\|]', raw)
                results.extend(parts)
                continue
            # tags declared on following bullet list
            collected: list[str] = []
            for _, maybe_line in iterator:
                stripped = maybe_line.strip()
                if not stripped:
                    break
                if not stripped.startswith(('-', '*', '•')):
                    break
                collected.append(stripped)
            if collected:
                results.extend(collected)
    return results


def _sanitize_tag(raw: str) -> Optional[str]:
    candidate = raw
    candidate = candidate.replace('**', '').strip()
    candidate = re.sub(r'^[-\*•\d#\.\)\(\s]+', '', candidate)
    candidate = candidate.strip('.,;:!?"\'[]{}«»()')
    if not candidate:
        return None
    return candidate[:48]


def _heuristic_tags(rendered_output: str, existing_tags: Optional[list[str]] = None) -> list[str]:
    tags: list[str] = []
    existing = existing_tags or []
    for tag in existing:
        clean = _sanitize_tag(str(tag))
        if clean:
            tags.append(clean)

    summary_from_front_matter, tags_from_front_matter = _parse_front_matter(rendered_output or '')
    if tags_from_front_matter:
        for tag in tags_from_front_matter:
            clean = _sanitize_tag(tag)
            if clean:
                tags.append(clean)

    lines = (rendered_output or '').splitlines()
    for raw_tag in _collect_tag_candidates(lines):
        clean = _sanitize_tag(raw_tag)
        if clean:
            tags.append(clean)

    for hashtag in _HASHTAG_RE.findall(rendered_output or ''):
        clean = _sanitize_tag(hashtag)
        if clean:
            tags.append(clean)

    seen = set()
    ordered: list[str] = []
    for tag in tags:
        normalized = tag.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(tag)
        if len(ordered) >= 6:
            break
    return ordered


def _paragraph_candidates(text: str) -> Iterable[str]:
    for block in re.split(r'\n\s*\n', text or ''):
        cleaned_lines = []
        for raw_line in block.splitlines():
            stripped = _strip_markdown_prefix(raw_line)
            if not stripped:
                continue
            cleaned_lines.append(stripped)
        paragraph = ' '.join(cleaned_lines).strip()
        if paragraph:
            yield re.sub(r'\s+', ' ', paragraph)


def _heuristic_summary(rendered_output: str, original_text: str) -> str:
    summary_front_matter, _ = _parse_front_matter(rendered_output or '')
    if summary_front_matter:
        return summary_front_matter.strip()

    for paragraph in _paragraph_candidates(rendered_output or ''):
        if len(paragraph) < 40:
            continue
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)
        collected = []
        for sentence in sentences:
            if not sentence:
                continue
            collected.append(sentence.strip())
            if len(' '.join(collected)) >= 220 or len(collected) >= 2:
                break
        if collected:
            return ' '.join(collected)

    fallback = (original_text or '').strip()
    if not fallback:
        return ''
    fallback = re.sub(r'\s+', ' ', fallback)
    return fallback[:220]


async def _llm_summary_and_tags(rendered_output: str, original_text: str, base_summary: str, base_tags: list[str]) -> tuple[str, list[str]]:
    if not OPENROUTER_API_KEY:
        return base_summary, base_tags

    source_text = rendered_output.strip() or original_text.strip()
    if not source_text:
        return base_summary, base_tags

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'Content-Type': 'application/json',
        'HTTP-Referer': os.getenv('OPENROUTER_REFERER', 'https://transkribator.local'),
        'X-Title': os.getenv('OPENROUTER_APP_NAME', 'CyberKitty'),
    }
    system_prompt = (
        'Ты обрабатываешь заметку и возвращаешь JSON. '
        'Структура: {"summary": "две-три ёмких русских фразы до 280 символов", "tags": ["тег1", "тег2", ...]}. '
        'Теги — 3-6 коротких слов или фраз без хэштегов. '
        'Только JSON без комментариев.'
    )
    user_prompt = f"Заметка:\n<<<\n{source_text[:4000]}\n>>>"
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
    except Exception as exc:  # noqa: BLE001
        logger.warning('Summary LLM call failed', extra={'error': str(exc)})
        return base_summary, base_tags

    choices = data.get('choices') or []
    if not choices:
        return base_summary, base_tags
    content = choices[0].get('message', {}).get('content') or ''
    match = re.search(r'{.*}', content, re.S)
    if not match:
        return base_summary, base_tags
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return base_summary, base_tags

    summary_candidate = str(parsed.get('summary') or '').strip()
    tags_candidate = parsed.get('tags')
    tags_list: list[str] = base_tags[:]
    if isinstance(tags_candidate, list):
        for tag in tags_candidate:
            clean = _sanitize_tag(str(tag))
            if clean:
                tags_list.append(clean)
    if summary_candidate:
        base_summary = summary_candidate

    seen = set()
    merged: list[str] = []
    for tag in tags_list:
        lowered = tag.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(tag)
        if len(merged) >= 6:
            break

    return base_summary, merged


async def _build_summary_and_tags(
    rendered_output: str,
    original_text: str,
    existing_tags: Optional[list[str]] = None,
) -> tuple[str, list[str]]:
    summary = _heuristic_summary(rendered_output, original_text)
    tags = _heuristic_tags(rendered_output, existing_tags)

    needs_llm = (len(summary) < 80) or (not tags)
    if needs_llm:
        summary, tags = await _llm_summary_and_tags(rendered_output, original_text, summary, tags)

    summary = summary.strip()
    if len(summary) > 280:
        summary = summary[:277].rstrip() + '…'

    return summary, tags
