# RESEARCH.md

## Stack

- **Язык:** Python 3.10 (`from __future__ import annotations` для PEP 604 union syntax). EOL Oct 2026.
- **Бот:** python-telegram-bot 22.1 (PTB), entrypoint `transkribator_modules/main.py` → `transkribator_modules/bot/handlers.py` (2262 строки). Application строится через `ApplicationBuilder` в `main()` (строка 78–168), запуск `application.run_polling(allowed_updates=Update.ALL_TYPES)`.
- **ASR pipeline:** `transcribe_client/` — абстракция над адаптерами (openrouter, deepinfra, gpu, local, di_worker, stub). `TranscribeClient` (в `__init__.py`) выбирает ОДИН адаптер через `_resolve_default_adapter` — fallback между адаптерами при ошибке НЕ реализован. Оркестратор: `transkribator_modules/transcribe/transcriber_v4.py` (1987 строк).
- **Worker:** `job_worker.py` (399 строк) — `JobWorker` pull-loop, `dispatch_job` → `transkribator_modules/jobs/pipeline.py` `run_media_pipeline` → stages (prepare/download/transcribe/finalize/deliver/cleanup) из `transkribator_modules/jobs/services.py`.
- **БД:** PostgreSQL 16 + SQLAlchemy 2.0.25. `ProcessingJob.error` — текстовое поле (str, обрезается до 4000 символов в `fail_job`).
- **Тесты:** pytest 8.1.1 + pytest-asyncio (asyncio_mode=auto). `make test` → `pytest -q`. Существующие тесты: `tests/test_transcribe_client.py` (StubAdapter), `tests/test_job_queue_db.py` (enqueue/acquire/complete).
- **Build/test команды:**
  - `make test` → `pytest -q` (локально, второй `test:` target в Makefile перекрывает Docker-вариант).
  - `make install` → venv + pip install -r requirements.txt.

## Architecture

### Directory layout (релевантные файлы задачи)

```
transcribe_client/
  __init__.py          # TranscribeClient, _resolve_default_adapter — НЕТ fallback между адаптерами
  openrouter.py        # OpenRouterAdapter — _transcribe_bytes (retry), transcribe (chunking)
  deepinfra.py         # DeepInfraAdapter — _transcribe_file (retry + fallback на local whisper)
  stub.py              # StubAdapter для тестов
transkribator_modules/
  main.py              # main() — PTB Application setup, НЕТ add_error_handler
  bot/
    handlers.py        # 2262 строки — handle_message, process_*_file, _process_external_audio
                      # строки 1358/1360: _safe_edit_message(status_msg, str(exc)) — утечка str(exc)
  transcribe/
    transcriber_v4.py  # transcribe_segment_with_openrouter_gemini (строка 1799) — 429 retry без backoff
                      # _try_transcribe_with_client (строка 183) — transcribe_client вызов
                      # format_transcript_with_openrouter (строка 590) — LLM форматирование, 429 retry
  jobs/
    services.py        # default_transcribe_media (строка 120) — TranscribeClient вызов, raise RuntimeError
                      # default_deliver_results (строка 360) — ТОЛЬКО success-сообщения в Telegram
    pipeline.py        # run_media_pipeline — stage failure → raise → job_worker._handle_failure
    queue.py           # fail_job (строка 194) — job.error = error_message[:4000]
job_worker.py          # JobWorker._handle_failure (строка 199) — traceback.format_exception → fail_job
core_api/
  api/v1/internal_bot.py     # GET /jobs/{job_id} — возвращает "error": job.error raw (строка 61)
  domains/ingestion/media_service.py  # get_job_status — error=job.error raw (строка 104)
max_bot/
  native_service.py   # _poll_completed_jobs (строка 60) — send_message(chat_id, job.error) raw
  native_handlers.py  # _poll_max_job_progress (строка 203) — edit_message(chat_id, job.error) raw
```

### Key components и flow

