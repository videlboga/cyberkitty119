# RESEARCH.md

## Stack

- **Язык:** Python 3.10 (EOL Oct 2026 — в System Status отмечен план миграции на 3.11+). В коде уже используется `from __future__ import annotations` для совместимости с 3.10 type hints.
- **Бот:** python-telegram-bot 22.1 (с job-queue), entrypoint `cyberkitty_modular.py` → `transkribator_modules/main.py` → `transkribator_modules/bot/handlers.py`.
- **API:** FastAPI 0.108.0 + uvicorn 0.25.0 + pydantic 2.5.3. Два уровня: legacy `api_server.py` (монолит, 1365 строк) и современный `core_api/` (domain-driven: agent/auth/ingestion/memory/system/users, api/v1 router). python-multipart 0.0.6 для multipart/form-data (audio upload).
- **БД:** PostgreSQL 16 + pgvector (образ `ankane/pgvector`), embeddings 1536-мерные.
- **ORM/миграции:** SQLAlchemy 2.0.25 + Alembic 1.13.1 + psycopg 3.3.2 (binary+pool).
- **ASR:** DeepInfra Whisper (`transcribe_client/deepinfra.py`, `tools/di_worker`) + OpenRouter Gemini (`transcribe_client/openrouter.py`, chunked). Также адаптеры: `gpu.py`, `local.py`, `di_worker.py`, `stub.py`. Транскрипция оркестрируется `transkribator_modules/transcribe/transcriber_v4.py` (1987 строк, монолит).
- **LLM:** OpenAI SDK 1.14.0 (через OpenRouter). Промпты в `prompts_catalog.json`.
- **Поиск:** pgvector + redis 5.0.4 + BM25/TF-IDF (`transkribator_modules/search/`: service, reranker, embeddings, index).
- **Платежи:** YooKassa 3.0 (optional, `requirements/payments.txt`), Telegram Stars.
- **Медиа-источники:** Telegram, YouTube (yt-dlp 2025.9.26), Google Drive (gdown 5.1.0), Mega (mega.py 1.0.8), Dropbox, Yandex.Disk, VK, прямые ссылки.
- **Google интеграции:** google-api-python-client 2.119.0 (Sheets/Drive/Calendar/Docs/OAuth), google-auth 2.28.0.
- **Деплой:** Docker Compose. Эталонный файл — `docker-compose.bot-v2.yml` (сервисы: postgres, bot, worker, core-api; telegram-bot-api в профиле `donotstart` — заменён на native процесс в VPN namespace). 7 альтернативных compose-файлов в корне (`.disabled`/legacy/dev). 11 Dockerfile-вариантов.
- **Тесты:** pytest 8.1.1 + pytest-asyncio (asyncio_mode=auto), testpaths=tests. 15 тест-файлов в `tests/`.
- **Frontend/miniapp:** `miniapp/` + `miniapp_dist/` (status mixed — нужно выяснить, какая сборка отдаётся в проде).
- **Build/test команды:**
  - `make test` → `pytest -q` (или Docker: `docker run --rm -v "$(PWD)":/work python:3.11-slim ... pytest -q`)
  - `make docker-test` → `./scripts/docker-test.sh`
  - `make install` → `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`
  - `make migrate` → `alembic upgrade head`
  - `make revision NAME=msg` → `alembic revision --autogenerate -m "msg"`
  - `make start-docker` → `./scripts/docker-start.sh` (docker-compose bot-v2)
  - `make smoke` → `./scripts/smoke_test_pipeline.sh` (требует запущенный compose)
  - `make backup-postgres` → `docker compose exec -T postgres pg_dump ...`

## Architecture

### Directory layout (канонический верхний уровень)

