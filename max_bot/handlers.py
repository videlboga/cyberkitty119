"""Handlers for incoming Max messenger events.

This file contains minimal code to accept an incoming media event, download the
file, enqueue a media job and start a polling task to deliver progress/results.
Adjust to fit the real Max webhook format.
"""
from __future__ import annotations
import asyncio
import time
from pathlib import Path
from typing import Optional

from max_bot.api_client import MaxAPI
from max_bot.config import MEDIA_INCOMING_DIR, PROGRESS_POLL_INTERVAL, PROGRESS_TIMEOUT, logger
from max_bot.db import ensure_user
from max_bot.jobs import create_media_job
from bot.db import get_job_row, get_note_for_job, get_transcript_for_job


async def handle_media_event(event: dict, *, api: Optional[MaxAPI] = None) -> None:
    """Process a media event from Max.

    Expected event (example): {"chat_id": "user-123", "file_url": "https://...", "file_id": "abc", "filename": "voice.ogg"}
    """
    api = api or MaxAPI()
    chat_id = event.get("chat_id")
    file_url = event.get("file_url")
    file_id = event.get("file_id") or (file_url and file_url.split("/")[-1])
    filename = event.get("filename") or f"media_{file_id}.bin"
    message_id = event.get("message_id")

    # If event is a raw provider update, try to extract chat/text from it
    recipient_obj = None
    if not chat_id:
        try:
            raw = event.get("_raw_update") or event
            msg = raw.get("message") or {}
            rec = msg.get("recipient") or {}
            recipient_obj = rec or None
            chat_id = chat_id or rec.get("chat_id") or rec.get("user_id")
            # also support nested body text
            if not file_url:
                file_url = (msg.get("body") or {}).get("file_url")
        except Exception:
            pass
    else:
        # If chat_id present but caller provided raw update, capture recipient
        try:
            raw = event.get("_raw_update") or event
            msg = raw.get("message") or {}
            rec = msg.get("recipient") or {}
            if rec:
                recipient_obj = rec
        except Exception:
            recipient_obj = None

    logger.info("[max] received media event chat=%s file=%s filename=%s", chat_id, file_id, filename)
    dest_path = Path(MEDIA_INCOMING_DIR) / f"{file_id}_{filename}"
    try:
        # If no file_url present, this may be a text message; handle below
        ok = True
        if file_url:
            ok = api.download_url_to_file(file_url, str(dest_path))
    except Exception as exc:
        logger.exception("[max] download error")
        # send simple error message
        try:
            api.send_message(chat_id, f"❌ Не удалось скачать файл: {exc}")
        except Exception:
            pass
        return

    # If there is no file_url, treat this as a text/update event and reply simply
    if not file_url:
        # Try to extract text from the event
        text = event.get("text")
        if not text:
            try:
                text = (event.get("_raw_update") or {}).get("message", {}).get("body", {}).get("text")
            except Exception:
                text = None
        try:
            reply = f"✅ Принял сообщение: {text or '[пустое сообщение]'}"
            # Prefer sending using the raw update when available (it contains
            # recipient and sender info) so the API client can pick correct
            # recipient shape.
            target = (event.get("_raw_update") or event) if (event.get("_raw_update") or event) else (recipient_obj if recipient_obj is not None else chat_id)
            api.send_message(target, reply)
        except Exception:
            logger.exception("[max] failed to send reply to text message")
        return

    # Ensure/create internal user
    try:
        user_id = ensure_user(max_id=chat_id, username=chat_id)
    except Exception:
        logger.exception("[max] ensure_user failed")
        try:
            target = (event.get("_raw_update") or event) if (event.get("_raw_update") or event) else (recipient_obj if recipient_obj is not None else chat_id)
            api.send_message(target, "❌ Не удалось зарегистрировать пользователя. Попробуй позже.")
        except Exception:
            pass
        return

    # Create job
    try:
        job = create_media_job(
            user_id=user_id,
            max_user_id=chat_id,
            file_id=file_id,
            audio_path=str(dest_path),
            message_id=message_id,
        )
    except Exception:
        logger.exception("[max] create job failed")
        try:
            api.send_message(chat_id, "❌ Не удалось поставить задачу в очередь. Попробуй позже.")
        except Exception:
            pass
        return

    # Inform user
    try:
        target = (event.get("_raw_update") or event) if (event.get("_raw_update") or event) else (recipient_obj if recipient_obj is not None else chat_id)
        status_msg = api.send_message(target, f"📥 Получил файл: {filename}\n⬇️ Скачан. Ставлю в очередь…")
        status_message_id = str(status_msg.get("id") or status_msg.get("message_id"))
    except Exception:
        status_message_id = None

    # Start background polling
    asyncio.create_task(
        _poll_and_deliver_max(
            chat_id=chat_id,
            status_message_id=status_message_id,
            job_id=job.id,
            filename=filename,
            api=api,
        ),
        name=f"max_poll_job_{job.id}",
    )