**Транскрипция (production path):**
1. Бот получает аудио → `handle_message` → `process_audio_file` / `process_video_file` → `enqueue_media_job` (в `transkribator_modules/jobs/media.py`). Status message редактируется на "✅ Файл принят! Транскрипция началась…".
2. Worker (`job_worker.py`) acquire_job → `dispatch_job` → `run_media_pipeline` → stages.
3. Transcribe stage: `default_transcribe_media` (`services.py:120`) → `TranscribeClient(default_mode=TRANSCRIBE_DEFAULT_MODE)` → `client.transcribe(media_path, mode=mode)`.
4. В проде `TRANSCRIBE_DEFAULT_MODE=deepinfra` (docker-compose.bot-v2.yml:66). НО `_resolve_default_adapter` в auto-режиме предпочитает OpenRouter если `OPENROUTER_API_KEY` задан (строка 85-89 в `__init__.py`). При явном mode=deepinfra → DeepInfraAdapter.
5. OpenRouterAdapter.transcribe → `_transcribe_bytes` (single или chunked) → POST `https://openrouter.ai/api/v1/audio/transcriptions`.
6. При 429: `raise_for_status()` → `HTTPError` (subclass of `RequestException`) → caught at line 134 → retry с `time.sleep(2 ** attempt)` (2s, 4s, 8s). max_retries=3. После 3 попыток — return `{"status": "error", ...}`.
7. `default_transcribe_media` видит status=error → `raise RuntimeError(f"Transcription failed: {error_msg}")`.
8. Pipeline stage raises → `run_media_pipeline` except (line 78) → `logger.exception` + re-raise.
9. `job_worker.py` `_handle_failure` (line 199): `error_message = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))` → `fail_job(job.id, error_message=error_message)` → `job.error = error_message[:4000]` (RAW TRACEBACK).
10. `logger.exception("Job failed")` — полный traceback в логах воркера (это корректно).

**Утечка traceback пользователю:**
- `job.error` содержит сырой traceback (шаг 9 выше).
- Telegram: `default_deliver_results` (`services.py:360`) отправляет ТОЛЬКО success-сообщения. При failure pipeline не доходит до deliver stage. НО:
  - `core_api/api/v1/internal_bot.py:61` — `GET /jobs/{job_id}` отдаёт `"error": job.error` (raw traceback). Это потребляет miniapp и любой поллинг.
  - `core_api/domains/ingestion/media_service.py:104` — `get_job_status` → `JobStatusResponse.error` (raw traceback) → `GET /api/v1/ingest/job/{job_id}`.
  - `max_bot/native_handlers.py:203` — `api.edit_message(chat_id, msg_id, f"❌ Ошибка обработки: {row.get('error')}")` — raw traceback через editMessageText (MAX бот).
  - `max_bot/native_service.py:63` — `api.send_message(chat_id, f"❌ Ошибка обработки:\n{error_text}")` — raw traceback через sendMessage.
  - `transkribator_modules/bot/handlers.py:1358,1360` — `await _safe_edit_message(status_msg, str(exc))` — утечка `str(exc)` для GDrive/Dropbox ошибок скачивания (не transcription traceback, но тот же паттерн).
- Финальное сообщение об ошибке для Telegram-пользователя: при failure job помечается failed, deliver stage не выполняется. Пользователь видит "✅ Файл принят! Транскрипция началась…" и затем... ничего (если нет поллинга в боте). НО если пользователь открывает miniapp или повторно запрашивает статус — получает raw traceback через API.

