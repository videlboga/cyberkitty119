---
title: "Project Overview — Cyberkitty119 (Transkribator)"
author: "Agent Dashboard v3 Team"
date: 2026-07-05
status: Active
tags: [agent, project-overview, research]
related: [RESEARCH.md, docs/INVENTORY.md]
---

# Project Overview — Cyberkitty119 (Transkribator)

Canonical description of the Cyberkitty119 / Transkribator project, distilled from `RESEARCH.md` and `docs/INVENTORY.md`. Use this as the entry point for understanding the system; follow the file paths for detail.

## Stack

| Layer         | Technology / Library                | Version / Notes                                              |
|---------------|-------------------------------------|--------------------------------------------------------------|
| Language      | Python                              | 3.10 (`from __future__ import annotations` for PEP 604). EOL Oct 2026. |
| Bot framework | python-telegram-bot (PTB)           | 22.1, `ApplicationBuilder`, `run_polling(allowed_updates=Update.ALL_TYPES)` |
| ASR client    | `transcribe_client/` (in-repo)      | Adapter abstraction: openrouter, deepinfra, gpu, local, di_worker, stub. One adapter selected via `_resolve_default_adapter`; no inter-adapter fallback on error. |
| ASR orchestrator | `transcriber_v4.py`              | 1987 lines. Gemini chat/completions path + `transcribe_client` path. |
| Worker        | `job_worker.py` (`JobWorker`)       | Pull-loop, `dispatch_job` → `run_media_pipeline` → staged pipeline. |
| Database      | PostgreSQL 16 + pgvector            | `ankane/pgvector:latest` image. `processing_jobs.error` is text, truncated to 4000 chars in `fail_job`. |
| ORM           | SQLAlchemy                          | 2.0.25.                                                       |
| Tests         | pytest + pytest-asyncio             | 8.1.1, `asyncio_mode=auto`. Existing: `tests/test_transcribe_client.py`, `tests/test_job_queue_db.py`. |
| Container     | Docker / docker-compose             | `docker-compose.bot-v2.yml` is the canonical prod topology.   |
| Telegram API  | native `telegram-bot-api`           | Runs in a VPN namespace on the host (not the compose service, which is `profiles: [donotstart]`). |

## Module map

Paths are relative to repo root. Corrected per the INVENTORY fixes (content_processor moved out of `beta/`; root `handlers.py` is gone).

| Component                         | Path                                                | Role |
|-----------------------------------|-----------------------------------------------------|------|
| Bot entrypoint                    | `transkribator_modules/main.py`                     | PTB `Application` setup in `main()` (lines 78–170). Registers `_on_error` via `add_error_handler` (line 170). |
| Bot handlers                      | `transkribator_modules/bot/handlers.py`             | 2262 lines. `handle_message`, `process_*_file`, `_process_external_audio`. Single canonical handler file (legacy root `handlers.py` removed). |
| ASR orchestrator | `transkribator_modules/transcribe/transcriber_v4.py` | Gemini chat/completions path + `transcribe_client` path. `transcribe_segment_with_openrouter_gemini` (line 1799), `_try_transcribe_with_client` (line 183), `format_transcript_with_openrouter` (line 590). |
| Transcribe client core            | `transcribe_client/__init__.py`                     | `TranscribeClient`, `_resolve_default_adapter`. Auto mode prefers OpenRouter when `OPENROUTER_API_KEY` is set. No cross-adapter fallback. |
| OpenRouter adapter                | `transcribe_client/openrouter.py`                   | `_transcribe_bytes` retries on 429/502/503/504, `max_retries=5` hardcoded, backoff `min(2 ** attempt, 30)`. No jitter, no `Retry-After` handling, no `OPENROUTER_MAX_RETRIES` env. Chunk-level throttle via `OPENROUTER_429_THROTTLE_SEC` (default 30s). `transcribe` does chunked sequential transcription. |
| REST API backend                  | `core_api/main.py`                                  | FastAPI app `Second Brain Core API` v2.0.0. Routers under `/api/v1/{system,agent,memory,ingest,transcribe,internal_bot,payments}`. Runs in `core-api` compose service, port `8001:8000`. |
| DeepInfra adapter                 | `transcribe_client/deepinfra.py`                    | `_transcribe_file` with retry + local whisper fallback. Primary in prod (`TRANSCRIBE_DEFAULT_MODE=deepinfra`). |
| Stub adapter                      | `transcribe_client/stub.py`                         | Used by tests. |
| Job worker                        | `job_worker.py`                                     | `JobWorker` pull-loop, `_handle_failure` (line 199) stores raw traceback in `job.error`. |
| Job pipeline                      | `transkribator_modules/jobs/pipeline.py`            | `run_media_pipeline` — stages: prepare/download/transcribe/finalize/deliver/cleanup. Stage failure re-raises. |
| Job services                      | `transkribator_modules/jobs/services.py`            | `default_transcribe_media` (line 120), `default_deliver_results` (line 360, success-only). |
| Job queue                         | `transkribator_modules/jobs/queue.py`               | `fail_job` (line 194): `job.error = error_message[:4000]`. |
| Media job enqueue                 | `transkribator_modules/jobs/media.py`               | `enqueue_media_job` — called from bot handlers. |
| Core API — internal bot           | `core_api/api/v1/internal_bot.py`                   | `GET /jobs/{job_id}` returns `error: job.error` raw (line 61). |
| Core API — ingestion              | `core_api/domains/ingestion/media_service.py`       | `get_job_status` → `JobStatusResponse.error` raw (line 104). |
| Content processor (LLM notes)     | `core_api/domains/agent/core/content_processor.py`  | Summary/tag generation via OpenRouter. `ContentProcessor` marked stub; real logic in `_build_summary_and_tags`. (Moved from `transkribator_modules/beta/` in commit 3e469c3.) |
| MAX bot — native service          | `max_bot/native_service.py`                         | `_poll_completed_jobs` (line 60) sends `job.error` raw via `send_message`. |
| MAX bot — native handlers         | `max_bot/native_handlers.py`                        | `_poll_max_job_progress` (line 203) edits message with `job.error` raw. |
| Dialog / notes agent              | `transkribator_modules/agent/dialog.py`             | Notes creation from transcript, dialog agent. Prompts hardcoded. |
| Config                            | `transkribator_modules/config.py`                   | Env-driven config. `SUPPRESS_FAILURE_MESSAGES` (line 173) exists but does not cover `job.error` path. |

