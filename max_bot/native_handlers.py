from __future__ import annotations
import asyncio

import os
import time
import tempfile
from pathlib import Path
from typing import Optional

from .api_client import MaxAPI
from .native_types import Event, Attachment
from transkribator_modules.config import logger, MAX_FILE_SIZE_MB, AUDIO_DIR, VIDEOS_DIR

from transkribator_modules.db.database import SessionLocal, UserService, get_media_duration, log_event
from bot.handlers import _build_note_file_content, _build_note_filename
from .core_api_client import enqueue_media_job, get_job_status_sync, get_note_for_job_sync
from transkribator_modules.utils.large_file_downloader import download_large_file
from transkribator_modules.audio.extractor import extract_audio_from_video, compress_audio_for_api


def _attachment_best_filename(att: Attachment) -> str:
    if att.filename:
        return att.filename
    # derive from url
    if att.url:
        p = Path(att.url.split("?")[0])
        if p.name:
            return p.name
    # fallback
    return f"media_{int(time.time())}"


def _is_video_by_name(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in {'.mp4', '.mkv', '.mov', '.webm', '.avi', '.flv', '.wmv', '.m4v', '.3gp'}


def _is_audio_by_name(name: str) -> bool:
    ext = Path(name).suffix.lower()
    return ext in {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.opus', '.wma'}


MAX_USER_STATES = {}

def _get_telegram_id_from_event(event: Event) -> int:
    try:
        return int(event.user.id)
    except Exception:
        return abs(hash(str(event.user.id))) % (10 ** 9)

def _get_or_create_user_from_event(event: Event):
    from types import SimpleNamespace
    tid = _get_telegram_id_from_event(event)
    return SimpleNamespace(id=tid)


def _main_menu_keyboard_inline() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "💎 Подписка", "callback_data": "menu:subscription"},
                {"text": "🐱 Личный кабинет", "callback_data": "menu:profile"}
            ],
            [
                {"text": "🔎 Поиск по заметкам", "callback_data": "menu:search"}
            ],
            [
                {"text": "⚙️ Настройки", "callback_data": "menu:settings"},
                {"text": "❓ Помощь", "callback_data": "menu:help"}
            ]
        ]
    }

def _qa_menu_keyboard_inline() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "⬅️ В главное меню", "callback_data": "menu:main"}
            ]
        ]
    }




def _enqueue_external_audio(user_id: int, audio_path: str, filename: str, file_size_mb: Optional[float], duration_minutes: Optional[float], source_url: Optional[str], chat_id: Optional[str] = None):
    try:
        from .core_api_client import enqueue_media_job as core_enqueue
        base_name = f"external_{Path(audio_path).stem}_{int(time.time())}"
        job_id = asyncio.run(core_enqueue(
            telegram_id=user_id,
            file_id=base_name,
            audio_path=str(audio_path),
            message_id=None
        ))
        from types import SimpleNamespace
        return SimpleNamespace(id=job_id)
    except Exception as e:
        logger.error(f"Failed to enqueue: {e}")
        from types import SimpleNamespace
        return SimpleNamespace(id=0)


import threading
import tempfile