**AttributeError: 'NoneType' object has no attribute 'from_user':**
- `transkribator_modules/main.py` — НЕТ вызова `application.add_error_handler(...)`. PTB при отсутствии error handler логирует unhandled exception через стандартный logging, но не показывает пользователю.
- Ошибка возникает когда update не содержит message/callback_query (например edited_message, channel_post, или пустой update при `allowed_updates=Update.ALL_TYPES`). Handlers обращаются к `update.message.from_user` или `update.callback_query.from_user` без None-проверок:
  - `bot/handlers.py:227` — `(update.message.text or "").strip()` (если update.message None → AttributeError на .text, не .from_user).
  - `bot/commands.py:656` — `update.message.from_user.id` в start_command (через commands.py).
  - `bot/commands.py:1092,1134,1176,1212,1270` — `update.message.from_user.id` в различных handlers.
  - `max_bot/adapter.py:80` — `self.from_user = None` (FakeMessage, но это MAX).

## Acceptance Criteria

### 1. Fix 429 rate limiting in transcribe_client/openrouter.py
- **AC1.1:** `OpenRouterAdapter._transcribe_bytes` должен делать до 6 попыток (настраиваемо через env `OPENROUTER_MAX_RETRIES`, default 6) при 429/502/503/504.
- **AC1.2:** Backoff — экспоненциальный с jitter: 2s, 4s, 8s, 16s, 30s (cap 30s). При наличии `Retry-After` header в 429 response — использовать его значение (но не более 60s).
- **AC1.3:** Каждая retry-попытка логируется с timestamp, номером попытки, HTTP status, и backoff-задержкой (через `logger.warning` с `extra={"attempt": N, "status": 429, "backoff_sec": X}`).
- **AC1.4:** При persisting 429 (все retry исчерпаны) — `transcribe()` возвращает `{"status": "error", "meta": {"error": ..., "provider": "openrouter", "rate_limited": True}}` вместо raise. Вышестоящий код (`TranscribeClient` или `default_transcribe_media`) должен инициировать fallback на DeepInfra.
- **AC1.5:** Fallback: при ошибке OpenRouter (status=error с rate_limited=True или любой TranscriptionError) — `TranscribeClient.transcribe` (или `default_transcribe_media`) пытается переключиться на DeepInfra (`TRANSCRIBE_DEFAULT_MODE=deepinfra` или явный `DeepInfraAdapter`), если `DEEPINFRA_API_KEY` доступен. Fallback логируется.
- **AC1.6:** Троттлинг: при последовательных 429 — chunk-запросы идут последовательно (не параллельно). В текущем коде chunking уже последовательный (цикл for в transcribe), но это нужно сохранить и не вводить asyncio.gather.

### 2. Hide raw tracebacks from users
- **AC2.1:** `job_worker.py` `_handle_failure` — хранить в `job.error` краткое сообщение (например `f"Processing failed: {type(exc).__name__}: {str(exc)[:200]}"`), а НЕ полный traceback. Полный traceback уже логируется через `logger.exception("Job failed")` (строка 215) — это остаётся в логах воркера.
- **AC2.2:** `fail_job` в `queue.py` — дополнительно sanitize: если `error_message` содержит подстроку `Traceback (most recent call last)` — заменить на `"Internal processing error"`. Это defence-in-depth на случай если другой caller передаёт traceback.
- **AC2.3:** Все точки отображения ошибки пользователю показывают дружелюбное сообщение вместо raw error:
  - `max_bot/native_handlers.py:203` — `f"❌ Ошибка обработки: {row.get('error') or 'Неизвестная ошибка'}"` → `f"❌ Произошла ошибка при обработке. Попробуйте позже или обратитесь в поддержку."` (НЕ показывать job.error).
  - `max_bot/native_service.py:63` — `f"❌ Ошибка обработки:\n{error_text}"` → то же дружелюбное сообщение.
  - `transkribator_modules/bot/handlers.py:1358,1360` — `str(exc)` → дружелюбное сообщение для download-ошибок.
- **AC2.4:** API endpoints (`internal_bot.py:61`, `media_service.py:104`) — могут возвращать `job.error` (он уже sanitize после AC2.1), но miniapp/front-end должен отображать его только в debug-режиме. Для users — показывать generic message. Это помечается как recommendation в engineering notes, не blocking.