```
cyberkitty_modular.py          # thin entrypoint → transkribator_modules/main.py
api_server.py                  # legacy FastAPI монолит (1365 строк) — core_api заменяет
job_worker.py                  # воркер фоновых задач (399 строк), сервис worker в compose
transkribator_modules/         # основной пакет (core)
  bot/                         # commands, handlers (2262 строк), callbacks, payments, processing_guard, yukassa_webhook, update_dedupe, logging_utils
  api/                         # miniapp API (legacy, перекрыт core_api)
  jobs/                        # queue, pipeline, stages, services, progress, plan_reminders, service_factory, bootstrap, media, overrides
  db/                          # database, models, user_service
  agent/                       # dialog.py (прототип decision layer, 190 строк)
  transcribe/                  # transcriber_v4.py (основной ASR + LLM форматирование, 1987 строк)
  search/                      # service, reranker, embeddings, index
  google_api/                  # Google Sheets/Drive/Calendar/Docs интеграции
  audio/                       # extractor (ffmpeg/аудиоподготовка)
  beta/                        # entrypoint (884 строки), handlers/{callbacks,command_flow,content_flow,entrypoint}, router, content_processor (stub)
  payments/                    # yukassa, monitoring
  utils/                       # large_file_downloader
  config.py, events_registry.py, main.py, manual_mode.py, note_utils.py, wai_flow.py
transcribe_client/             # адаптеры ASR: deepinfra, openrouter, di_worker, gpu, local, stub
core_api/                      # современный domain-driven API (FastAPI)
  api/v1/                      # agent, auth, dependencies, ingest, internal_bot, memory, payments, system, transcribe
  domains/                     # agent/{core,persistence,session_store}, ingestion/media_service, memory/search_service
  schemes/                     # auth, system
  main.py
tools/                         # di_worker (контейнерный ASR с WireGuard egress), audio_prep, whisper_service, integration_smoke, mock_whisper_server
alembic/                       # миграции БД
docs/                          # adr/ADR-2026-001, INVENTORY.md, developer-setup, templates
tests/                         # 15 pytest-файлов
```

### Key components / data flow (по ADR-2026-001 и ARCHITECTURE_AGENT_FIRST.md)