def _deliver_result_max(chat_id: str, msg_id: str, job_id: int, filename: str, api: MaxAPI):
    """Синхронно высылает результат обработки в MAX-чат."""
    note = get_note_for_job_sync(job_id)
    job_row = get_job_status_sync(job_id)
    payload = (job_row or {}).get("payload") or {}
    result_blob = payload.get("_result") or {}
    raw_transcript = result_blob.get("raw_transcript")
    inline_transcript = result_blob.get("final_transcript")
    segments_blob = result_blob.get("segments")
    segments = segments_blob if isinstance(segments_blob, list) else []

    if note:
        file_content = _build_note_file_content(note, raw_transcript, filename, segments)
        try:
            normalized_title = _build_note_filename(note)
            caption = "🐱 CyberKitty119 Транскрибатор\n[Написать Боту](https://max.ru/id632523990270_bot)"
            reply_markup = {"inline_keyboard": [[{"text": "💬 Спросить по заметке", "callback_data": f"noteqa:{note.get('id')}"}]]}
            from io import BytesIO
            bio = BytesIO(file_content.encode("utf-8"))
            api.send_document(chat_id, bio, f"{normalized_title}.txt", caption=caption)
            try:
                api.send_message(chat_id, "Действия по заметке:", reply_markup=reply_markup)
            except Exception:
                pass
                api.edit_message(chat_id, msg_id, f"📂 {normalized_title}\n✅ Готово! Результат отправлен.")
            except Exception:
                pass
            return
        except Exception:
            logger.exception("max_bot delivery note failed")
            pass

    transcript = inline_transcript or get_transcript_for_job(job_id)
    if transcript:
        try:
            from io import BytesIO
            bio = BytesIO(transcript.encode("utf-8"))
            api.send_document(chat_id, bio, f"{Path(filename).stem}_transcript.txt", caption="🐱 CyberKitty119 Транскрибатор | Транскрипция\n[Бот](https://max.ru/id632523990270_bot)", parse_mode="Markdown")
            try:
                api.edit_message(chat_id, msg_id, f"📂 {filename}\n✅ Готово! Транскрипция отправлена.")
            except Exception:
                pass
        except Exception:
            logger.exception("max_bot delivery transcript failed")
            pass
        return

    try:
        api.edit_message(chat_id, msg_id, f"📂 {filename}\n✅ Обработка завершена, но текст не найден.")
    except Exception:
        pass


def _poll_max_job_progress(chat_id: str, msg_id: str, job_id: int, filename: str, api: MaxAPI):
    """Синхронный поллинг прогресса ProcessingJob для MAX бота."""
    import time
    started = time.monotonic()
    last_text = None
    TIMEOUT = 3600
    POLL_INTERVAL = 3.0

    def _progress_bar(progress: Optional[int], width: int = 12) -> str:
        if progress is None:
            return "▒" * width
        filled = int(width * progress / 100)
        return "█" * filled + "▒" * (width - filled)

    while True:
        elapsed = time.monotonic() - started
        if elapsed > TIMEOUT:
            try:
                api.edit_message(chat_id, msg_id, f"📂 {filename}\n⏰ Превышено время ожидания.")
            except Exception:
                pass
            return

        row = get_job_status_sync(job_id)
        if not row:
            time.sleep(POLL_INTERVAL)
            continue

        status = row.get("status", "unknown")
        raw_progress = row.get("progress")
        stage_progress = row.get("stage_progress")

        if status == "completed":
            # Рабочий успешно завершил задачу, поэтому мы сами собираем и отправляем файл
            try:
                api.edit_message(chat_id, msg_id, f"📂 {filename}\n✅ Завершаю обработку, загружаю файл...")
            except Exception:
                pass
            _deliver_result_max(chat_id, msg_id, job_id, filename, api)
            return
        
        if status == "failed":
            try:
                api.edit_message(chat_id, msg_id, f"📂 {filename}\n❌ Произошла ошибка при обработке. Попробуйте позже или обратитесь в поддержку.")
            except Exception:
                pass
            return

        status_emoji = "⏳ В очереди" if status == "new" else "⚙️ Обрабатывается"
        if status == "stt_transcribing":
            status_emoji = "🗣️ Транскрипция"
        elif status == "agent_formatting":
            status_emoji = "🧠 Анализ"

        try:
            progress = max(0, min(100, int(raw_progress))) if raw_progress is not None else None
        except (ValueError, TypeError):
            progress = None

        try:
            s_progress = max(0, min(100, int(stage_progress))) if stage_progress is not None else None
        except (ValueError, TypeError):
            s_progress = None

        # Выбираем, какую полосу показывать (общую, или в стадии)
        bar_val = progress if progress is not None else s_progress
        bar_str = f"`[{_progress_bar(bar_val)}]` {bar_val}%" if bar_val is not None else "🌀"
        
        text = f"📂 {filename}\n🐱 {status_emoji}\n{bar_str}"

        if text != last_text:
            try:
                api.edit_message(chat_id, msg_id, text)
            except Exception:
                pass
            last_text = text

        time.sleep(POLL_INTERVAL)

def handle_event(event: Event, api: Optional[MaxAPI] = None) -> None:
    api = api or MaxAPI()
    t = threading.Thread(target=_process_event_async, args=(event, api))
    t.start()