### 3. Fix AttributeError: 'NoneType' object has no attribute 'from_user'
- **AC3.1:** В `transkribator_modules/main.py` `main()` — зарегистрировать error handler: `application.add_error_handler(_error_handler)`. Handler логирует exception (через `logger.exception`) и, если update валиден и есть effective_chat, отправляет `await context.bot.send_message(chat_id, "Произошла ошибка. Попробуйте позже.")`.
- **AC3.2:** Error handler должен корректно обрабатывать `update is None` (не падать сам).
- **AC3.3:** Handlers, обращающиеся к `update.message.from_user` / `update.callback_query.from_user` без проверки — должны использовать `update.effective_user` (возвращает None-safe User или None) или добавить None-проверки. Минимум: `handle_message` в `handlers.py` должна early-return если `update.effective_user is None` или `update.message is None`.

## Engineering Notes

### transcribe_client/openrouter.py
- Строки 256–314 — ДУБЛИРУЮТ логику chunked transcription (строки 198–254). Это мёртвый код (unreachable после `return` на строке 243). Инженер может удалить строки 256–314 для чистоты, но это опционально — не часть задачи.
- `_transcribe_bytes` line 116: retry только для `(502, 503, 504)`. 429 попадает в `except RequestException` (line 134) через `raise_for_status()` → `HTTPError`. Это работает, но нечитаемо. Инженер должен явно добавить 429 в retry-условие и обрабатывать `Retry-After` header.
- `requests` импортируется через try/except (line 16–19) — может быть None. Проверка `if requests is None` есть в `transcribe()` (line 166), но не в `_transcribe_bytes`.
- Текущий `max_retries=3` (hardcoded line 106). Заменить на `int(os.getenv("OPENROUTER_MAX_RETRIES", "6"))`.
- Backoff: текущий `time.sleep(2 ** attempt)` → 2s, 4s, 8s. Заменить на `min(2 ** attempt, 30)` + добавить jitter `random.uniform(0, backoff * 0.1)`.

### transcribe_client/__init__.py — fallback
- `TranscribeClient.transcribe` (line 126–138) оборачивает exception в `TranscriptionError` — НЕ пытается fallback.
- `default_transcribe_media` (`services.py:120`) — лучший место для fallback: после `client.transcribe` check `result["status"] == "error"` → если `result["meta"].get("rate_limited")` → создать `TranscribeClient(default_mode="deepinfra")` и retry. Это держит логику в services.py, не трогая TranscribeClient.
- Альтернатива: добавить fallback в `TranscribeClient.transcribe` — но это усложняет абстракцию. Рекомендуется fallback в `default_transcribe_media`.

### transcriber_v4.py — параллельный путь
- `transcribe_segment_with_openrouter_gemini` (line 1799) — отдельный путь транскрипции через chat/completions (не audio/transcriptions). Используется в `transcribe_whole_audio_with_gemini` (line 1043). Этот путь также получает 429 (line 1953) и делает `continue` БЕЗ backoff sleep. НО этот путь активируется только если `_try_transcribe_with_client` вернул None (TRANSCRIBE_CLIENT_ENABLED=0 или transcribe_client не смог). В проде с `TRANSCRIBE_DEFAULT_MODE=deepinfra` и `TRANSCRIBE_CLIENT_ENABLED=1` — основной путь через `transcribe_client`. Инженер должен проверить: если `TRANSCRIBE_CLIENT_ENABLED=1` (default в проде?), то transcriber_v4.py gemini path — это fallback. Если 0 — это primary. Нужно зафиксировать backoff для 429 в `transcribe_segment_with_openrouter_gemini` (line 1953): добавить `await asyncio.sleep(min(2 ** attempt, 30))` перед continue.
- `LLM_FORMAT_RETRY_ATTEMPTS=3` (line 24, env). `format_transcript_with_openrouter` (line 590) уже имеет backoff `min(10, 2 ** attempt)` (line 746) и обрабатывает 429 (line 718, transient_statuses). Этот путь ОК.