async def _poll_and_deliver_max(
    *,
    chat_id: str,
    status_message_id: Optional[str],
    job_id: int,
    filename: str,
    api: MaxAPI,
) -> None:
    started = time.monotonic()
    last_text = None

    while True:
        elapsed = time.monotonic() - started
        if elapsed > PROGRESS_TIMEOUT:
            try:
                api.send_message(chat_id, "⏰ Превышено время ожидания. Задача могла зависнуть.")
            except Exception:
                pass
            return

        row = get_job_row(job_id)
        if row is None:
            await asyncio.sleep(PROGRESS_POLL_INTERVAL)
            continue

        status = row.get("status")
        progress = row.get("progress")
        stage_label = row.get("stage_label")
        stage_progress = row.get("stage_progress")

        text = f"📂 {filename}\n\nСтатус: {status}\nПрогресс: {progress or '—'}%"
        if stage_label:
            text = f"{text}\nСтадия: {stage_label} {stage_progress or ''}%"

        if text != last_text:
            try:
                if status_message_id:
                    api.edit_message(chat_id, status_message_id, text)
                else:
                    api.send_message(chat_id, text)
            except Exception:
                # ignore send/edit errors
                pass
            last_text = text

        if status == "completed":
            await _deliver_result_max(chat_id=chat_id, job_id=job_id, filename=filename, api=api)
            return
        if status == "failed":
            try:
                api.send_message(chat_id, f"❌ Ошибка при обработке: {row.get('error')}")
            except Exception:
                pass
            return

        await asyncio.sleep(PROGRESS_POLL_INTERVAL)


async def _deliver_result_max(chat_id: str, job_id: int, filename: str, api: MaxAPI) -> None:
    note = get_note_for_job(job_id)
    job_row = get_job_row(job_id)
    payload = (job_row or {}).get("payload") or {}
    result_blob = payload.get("_result") or {}
    raw_transcript = result_blob.get("raw_transcript")
    inline_transcript = result_blob.get("final_transcript")

    if note:
        # build a text file with the note content (reuse bot logic optionally)
        # For now, send raw transcript as document
        content = raw_transcript or inline_transcript or note.get("text")
        if not content:
            try:
                api.send_message(chat_id, "✅ Готово, но текст недоступен.")
            except Exception:
                pass
            return
        try:
            from io import BytesIO
            bio = BytesIO(content.encode("utf-8"))
            api.send_document(chat_id, bio, f"{Path(filename).stem}_note.txt", caption="Результат обработки")
            api.send_message(chat_id, "✅ Файл с заметкой отправлен!")
        except Exception:
            pass
        return

    transcript = inline_transcript or get_transcript_for_job(job_id)
    if not transcript:
        try:
            api.send_message(chat_id, "✅ Готово, но текст недоступен.")
        except Exception:
            pass
        return

    try:
        from io import BytesIO
        bio = BytesIO(transcript.encode("utf-8"))
        api.send_document(chat_id, bio, f"{Path(filename).stem}_transcript.txt", caption="Транскрипция готова")
        api.send_message(chat_id, "✅ Транскрипция отправлена!")
    except Exception:
        try:
            api.send_message(chat_id, "❌ Не удалось отправить файл результата.")
        except Exception:
            pass