import httpx
import os
CORE_API_URL = os.getenv("CORE_API_URL", "http://bot-v2-core-api:8000")
CORE_API_SERVICE_TOKEN = os.getenv("CORE_API_SERVICE_TOKEN", "").strip()

def _core_headers():
    headers = {}
    if CORE_API_SERVICE_TOKEN:
        headers["X-Service-Token"] = CORE_API_SERVICE_TOKEN
    return headers

def _show_profile_max(event: Event, api: MaxAPI) -> None:
    try:
        try:
            tid = int(event.user.id)
        except Exception:
            tid = abs(hash(str(event.user.id))) % (10 ** 9)

        params = {}
        if event.user.first_name: params['first_name'] = event.user.first_name
        if event.user.last_name: params['last_name'] = event.user.last_name
            
        with httpx.Client() as client:
            res = client.get(
                f"{CORE_API_URL}/api/v1/system/profile/tg/{tid}",
                params=params,
                timeout=10.0,
                headers=_core_headers(),
            )
            res.raise_for_status()
            data = res.json()

        plan_status = data.get("plan_status_text", "")
        plan_name = data.get("current_plan", "free").capitalize()
        limit_val = data.get('minutes_limit')
        rem_val = data.get('minutes_remaining')
        limit_str = f"{limit_val:.1f}" if limit_val is not None else "Безлимитно"
        rem_str = f"{rem_val:.1f}" if rem_val is not None else "Безлимитно"
        usage_text = f"• Использовано минут: {data.get('minutes_used_this_month', 0):.1f}\n• Лимит минут: {limit_str}\n• Остаток минут: {rem_str}"
        
        msg = f"👤 **Ваш профиль (MAX):**\n\nВам доступен тариф **{plan_name}** {plan_status}\n\n📊 **Использование в этом месяце:**\n{usage_text}\n\n📝 **Всего обработано файлов:** {data.get('transcriptions_count', 0)}"
        api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())
    except Exception as e:
        logger.exception("Failed to show profile in MAX via API")
        api.send_message(event.chat_id, "❌ Произошла ошибка. Попробуйте позже.", reply_markup=_main_menu_keyboard_inline())

def _show_subscription_max(event: Event, api: MaxAPI) -> None:
    try:
        plans_text = (
            "💎 Тарифы CyberKitty Transkribator\n"
            "🆓 Бесплатный\n"
            "• Безлимитные минуты\n"
            "• 3 генерации в месяц\n"
            "• Базовое качество\n\n"
            "💎 Профессиональный — 299₽/мес\n"
            "• 10 часов транскрибации\n"
            "• Приоритетная обработка\n\n"
            "🚀 Безлимитный — 699₽/мес\n"
            "• Полный безлимит\n"
            "• Максимальный приоритет\n\n"
            "🚀 Безлимит на год — 4900₽/год\n"
            "• Безлимит на 12 месяцев\n"
            "• Все функции включены\n\n"
            "⚠️ Покупка тарифов пока доступна только в нашем Telegram боте @cyberkitty119_bot или по ссылке."
        )
        api.send_message(event.chat_id, plans_text, reply_markup=_main_menu_keyboard_inline())
    except Exception as e:
        api.send_message(event.chat_id, "Ошибка.", reply_markup=_main_menu_keyboard_inline())

def _show_search_max(event: Event, api: MaxAPI) -> None:
    _ACTIVE_MAX_SEARCH_USERS.add(event.user.id)
    msg = "��🔎 Напиши, что найти в заметках. Я поищу по содержимому и тегам. (Для отмены выберите любое действие в меню)"
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())
    
def _show_settings_max(event: Event, api: MaxAPI) -> None:
    msg = "⚙️ Настройки в разработке. Если нужно что-то сменить (например формат) — напиши и помогу вручную."
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())
    
def _show_help_max(event: Event, api: MaxAPI) -> None:
    msg = "❓ Я бот-транскрибатор. Отправь мне аудио или видео файл через скрепку, и я превращу его в текст и короткую заметку!"
    api.send_message(event.chat_id, msg, reply_markup=_main_menu_keyboard_inline())