### job_worker.py — error_message truncation
- `_handle_failure` (line 199–219): для `UnknownJobTypeError` — уже краткое сообщение. Для остальных — `traceback.format_exception(...)`. Заменить на: `error_message = f"{type(exc).__name__}: {str(exc)[:500]}"`. Полный traceback остаётся в `logger.exception` (line 215).
- `fail_job` (`queue.py:194`) — `job.error = error_message[:4000]`. Добавить sanitize: если `"Traceback (most recent call last)" in error_message` → `error_message = "Internal processing error"`.

### Telegram bot error handler
- `transkribator_modules/main.py` line 164: `application.add_handler(CallbackQueryHandler(handle_callback_query))` — последний handler. После него добавить: `application.add_error_handler(_error_handler)`.
- `_error_handler` должна быть async, signature: `async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None`. Доступ к `context.error` (Exception). Логировать через `logger.exception("Unhandled telegram error", extra={...})`. Отправлять пользователю `await context.bot.send_message(chat_id, "Произошла ошибка. Попробуйте позже.")` только если `update` имеет `effective_chat`.
- PTB 22.1: `Application.add_error_handler(callback)` — принимает async callback `(update, context)`. `context.error` содержит exception. `context.bot` доступен для send_message.
- Guard в `handle_message` (`handlers.py`): добавить early return если `update.effective_user is None` или `update.message is None` в начале функции (до любых обращений к `.from_user`, `.text` и т.д.).

### Тесты
- Существующие: `tests/test_transcribe_client.py` — StubAdapter, 2 теста. `tests/test_job_queue_db.py` — enqueue/acquire/complete (НЕ fail_job).
- Новые тесты (инженер должен добавить):
  - `tests/test_openrouter_retry.py` — mock `requests.post` возвращать 429 N раз, проверить retry count, backoff delays (mock `time.sleep`), и最终的 return `{"status": "error", "meta": {"rate_limited": True}}`.
  - `tests/test_fail_job_sanitize.py` — `fail_job` с traceback-сообщением → `job.error` не содержит "Traceback".
  - `tests/test_error_handler.py` — mock Application, проверить что `_error_handler` вызывается и логирует.
- `make test` → `pytest -q`. Все тесты должны проходить.

### Constraints
- НЕ ломать существующий DeepInfra path — fallback должен работать только при OpenRouter failure, не заменять primary adapter.
- `TRANSCRIBE_DEFAULT_MODE=deepinfra` в docker-compose.bot-v2.yml — значит в проде primary УЖЕ DeepInfra. OpenRouter fallback в transcribe_client не нужен если primary deepinfra. НО: `_resolve_default_adapter` auto-режим предпочитает OpenRouter (line 85). Нужно проверить какой mode реальный в проде: если `TRANSCRIBE_DEFAULT_MODE=deepinfra` → DeepInfraAdapter directly, OpenRouter НЕ участвует. Тогда 429 от OpenRouter возникает только через `transcriber_v4.py` gemini path (если TRANSCRIBE_CLIENT_ENABLED=0) ИЛИ через `format_transcript_with_openrouter` (LLM форматирование, line 590). Задача говорит "OpenRouter возвращает 429 при аудио-транскрибации" — значит OpenRouter IS used for transcription. Это означает либо `TRANSCRIBE_DEFAULT_MODE=openrouter`, либо auto-режим с `OPENROUTER_API_KEY`. Инженер должен фиксить ОБА пути: `transcribe_client/openrouter.py` И `transcriber_v4.py:1799`.
- `SUPPRESS_FAILURE_MESSAGES=true` (config.py:173) — уже есть env для подавления сообщений об ошибках. Это существующий механизм, но он не работает для job.error path (только для inline error messages в handlers).
- Не коммитить, не пушить — только локальные изменения в worktree.
- Соблюдать стиль: `from __future__ import annotations`, logging через `logger` из `transkribator_modules.config`, `extra={...}` для structured logging.