1. **Bot handler** (`transkribator_modules/bot/handlers.py`) — принимает медиа, НЕ блокирует. Вызывает `enqueue_media_job()` → немедленный ответ пользователю «✅ File accepted!».
2. **Queue** (`transkribator_modules/jobs/queue.py`) — Postgres-таблица `processing_jobs` (durable, status/progress/error, retry). Семантика транзакций.
3. **Job Worker** (`job_worker.py`, `transkribator_modules/jobs/pipeline.py` + `stages.py`) — асинхронно dequeue → download media → transcribe → format → finalize note → deliver → cleanup → update DB.
4. **Core Transcriber** (`transcriber_v4.py` + `transcribe_client/` адаптеры) — ASR: OpenRouter Gemini (chunked, auto-chunk >20MB), DeepInfra Whisper, local whisper, GPU, stub. OpenRouter использует multipart/form-data (fix #6).
5. **Processing Module** (`transkribator_modules/beta/content_processor.py` — STUB) — должен: chunking, prompt orchestration (prompts_catalog.json), scoring. Пока заглушка.
6. **Agent Orchestrator** (`transkribator_modules/agent/dialog.py` — прототип, 190 строк) — LLM-based controller + rule engine. Требуется decision policy + audit trail.
7. **LTM** (`transkribator_modules/search/` + core_api/domains/memory/) — pgvector embeddings 1536, similarity search. Упомянут, нужна интеграция/ingestion pipeline.
8. **Core API** (`core_api/`) — domain-driven FastAPI: agent, auth, ingestion (media_service), memory (search_service), system, users, internal_bot, payments.
9. **Telegram Bot API** — native процесс в VPN namespace (WireGuard, 10.8.0.2/24), заменяет контейнерный telegram-bot-api.

### Contracts (из ARCHITECTURE_AGENT_FIRST.md, short)
- Job: `{id, device_id, file_uri, privacy_profile, prefs, created_at}`
- TranscriptionResult: `{job_id, segments[], text, model, meta}`
- MemoryEntry: `{id, embedding, text, source_refs, tags, created_at}`
- AgentAction: `{type, payload, confidence, rationale, created_at}`

### Технический долг (по docs/INVENTORY.md, приоритеты H/M/L)

КРИТИЧНО (H):
- Вложенный дублирующий пакет `transkribator_modules/transkribator_modules/` — существовал в git-истории (подтверждено: `git log --all --diff-filter=A` показывает добавление `transkribator_modules/transkribator_modules/bot/handlers.py` и `.../transcribe/transcriber_v4.py`). В текущем worktree (commit dfb2465) уже ОТСУТСТВУЕТ — удалён. Риск остаточных импортов требует проверки.
- `handlers.py` в корне — legacy entrypoint, дублирует `transkribator_modules/bot/handlers.py`. Проверить использование.
- `transcriber_v4.py` (1987 строк) — монолит: ASR + chunking + форматирование + закомментированная DeepInfra-логика. Разделить на функции.
- `format_transcript_with_llm` — нет защиты от артефактов («та-та-та…»), нет пост-валидации (повторы, искажение длины/содержания, факты/даты).
- Bot handlers смешаны старые/новые подходы (AGENT_FIRST, FEATURE_BETA_MODE) — разбить на подмодули (video/audio/text/agent).

СРЕДНЕЕ (M):
- 7 docker-compose файлов, 11 Dockerfile — зафиксировать один эталонный prod, остальные пометить legacy/dev.
- `job_worker.py` — проинвентаризировать job_type, отключить неиспользуемые.
- `api_server.py` — мёртвые эндпоинты, пересечение логики с ботом. core_api частично решает.
- DB: таблицы users/transcriptions/notes — поля под старые фичи (DeepInfra, старые планы).
- Логи не стандартизированы — нет user_id/media_id/job_id в одном сообщении (ADR-2026-001 требует).
- Beta-ветки — описать реальное использование, отключить мёртвые.
- Тесты не покрывают длинные транскрипции с артефактами и искажением фактов.

### Состояние очереди задач
- 0 открытых задач в control-room, 0 raw записей в памяти.
- Система готова к новому циклу разработки.

### История разработки (SESSION_COMPLETION_SUMMARY.md)
- 22 major tasks (TASK-00..TASK-22) за 11 месяцев (Mar 2025 — Feb 2026).
- ~2,470 часов, 1 разработчик.
- TASK-00..11: Original development phases (~1,870h) — completed.
- TASK-12..22: Queue/Worker migration phase (~600h) — in progress.

## Acceptance Criteria

Эпик — исследование и документирование. Acceptance criteria для deliverable (комплексное описание проекта в RESEARCH.md):

1. **Stack зафиксирован полностью** — все версии зависимостей извлечены из `requirements/*.txt` (base/bot/api/payments), не placeholder. Включая: Python 3.10, FastAPI 0.108.0, python-telegram-bot 22.1, SQLAlchemy 2.0.25, Alembic 1.13.1, psycopg 3.3.2, pgvector 0.2.4, redis 5.0.4, OpenAI 1.14.0, yt-dlp 2025.9.26, gdown 5.1.0, mega.py 1.0.8, yookassa 3.0, google-api-python-client 2.119.0, pytest 8.1.1.
2. **Архитектура описана с привязкой к файлам** — каждый компонент (Device Agent, Sync Gateway, File Preparer, Queue+Workers, Core Transcriber, Processing Module, Agent Orchestrator, LTM, API/Bot/UI, Governance) сопоставлен с реальными файлами/директориями в репозитории (по mapping в ARCHITECTURE_AGENT_FIRST.md + фактическая структура `transkribator_modules/`, `core_api/`, `transcribe_client/`, `tools/`).
3. **Технический долг зафиксирован по приоритетам** — каждый пункт из docs/INVENTORY.md включён с приоритетом (H/M/L), статусом (core/legacy/dup/remove/mixed) и planned actions. КРИТИЧЕСКИЙ пункт (вложенный дублирующий пакет) проверен фактически: подтверждено наличие в git-истории и отсутствие в текущем worktree.
4. **Build/test команды актуальны** — извлечены из Makefile, включая `make test`, `make docker-test`, `make install`, `make migrate`, `make smoke`, `make backup-postgres`.
5. **Стек деплоя зафиксирован** — docker-compose.bot-v2.yml как эталон, перечень сервисов (postgres, bot, worker, core-api, telegram-bot-api в профиле donotstart), альтернативные compose-файлы перечислены и помечены как legacy/dev.
6. **Приоритетные пробелы MVP зафиксированы** — 5 пунктов из ARCHITECTURE_AGENT_FIRST.md (контракты OpenAPI, transcribe_client adapter, Processing Module, Agent Orchestrator, LTM) с текущим статусом каждого (stub/прототип/частично).
7. **Engineering notes содержат конкретные constraints** — Python 3.10 EOL, `from __future__ import annotations` требование, OpenRouter multipart/form-data (fix #6), auto-chunk >20MB, WireGuard VPN для telegram-bot-api, pgvector embeddings 1536-мерные.

## Engineering Notes

- **Python 3.10 constraint:** EOL Oct 2026. Код уже использует `from __future__ import annotations` для PEP 604 union syntax (int | None) на 3.10. Миграция на 3.11+ запланирована. `make test` запускает pytest через `python:3.11-slim` Docker образ — тесты выполняются на 3.11, не на 3.10.
- **OpenRouter audio:** multipart/form-data обязательно (commit 623a64d, fix #6). Auto-chunking для файлов >20MB (commit 0367180). Retry на 502 transient errors (commit d89a895).
- **Video pipeline:** PCM codec несовместим с .ogg container (commit c602753). Детект video streams через ffprobe для .media файлов (commit 27292e9).
- **Telegram Bot API:** запускается как native процесс в VPN namespace (WireGuard, 10.8.0.2/24, внешний IP 185.125.216.254), НЕ в Docker. Контейнерный telegram-bot-api в compose помечен `profiles: [donotstart]`. Скрипты: `run-telegram-bot-api-native-vpn.sh`, `run-telegram-vpn-proxy.sh`.
- **DB/queue:** Postgres-таблица `processing_jobs` (ADR-2026-001). Бот НЕ блокирует на `await transcribe_audio()` — использует `enqueue_media_job()`. Миграции через Alembic, в core-api контейнере alembic файлы копируются и миграции запускаются на startup (commit f8fb184).
- **pgvector:** embeddings 1536-мерные (соответствие OpenAI text-embedding-ada-002 / OpenRouter). Образ `ankane/pgvector`.
- **core_api vs api_server.py:** core_api — domain-driven (api/v1 router: agent/auth/ingest/internal_bot/memory/payments/system/transcribe). api_server.py — legacy монолит (1365 строк). При разработке новых эндпоинтов использовать core_api, не api_server.py.
- **transcribe_client:** 6 адаптеров (deepinfra, openrouter, di_worker, gpu, local, stub). Унификация вызовов ASR — приоритетный пробел MVP #2. `TRANSCRIBE_DEFAULT_MODE=deepinfra` в compose.
- **content_processor.py — STUB:** Processing Module не реализован. `transkribator_modules/beta/content_processor.py` помечен stub. Реальная логика `_build_summary_and_tags` существует отдельно. Приоритет MVP #3.
- **agent/dialog.py — ПРОТОТИП:** Agent Orchestrator не реализован. 190 строк, промпты зашиты в код. Требуется decision policy + audit trail. Приоритет MVP #4.
- **LTM:** pgvector упомянут, search/ модуль есть, но ingestion pipeline и миграции для memory entries не завершены. Приоритет MVP #5.
- **Вложенный дублирующий пакет:** `transkribator_modules/transkribator_modules/` существовал в git-истории (добавлен в коммитах, виден через `git log --all --diff-filter=A`). В текущем worktree (commit dfb2465) УДАЛЁН — директория отсутствует. Однако при рефакторинге импортов необходимо проверить, что ни один модуль не ссылается на вложенный путь (риск silent legacy import).
- **Логи:** не стандартизированы. ADR-2026-001 требует `job_id`, `user_id`, `media_id` в одном сообщении для traceability. Текущее состояние — ключевые события разнесены, трудно собирать полную трассу.
- **Тесты:** pytest.ini: `testpaths=tests`, `asyncio_mode=auto`. 15 файлов в tests/. Не покрывают: длинные транскрипции с артефактами, искажение фактов/дат в LLM-формате, регресс на повторы токенов.
- **Файлы в корне (untracked):** `openapi.yaml`, `branch_protection.json`, `deploy_proxy.sh`, `deploy_proxy_sync.sh`, `docs/GITHUB_ACTIONS_SETUP.md`, `test_dl.py`, `test_dl2.py` — не в git (untracked). `openapi.yaml` — стартовая точка для контрактов MVP #1.
- **Незакоммиченные изменения (в реальном репо):** `bot/handlers.py` (modified) — в worktree чисто (snapshot), но в `/home/cyberkitty/Projects/Cyberkitty119` есть изменения.
- **Docker:** `.dockerignore` оптимизирован — исключает `.venv*` (экономия 1.7GB build context). 4prod-сервиса: bot, worker, core-api, postgres. Volumes: media, data, core_api, transkribator_modules, transcribe_client, audio, telegram-bot-api-data (ro).
- **Git:** branch protection настроена (branch_protection.json untracked), GitHub Actions CI есть (.github/), pre-commit config (.pre-commit-config.yaml). Base commit worktree: dfb24655342d4cb416a16d305e69ba8e1bca4e84.
- **Не трогать без необходимости:** `.env` (секреты: BOT_TOKEN, DEEPINFRA_API_KEY, TELEGRAM_API_ID/HASH, POSTGRES_PASSWORD, OpenRouter keys, YooKassa, Google OAuth client_secret). `client_secret_*.json` в реальном репо — Google OAuth credentials.