## Deploy topology

Canonical production compose: `docker-compose.bot-v2.yml`. All services share the `bot-v2-net` bridge network.

| Service            | Container               | Image / Build                  | Ports      | Depends on        | Notes |
|--------------------|-------------------------|--------------------------------|------------|-------------------|-------|
| `postgres`         | `bot-v2-postgres`       | `ankane/pgvector:latest`       | —          | —                 | Volume `./postgres_data_transkribator`. Healthcheck `pg_isready`. |
| `bot`              | `bot-v2`                | `Dockerfile.bot-v2`            | —          | `postgres` (healthy) | Env: `TRANSCRIBE_DEFAULT_MODE=deepinfra`, `USE_LOCAL_BOT_API`, `LOCAL_BOT_API_URL=http://172.29.0.2:8081`. Bind-mounts `core_api`, `transkribator_modules`, `transcribe_client`, media, `telegram-bot-api-data` (ro). DNS 8.8.8.8/1.1.1.1, `host.docker.internal:host-gateway`. |
| `worker`           | `bot-v2-worker`         | `Dockerfile` (`cyberkitty119/worker:fix-vpnstack`) | — | `postgres` (healthy) | Entrypoint `entrypoint-worker.sh`, command `python workers/transcribe_worker.py`. `DISABLE_LOCAL_WHISPER=1`, `REMOTE_DEEPINFRA_SSH_ALIAS`/`RELAY_URL` for proxied DeepInfra. Bind-mounts `~/.ssh` ro. |
| `core-api`         | `bot-v2-core-api`       | `Dockerfile.api`               | `8001:8000`| `postgres` (healthy) | FastAPI backend (`core_api/main.py`) for miniapp and internal consumers. |
| `telegram-bot-api` | `bot-v2-telegram-api`   | `aiogram/telegram-bot-api:latest` | `8081:8081` | —              | **Disabled in compose** via `profiles: [donotstart]`. In production the native `telegram-bot-api` runs on the host inside the VPN namespace; `LOCAL_BOT_API_URL` points at it (`172.29.0.2:8081`). See `run-telegram-bot-api-native-vpn.sh`. |

### Production state (Telegram API)

- The compose `telegram-bot-api` service is intentionally not started (`profiles: [donotstart]`).
- A native `telegram-bot-api` binary runs on the host within the VPN namespace, exposing `http://172.29.0.2:8081` to the `bot` and `worker` containers via `LOCAL_BOT_API_URL` / `LOCAL_BOT_FILE_API_URL`.
- `USE_LOCAL_BOT_API` toggles whether PTB talks to the local server vs. the public Telegram API.
- Helper scripts: `run-telegram-bot-api-native-vpn.sh`, `run-telegram-vpn-proxy.sh`, `setup-telegram-vpn-relay.sh`.

### Transcription routing in prod

- `TRANSCRIBE_DEFAULT_MODE=deepinfra` (compose line 66/107) → `DeepInfraAdapter` is the primary transcription path.
- OpenRouter is still exercised by `transcriber_v4.py` Gemini path (when `TRANSCRIBE_CLIENT_ENABLED=0`) and by `format_transcript_with_openrouter` (LLM formatting, already has backoff).
- DeepInfra traffic from the worker is routed via an SSH relay (`REMOTE_DEEPINFRA_SSH_ALIAS=proxy`) or explicit `REMOTE_DEEPINFRA_RELAY_URL`.

## Build & test commands