def _process_event_async(event: Event, api: MaxAPI) -> None:

    """Process a normalized Event: download attachments and enqueue processing jobs.

    This intentionally mirrors transkribator behaviour for external files but
    uses the MAX download URL flows and the shared enqueue pipeline.
    """
    api = api or MaxAPI()

    if event.callback_data:
        logger.info("native_handlers: received callback_data=%s user=%s", event.callback_data, event.user.id)
        if event.callback_data.startswith("result:download_text:"):
            try:
                job_id = int(event.callback_data.split(":")[-1])
                from transkribator_modules.db.models import ProcessingJob
                db = SessionLocal()
                try:
                    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
                    if job and job.payload and "_result" in job.payload:
                        text_path = job.payload["_result"].get("text_path")
                        if not text_path:
                            # Generate on the fly if not in payload
                            text = job.payload["_result"].get("final_transcript") or job.payload["_result"].get("raw_transcript") or ""
                            if text:
                                from transkribator_modules.config import TRANSCRIPTIONS_DIR
                                TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)
                                text_path = str(TRANSCRIPTIONS_DIR / f"transcript_{job.id}.txt")
                                with open(text_path, "w", encoding="utf-8") as f:
                                    f.write(text)
                        
                        if text_path and Path(text_path).exists():
                            with open(text_path, "rb") as f:
                                api.send_document(event.chat_id, f, Path(text_path).name, caption="📄 Транскрипция готова.")
                        else:
                            api.send_message(event.chat_id, "❌ Файл с текстом недоступен.")
                    else:
                        api.send_message(event.chat_id, "❌ Результат не найден.")
                finally:
                    db.close()
            except Exception as e:
                logger.exception("native_handlers: failed to handle download_text callback")
                api.send_message(event.chat_id, "❌ Ошибка при скачивании файла.")
        elif event.callback_data == "menu:subscription":
            _show_subscription_max(event, api)
        elif event.callback_data == "menu:profile":
            _show_profile_max(event, api)
        elif event.callback_data == "menu:search":
            _show_search_max(event, api)
        elif event.callback_data == "menu:settings":
            _show_settings_max(event, api)
        elif event.callback_data == "menu:help":
            _show_help_max(event, api)
        elif event.callback_data.startswith("result:ask:"):
            api.send_message(event.chat_id, "В этой (MAX) версии бота функция QA пока в разработке. Отправьте аудио или видео для новой транскрипции!")
        elif event.callback_data.startswith("noteqa:"):
            # User requested to start a QA session tied to a specific note.
            try:
                _, nid = event.callback_data.split(":", 1)
                note_id = int(nid)
            except Exception:
                api.send_message(event.chat_id, "⚠️ Не удалось открыть чат для этой заметки.")
                return

            # Inform core API to set active note for this user (so agent_chat includes note context)
            # Use synchronous helper to avoid nesting event loops in threads
            try:
                from .core_api_client import set_active_note_sync
                tid = _get_telegram_id_from_event(event)
                if tid is None:
                    api.send_message(event.chat_id, "⚠️ Не удалось определить пользователя.")
                    return
                logger.info("Starting set_active_note_sync for telegram_id=%s note_id=%s", tid, note_id)
                set_active_note_sync(telegram_id=tid, note_id=note_id, local_artifact=True)
                MAX_USER_STATES[tid] = "QA"
                logger.info("set_active_note_sync succeeded for telegram_id=%s note_id=%s", tid, note_id)
                api.send_message(event.chat_id, "💬 Спросите что угодно по заметке. Я в контексте всей транскрипции.", reply_markup=_qa_menu_keyboard_inline())
            except Exception as exc:
                logger.exception("Failed to start note QA session (sync): %s", exc)
                api.send_message(event.chat_id, "⚠️ Ошибка: не удалось включить чат с заметкой.")
        elif event.callback_data == "menu:main":
            tid = _get_telegram_id_from_event(event)
            MAX_USER_STATES.pop(tid, None)
            try:
                from .core_api_client import set_active_note_sync
                set_active_note_sync(telegram_id=tid, note_id=0, local_artifact=False)
            except Exception:
                pass
            api.send_message(
                event.chat_id,
                "Привет! Я бот для транскрибации аудио и видео. Выберите действие или просто отправьте мне аудио/видео файл:",
                reply_markup=_main_menu_keyboard_inline()
            )
        return

    if not event.attachments and not event.text:
        logger.info("native_handlers: no attachments in event chat=%s user=%s", event.chat_id, event.user.id)
        return

    if event.text and not event.attachments:
        # Ignore echo of our own messages
        # "✅ Обработка завершена!" - is ours
        if "Обработка завершена!" in event.text or "✅ Принял сообщение" in event.text:
            return
            
        text_lower = event.text.lower().strip()
        
        # --- Handle all texts with Agent Chat ---
        from .core_api_client import agent_chat
        
        if text_lower not in {"/start", "старт", "/help", "помощь", "❓ помощь", "главное меню", "main:menu", "💎 подписка", "подписка", "🐱 личный кабинет", "личный кабинет", "профиль", "🔎 поиск по заметкам", "поиск по заметкам", "поиск", "⚙️ настройки", "настройки"}:
            try:
                api.send_message(event.chat_id, "⏳ Думаю...")
                tid = _get_telegram_id_from_event(event)
                answer = asyncio.run(agent_chat(
                    telegram_id=tid,
                    text=event.text.strip(),
                    name=event.user.first_name,
                    username=event.user.username
                ))
                if answer:
                    is_qa = MAX_USER_STATES.get(tid) == "QA"
                    markup = _qa_menu_keyboard_inline() if is_qa else _main_menu_keyboard_inline()
                    api.send_message(event.chat_id, answer, reply_markup=markup)
                    return
            except Exception as e:
                logger.error(f"Max bot agent chat error: {e}")
                api.send_message(event.chat_id, "❌ Ошибка вызова агента.")
                return

        # default fallback
        if text_lower in {"/start", "старт", "/help", "помощь", "❓ помощь", "main:menu", "главное меню"}:
            api.send_message(
                event.chat_id, 
                "Привет! Я бот для транскрибации аудио и видео. Выберите действие или просто отправьте мне аудио/видео файл:",
                reply_markup=_main_menu_keyboard_inline()
            )
            return
        
        # Mock handlers for other menu buttons if sent as text
        if text_lower in {"💎💎 подписка", "подписка"}:
            _show_subscription_max(event, api)
            return
        if text_lower in {"🐱 личный кабинет", "личный кабинет", "профиль"}:
            _show_profile_max(event, api)
            return
        if text_lower in {"🔎 поиск по заметкам", "поиск по заметкам", "поиск"}:
            _show_search_max(event, api)
            return
        if text_lower in {"⚙️ настройки", "настройки"}:
            _show_settings_max(event, api)
            return

        api.send_message(event.chat_id, f"✅ Принял текстовое сообщение. Пока бот принимает только медиафайлы. ({len(event.text)} симв.)")
        return

    # For simplicity, process first attachment only (expand later if needed)
    for att in event.attachments:
        status_msg = api.send_message(event.chat_id, "Файл принят! Готовлю обработку…\n\n🎵 Загружаю файл в MAX...")
        msg_id = None
        if isinstance(status_msg, dict):
            _m = status_msg.get("message", {})
            msg_id = _m.get("body", {}).get("mid") or _m.get("mid")
        last_progress_time = [time.time()]
        
        def progress_callback(downloaded, total):
            if not msg_id or not total:
                return
            now = time.time()
            if now - last_progress_time[0] < 1.5:
                return
            last_progress_time[0] = now
            percent = int((downloaded / total) * 100)
            width = 12
            filled = int(width * percent / 100)
            bar = "█" * filled + "▒" * (width - filled)
            try:
                # file_size_mb = total / (1024 * 1024)
                api.edit_message(event.chat_id, msg_id, f"🐱 Загружаю медиа…\n`[{bar}]` {percent}%")
            except Exception:
                pass
        # debug dump per-attachment when missing URL or small oddities
        try:
            if not att.url:
                os.makedirs("data", exist_ok=True)
                with open("data/max_native_debug.log", "a", encoding="utf-8") as fh:
                    import json as _json

                    fh.write(_json.dumps({"ts": int(time.time()), "note": "attachment_missing_url", "attachment": att.raw, "event_raw": event.raw}, ensure_ascii=False) + "\n---\n")
        except Exception:
            logger.exception("native_handlers: failed to write per-attachment debug dump")
        if not att.url:
            logger.warning("native_handlers: attachment has no url, skipping: %s", att.raw)
            continue

        filename = _attachment_best_filename(att)
        # try to determine type
        if _is_video_by_name(filename):
            # download video to VIDEOS_DIR
            VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
            dest = VIDEOS_DIR / f"max_video_{att.id or int(time.time())}_{filename}"
            ok = api.download_url_to_file(att.url, str(dest), expected_size_bytes=att.size, progress_callback=progress_callback)
            if not ok:
                logger.error("native_handlers: failed to download video %s", att.url)
                continue
            if msg_id:
                try:
                    api.edit_message(event.chat_id, msg_id, "🎛️ Конвертирую видео в аудио…")
                except Exception:
                    pass
            compressed = dest
            # user
            user = _get_or_create_user_from_event(event)
            duration_minutes = get_media_duration(str(dest)) if dest.exists() else None
            file_size_mb = (dest.stat().st_size / (1024 * 1024)) if dest.exists() else None
            job = _enqueue_external_audio(user.id, str(compressed), filename, file_size_mb, duration_minutes, att.url, chat_id=event.chat_id)
            if msg_id:
                threading.Thread(target=_poll_max_job_progress, args=(event.chat_id, msg_id, job.id, filename, api)).start()
                try:
                    api.edit_message(event.chat_id, msg_id, "✅ Структурирую файл…\n⏱️ Это может занять некоторое время.")
                except Exception:
                    pass
            try:
                log_event(user, "max_video_queued", {"filename": filename, "source_url": att.url})
            except Exception:
                logger.debug("Failed to log max_video_queued", exc_info=True)
            # We process just first workable attachment
            return

        if _is_audio_by_name(filename) or (att.mime and att.mime.startswith("audio")):
            AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            dest = AUDIO_DIR / f"max_audio_{att.id or int(time.time())}_{filename}"
            ok = api.download_url_to_file(att.url, str(dest), expected_size_bytes=att.size, progress_callback=progress_callback)
            if not ok:
                logger.error("native_handlers: failed to download audio %s", att.url)
                continue
            compressed = asyncio.run(compress_audio_for_api(dest))
            user = _get_or_create_user_from_event(event)
            duration_minutes = get_media_duration(str(dest)) if dest.exists() else None
            file_size_mb = (dest.stat().st_size / (1024 * 1024)) if dest.exists() else None
            job = _enqueue_external_audio(user.id, str(compressed), filename, file_size_mb, duration_minutes, att.url, chat_id=event.chat_id)
            if msg_id:
                threading.Thread(target=_poll_max_job_progress, args=(event.chat_id, msg_id, job.id, filename, api)).start()
                try:
                    api.edit_message(event.chat_id, msg_id, "✅ Структурирую файл…\n⏱️ Это может занять некоторое время.")
                except Exception:
                    pass
            try:
                log_event(user, "max_audio_queued", {"filename": filename, "source_url": att.url})
            except Exception:
                logger.debug("Failed to log max_audio_queued", exc_info=True)
            return

        # fallback: unknown type - treat as external audio if small or just enqueue as external
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        dest = AUDIO_DIR / f"max_media_{att.id or int(time.time())}_{filename}"
        ok = api.download_url_to_file(att.url, str(dest), expected_size_bytes=att.size, progress_callback=progress_callback)
        if not ok:
            logger.error("native_handlers: failed to download fallback media %s", att.url)
            continue
        compressed = asyncio.run(compress_audio_for_api(dest))
        user = _get_or_create_user_from_event(event)
        duration_minutes = get_media_duration(str(dest)) if dest.exists() else None
        file_size_mb = (dest.stat().st_size / (1024 * 1024)) if dest.exists() else None
        job = _enqueue_external_audio(user.id, str(compressed), filename, file_size_mb, duration_minutes, att.url, chat_id=event.chat_id)
        if msg_id:
            threading.Thread(target=_poll_max_job_progress, args=(event.chat_id, msg_id, job.id, filename, api)).start()
            try:
                api.edit_message(event.chat_id, msg_id, "✅ Структурирую файл…\n⏱️ Это может занять некоторое время.")
            except Exception:
                pass
        try:
            log_event(user, "max_attachment_queued", {"filename": filename, "source_url": att.url})
        except Exception:
            logger.debug("Failed to log max_attachment_queued", exc_info=True)
        return