| Command                  | What it does                                                      |
|--------------------------|-------------------------------------------------------------------|
| `make install`           | Create `venv`, `pip install -r requirements.txt`.                 |
| `make setup`             | Copy `env.sample` → `.env` if missing; create `videos/audio/transcriptions`. |
| `make test`              | `pytest -q` (local). Note: the second `test:` target in `Makefile` overrides the Docker variant. |
| `make docker-test`       | Run tests inside Docker via `scripts/docker-test.sh`.             |
| `make start`             | Start the Telegram bot via `scripts/start.sh`.                    |
| `make start-api`         | Start the API server via `scripts/start-api.sh`.                  |
| `make start-docker`      | Start services via `scripts/docker-start.sh`.                     |
| `make stop-docker`       | `docker-compose down`.                                            |
| `make migrate`           | `alembic upgrade head`.                                           |
| `make revision NAME=msg` | `alembic revision --autogenerate -m "msg"`.                       |
| `make backup-postgres`   | `docker compose exec -T postgres pg_dump` → `backups/`.           |
| `make logs` / `make status` | `docker-compose logs -f` / `docker-compose ps`.               |
| `make clean` / `make clean-all` | Remove `*.pyc`/`__pycache__`/logs; `clean-all` also drops venv and compose images/volumes. |

Build images:
- `docker compose -f docker-compose.bot-v2.yml build bot` — `Dockerfile.bot-v2`
- `docker compose -f docker-compose.bot-v2.yml build worker` — `Dockerfile`
- `docker compose -f docker-compose.bot-v2.yml build core-api` — `Dockerfile.api`

## Production notes & known issues

1. **PTB error handler is registered.** `transkribator_modules/main.py` calls `application.add_error_handler(_on_error)` at line 170; `_on_error` logs `context.error` with `exc_info` but does **not** send a user-visible message. The remaining risk is handlers that dereference `update.message.from_user` / `update.callback_query.from_user` without None-checks on updates such as `edited_message`, `channel_post`, or empty updates under `allowed_updates=Update.ALL_TYPES`.
2. **Raw traceback leaks via `job.error`.** `job_worker.py:_handle_failure` stores `traceback.format_exception(...)` into `job.error` (truncated to 4000 chars). This propagates raw to users through `core_api/api/v1/internal_bot.py:61`, `core_api/domains/ingestion/media_service.py:104`, `max_bot/native_handlers.py:203`, `max_bot/native_service.py:63`. The GDrive/Dropbox/Mega/Yandex.Disk download error sites at `transkribator_modules/bot/handlers.py` leak download exception strings to users (those messages are currently user-friendly Russian text from the downloader modules, but they bypass the bot's generic error wrapper).
3. **OpenRouter 429 handling.** `transcribe_client/openrouter.py:_transcribe_bytes` retries on 429/502/503/504 with `max_retries=5` (hardcoded) and `time.sleep(min(2 ** attempt, 30))`. It lacks jitter, `Retry-After` handling, and the `OPENROUTER_MAX_RETRIES` env override. The return envelope on exhaustion is `{"status": "error", "meta": {"error": ..., "provider": "openrouter"}}` (no `rate_limited=True`). There is no cross-adapter fallback to DeepInfra. The parallel Gemini path in `transcriber_v4.py:1953` retries on 429/500/502/503/504 with plain `continue` and no backoff sleep.
4. **Duplicate package shadows.** `transkribator_modules/transkribator_modules/...` nested package duplicates the canonical `transkribator_modules/` tree and can be imported by mistake (INVENTORY §2, §4). **Verified absent in this worktree.**
5. **`ContentProcessor` stub.** `core_api/domains/agent/core/content_processor.py` is marked stub; real summary/tag logic lives in `_build_summary_and_tags`.
6. **Many compose/Dockerfile variants.** Only `docker-compose.bot-v2.yml` is canonical prod; the rest (`.disabled`, `.proxy`, `.vpn-override`, etc.) are legacy/dev and should be classified or removed.

## Key data flow (transcription)

1. Bot receives audio → `handle_message` → `process_audio_file`/`process_video_file` → `enqueue_media_job` (`transkribator_modules/jobs/media.py`). Status message edited to "Файл принят!".
2. `job_worker.py` `JobWorker` acquires the job → `dispatch_job` → `run_media_pipeline` (`transkribator_modules/jobs/pipeline.py`).
3. Transcribe stage: `default_transcribe_media` (`services.py:120`) → `TranscribeClient(default_mode=TRANSCRIBE_DEFAULT_MODE)` → adapter `.transcribe()`.
4. Prod mode `deepinfra` → `DeepInfraAdapter._transcribe_file` (retry + local whisper fallback).
5. On error: stage raises → `run_media_pipeline` except (line 78) logs + re-raises → `job_worker._handle_failure` → `fail_job(job.id, traceback)` → `job.error = error_message[:4000]`.
6. Deliver stage (`default_deliver_results`, `services.py:360`) runs only on success and sends Telegram messages.