# RESEARCH.md

## Stack

- **Язык:** Python 3.10 (EOL Oct 2026 — в System Status отмечен план миграции на 3.11+). В коде уже используется `from __future__ import annotations` для совместимости с 3.10 type hints (PEP 604 union syntax `int | None`).
- **Бот:** python-telegram-bot 22.1 (с job-queue), entrypoint `cyberkitty_modular.py` → `transkribator_modules/main.py` → `transkribator_modules/bot/handlers.py` (2262 строки).
- **API:** FastAPI 0.108.0 + uvicorn 0.25.0 + pydantic 2.5.3. Два уровня: legacy `api_server.py` (монолит, 1365 строк) и современный `core_api/` (domain-driven: domains/{agent,auth,ingestion,memory,system,users}, api/v1 router: agent/auth/dependencies/ingest/internal_bot/memory/payments/system/transcribe). python-multipart 0.0.6 для multipart/form-data (audio upload).
- **БД:** PostgreSQL 16 + pgvector 0.2.4 (образ `ankane/pgvector`), embeddings 1536-мерные.
- **ORM/миграции:** SQLAlchemy 2.0.25 + Alembic 1.13.1 + psycopg 3.3.2 (binary+pool в requirements/api.txt).
- **ASR:** DeepInfra Whisper (`transcribe_client/deepinfra.py`, `tools/di_worker`) + OpenRouter Gemini (`transcribe_client/openrouter.py`, chunked). Также адаптеры: `gpu.py`, `local.py`, `di_worker.py`, `stub.py` — всего 6 адаптеров в `transcribe_client/`. Транскрипция оркестрируется `transkribator_modules/transcribe/transcriber_v4.py` (1987 строк, монолит).
- **LLM:** OpenAI SDK 1.14.0 (через OpenRouter). Промпты в `prompts_catalog.json`.
- **Поиск:** pgvector + redis 5.0.4 + BM25/TF-IDF (`transkribator_modules/search/`: service, reranker, embeddings, index).
- **Платежи:** YooKassa 3.0.0 (optional, `requirements/payments.txt`), Telegram Stars.
- **Медиа-источники:** Telegram, YouTube (yt-dlp 2025.9.26), Google Drive (gdown 5.1.0), Mega (mega.py 1.0.8), Dropbox, Yandex.Disk, VK, прямые ссылки.
- **Google интеграции:** google-api-python-client 2.119.0 (Sheets/Drive/Calendar/Docs/OAuth), google-auth 2.28.0.
- **Деплой:** Docker Compose. Эталонный файл — `docker-compose.bot-v2.yml` (сервисы: postgres, bot, worker, core-api; telegram-bot-api в профиле `donotstart` — заменён на native процесс в VPN namespace). 17 альтернативных compose-файлов в корне (11 `.disabled`/legacy, 6 активных non-bot-v2: gpu-worker.example, max, mock-whisper, remote, simple-bot, test-bot). 11 Dockerfile-вариантов.
- **Тесты:** pytest 8.1.1 + pytest-asyncio (asyncio_mode=auto, testpaths=tests). 15 тест-файлов в `tests/` (14 `test_*.py` + 1 `run_tests_no_pytest.py`).
- **Frontend/miniapp:** `miniapp/` (Vite-based, src/ + public/) + `miniapp_dist/` (assets/, index.html, version.txt, vite.svg — pre-built). Status mixed — нужно выяснить, какая сборка отдаётся в проде.
- **Build/test команды (из Makefile):**
  - `make test` → **`pytest -q`** (локально). ВНИМАНИЕ: Makefile содержит ДВА `test:` target (строка 7 — Docker `python:3.11-slim`, строка 160 — локальный `pytest -q`). Второй перекрывает первый; `make test` запускает локальный pytest, а НЕ Docker. `make -n test` подтверждает: `pytest -q`.
  - `make docker-test` → `./scripts/docker-test.sh` (требует `.env`)
  - `make install` → `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`
  - `make migrate` → `alembic upgrade head`
  - `make revision NAME=msg` → `alembic revision --autogenerate -m "msg"`
  - `make start-docker` → `./scripts/docker-start.sh` (docker-compose bot-v2)
  - `make smoke` → `./scripts/smoke_test_pipeline.sh` (требует запущенный compose)
  - `make backup-postgres` → `docker compose exec -T postgres pg_dump ...`
  - `make docs-validate` → `./.github/scripts/run_metadata_validator_docker.sh`

## Architecture

### Directory layout (канонический верхний уровень)

```
cyberkitty_modular.py          # thin entrypoint → transkribator_modules/main.py
api_server.py                  # legacy FastAPI монолит (1365 строк) — core_api заменяет
job_worker.py                  # воркер фоновых задач (399 строк), сервис worker в compose
bot/                           # ОТДЕЛЬНЫЙ root-level пакет (НЕ transkribator_modules/bot/)
  handlers.py (1287 строк)    # "чистый перезапуск" бота, импортирует bot.config/db/core_api_client
  main.py, config.py, db.py, core_api_client.py, jobs.py, minimal.py, hello.py
transkribator_modules/         # основной пакет (core)
  bot/                         # commands, handlers (2262 строки), callbacks, payments, processing_guard, yukassa_webhook, update_dedupe, logging_utils
  api/                         # miniapp API (legacy, перекрыт core_api)
  jobs/                        # queue, pipeline, stages, services, progress, plan_reminders, service_factory, bootstrap, media, overrides
  db/                          # database, models, user_service
  agent/                       # dialog.py (прототип decision layer, 190 строк)
  transcribe/                  # transcriber_v4.py (основной ASR + LLM форматирование, 1987 строк)
  search/                      # service, reranker, embeddings, index
  google_api/                  # Google Sheets/Drive/Calendar/Docs интеграции
  audio/                       # extractor (ffmpeg/аудиоподготовка)
  beta/                        # entrypoint.py (884 строки), router.py (449 строк), handlers/{callbacks,command_flow,content_flow,entrypoint}, __init__.py
  payments/                    # yukassa, monitoring
  utils/                       # large_file_downloader
  config.py, events_registry.py, main.py, manual_mode.py, note_utils.py, wai_flow.py
transcribe_client/             # адаптеры ASR: deepinfra, openrouter, di_worker, gpu, local, stub (6 адаптеров)
core_api/                      # современный domain-driven API (FastAPI)
  api/v1/                      # agent, auth, dependencies, ingest, internal_bot, memory, payments, system, transcribe
  domains/                     # agent/{core (content_processor.py 366 строк, agent_runtime, command_processor, llm, prompts, ...)}, auth, ingestion/media_service, memory/search_service, system, users
  schemes/                     # auth, system
  main.py
tools/                         # di_worker (контейнерный ASR с WireGuard egress), audio_prep, whisper_service, integration_smoke, mock_whisper_server, transcribe_vpnspace.sh
alembic/                       # миграции БД
docs/                          # adr/ADR-2026-001-queue-workers.md, INVENTORY.md, templates
tests/                         # 15 pytest-файлов
```

### Key components / data flow (по ADR-2026-001 и ARCHITECTURE_AGENT_FIRST.md)

1. **Bot handler** (`transkribator_modules/bot/handlers.py`, 2262 строки) — принимает медиа, НЕ блокирует. Вызывает `enqueue_media_job()` → немедленный ответ пользователю «✅ File accepted!».
2. **Queue** (`transkribator_modules/jobs/queue.py`) — Postgres-таблица `processing_jobs` (durable, status/progress/error, retry). Семантика транзакций.
3. **Job Worker** (`job_worker.py` 399 строк, `transkribator_modules/jobs/pipeline.py` + `stages.py`) — асинхронно dequeue → download media → transcribe → format → finalize note → deliver → cleanup → update DB.
4. **Core Transcriber** (`transcriber_v4.py` 1987 строк + `transcribe_client/` адаптеры) — ASR: OpenRouter Gemini (chunked, auto-chunk >20MB), DeepInfra Whisper, local whisper, GPU, stub. OpenRouter использует multipart/form-data (fix #6, commit 623a64d).
5. **Processing Module** (`core_api/domains/agent/core/content_processor.py`, 366 строк) — ПЕРЕМЕЩЁН из `transkribator_modules/beta/content_processor.py` (commit 3e469c3). Содержит `_unwrap_json_content`, summary/tags generation через OpenRouter. Архитектурный документ ARCHITECTURE_AGENT_FIRST.md всё ещё ссылается на старый путь `beta/content_processor.py` — устаревшая ссылка.
6. **Agent Orchestrator** (`transkribator_modules/agent/dialog.py` — прототип, 190 строк) — LLM-based controller + rule engine. Требуется decision policy + audit trail.
7. **LTM** (`transkribator_modules/search/` + `core_api/domains/memory/`) — pgvector embeddings 1536, similarity search. Упомянут, нужна интеграция/ingestion pipeline.
8. **Core API** (`core_api/`) — domain-driven FastAPI: agent, auth, ingestion (media_service), memory (search_service), system, users, internal_bot, payments.
9. **Telegram Bot API** — native процесс в VPN namespace (WireGuard, 10.8.0.2/24, внешний IP 185.125.216.254), заменяет контейнерный telegram-bot-api.

### Root-level `bot/` package (отдельный от `transkribator_modules/bot/`)

В корне репозитория существует отдельный пакет `bot/` (НЕ `transkribator_modules/bot/`):
- `bot/handlers.py` (1287 строк) — «чистый перезапуск» бота, описанный как новый подход
- `bot/main.py`, `bot/config.py`, `bot/db.py`, `bot/core_api_client.py`, `bot/jobs.py`, `bot/minimal.py`
- Импортируется только из `bot/main.py` и нескольких patch-скриптов (`patch_handlers_stage3.py`, `max_bot/`, `insert_qa_callback.py`)
- Не является основным entrypoint продакшена (продакшен использует `transkribator_modules/bot/handlers.py` через `cyberkitty_modular.py`)
- **ВНИМАНИЕ:** INVENTORY.md упоминает `handlers.py` в корне как legacy — фактически корневого `handlers.py` НЕТ, но есть `bot/handlers.py` (отдельный пакет). Корневой `handlers.py` либо был удалён, либо никогда не существовал в текущем worktree.

### Contracts (из ARCHITECTURE_AGENT_FIRST.md, short)
- Job: `{id, device_id, file_uri, privacy_profile, prefs, created_at}`
- TranscriptionResult: `{job_id, segments[], text, model, meta}`
- MemoryEntry: `{id, embedding, text, source_refs, tags, created_at}`
- AgentAction: `{type, payload, confidence, rationale, created_at}`

### Технический долг (по docs/INVENTORY.md, приоритеты H/M/L)

КРИТИЧНО (H):
- Вложенный дублирующий пакет `transkribator_modules/transkribator_modules/` — существовал в git-истории (подтверждено: `git log --all --diff-filter=A` показывает добавление). В текущем worktree (commit dfb2465) ОТСУТСТВУЕТ — удалён. Риск остаточных импортов требует проверки.
- `transcriber_v4.py` (1987 строк) — монолит: ASR + chunking + форматирование + закомментированная DeepInfra-логика. Разделить на функции.
- `format_transcript_with_llm` — нет защиты от артефактов («та-та-та…»), нет пост-валидации (повторы, искажение длины/содержания, факты/даты).
- Bot handlers (`transkribator_modules/bot/handlers.py`, 2262 строки) смешаны старые/новые подходы (AGENT_FIRST, FEATURE_BETA_MODE) — разбить на подмодули (video/audio/text/agent).
- Summary quality: потенциальная подмена фактов в `notes.summary` (пример с датой 1 февраля) — ужесточить промпты, добавить пост-валидацию.

СРЕДНЕЕ (M):
- 18 docker-compose файлов (1 эталонный bot-v2 + 17 альтернатив), 11 Dockerfile — зафиксировать один эталонный prod, остальные пометить legacy/dev.
- `job_worker.py` — проинвентаризировать job_type, отключить неиспользуемые.
- `api_server.py` — мёртвые эндпоинты, пересечение логики с ботом. core_api частично решает.
- DB: таблицы users/transcriptions/notes — поля под старые фичи (DeepInfra, старые планы).
- Логи не стандартизированы — нет user_id/media_id/job_id в одном сообщении (ADR-2026-001 требует).
- Beta-ветки — описать реальное использование, отключить мёртвые.
- `transkribator_modules/agent/dialog.py` — промпты зашиты в код, вынести в отдельный модуль.
- Тесты не покрывают длинные транскрипции с артефактами и искажением фактов.

НИЗКОЕ (L):
- `miniapp/` + `miniapp_dist/` — выяснить, какая сборка реально отдаётся в проде.
- `setup_and_build.sh`, `deploy*.sh`, `scripts/**` — одноразовые скрипты, описать реальный деплой.

### Известные проблемы (выявлены при исследовании)

1. **Сломанный тест:** `tests/test_content_processor.py` импортирует `from transkribator_modules.beta.content_processor import _unwrap_json_content` — файл перемещён в `core_api/domains/agent/core/content_processor.py` (commit 3e469c3). Импорт сломан: `_unwrap_json_content` больше не доступен по старому пути. Тест не пройдет без исправления импорта.
2. **Makefile conflict:** два `test:` target (строки 7 и 160). Второй перекрывает первый. `make test` запускает `pytest -q` локально, а не в Docker. Make выдаёт warning: `overriding recipe for target 'test'`.
3. **`openapi.yaml` отсутствует** в текущем worktree — упоминался в задаче как untracked, но в worktree (commit a4b499e) его нет. Не является стартовой точкой для MVP #1 в этом состоянии репозитория.

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

1. **Stack зафиксирован полностью** — все версии зависимостей извлечены из `requirements/*.txt` (base/bot/api/payments), не placeholder. Включая: Python 3.10, FastAPI 0.108.0, python-telegram-bot 22.1, SQLAlchemy 2.0.25, Alembic 1.13.1, psycopg 3.3.2, pgvector 0.2.4, redis 5.0.4, OpenAI 1.14.0, yt-dlp 2025.9.26, gdown 5.1.0, mega.py 1.0.8, yookassa 3.0.0, google-api-python-client 2.119.0, pytest 8.1.1, python-multipart 0.0.6, pydantic 2.5.3, uvicorn 0.25.0, google-auth 2.28.0, numpy 1.26.4, cryptography 42.0.5.
2. **Архитектура описана с привязкой к файлам** — каждый компонент (Device Agent, Sync Gateway, File Preparer, Queue+Workers, Core Transcriber, Processing Module, Agent Orchestrator, LTM, API/Bot/UI, Governance) сопоставлен с реальными файлами/директориями в репозитории (по mapping в ARCHITECTURE_AGENT_FIRST.md + фактическая структура `transkribator_modules/`, `core_api/`, `transcribe_client/`, `tools/`).
3. **Технический долг зафиксирован по приоритетам** — каждый пункт из docs/INVENTORY.md включён с приоритетом (H/M/L), статусом (core/legacy/dup/remove/mixed) и planned actions. КРИТИЧЕСКИЙ пункт (вложенный дублирующий пакет) проверен фактически: подтверждено наличие в git-истории и отсутствие в текущем worktree.
4. **Build/test команды актуальны** — извлечены из Makefile, включая `make test` (с указанием конфликта двух target'ов), `make docker-test`, `make install`, `make migrate`, `make smoke`, `make backup-postgres`, `make docs-validate`.
5. **Стек деплоя зафиксирован** — docker-compose.bot-v2.yml как эталон, перечень сервисов (postgres, bot, worker, core-api, telegram-bot-api в профиле donotstart), альтернативные compose-файлы перечислены (18 total: 1 эталон + 11 disabled + 6 active non-эталон) и помечены как legacy/dev.
6. **Приоритетные пробелы MVP зафиксированы** — 5 пунктов из ARCHITECTURE_AGENT_FIRST.md (контракты OpenAPI, transcribe_client adapter, Processing Module, Agent Orchestrator, LTM) с текущим статусом каждого (stub/прототип/частично) и указанием актуального пути файла (content_processor.py перемещён в core_api).
7. **Engineering notes содержат конкретные constraints** — Python 3.10 EOL, `from __future__ import annotations` требование, OpenRouter multipart/form-data (fix #6), auto-chunk >20MB, WireGuard VPN для telegram-bot-api, pgvector embeddings 1536-мерные, сломанный тест test_content_processor.py, конфликт Makefile test target.

## Engineering Notes

- **Python 3.10 constraint:** EOL Oct 2026. Код уже использует `from __future__ import annotations` для PEP 604 union syntax (`int | None`) на 3.10. Миграция на 3.11+ запланирована. ВАЖНО: `make test` запускает `pytest -q` локально (на установленном Python), а НЕ через Docker `python:3.11-slim` — Makefile содержит два `test:` target, второй (строка 160) перекрывает первый (строка 7).
- **OpenRouter audio:** multipart/form-data обязательно (commit 623a64d, fix #6). Auto-chunking для файлов >20MB (commit 0367180). Retry на 502 transient errors (commit d89a895).
- **Video pipeline:** PCM codec несовместим с .ogg container (commit c602753). Детект video streams через ffprobe для .media файлов (commit 27292e9).
- **Telegram Bot API:** запускается как native процесс в VPN namespace (WireGuard, 10.8.0.2/24, внешний IP 185.125.216.254), НЕ в Docker. Контейнерный telegram-bot-api в compose помечен `profiles: [donotstart]`. Скрипты: `run-telegram-bot-api-native-vpn.sh`, `run-telegram-vpn-proxy.sh`.
- **DB/queue:** Postgres-таблица `processing_jobs` (ADR-2026-001). Бот НЕ блокирует на `await transcribe_audio()` — использует `enqueue_media_job()`. Миграции через Alembic, в core-api контейнере alembic файлы копируются и миграции запускаются на startup (commit f8fb184).
- **pgvector:** embeddings 1536-мерные (соответствие OpenAI text-embedding-ada-002 / OpenRouter). Образ `ankane/pgvector`.
- **core_api vs api_server.py:** core_api — domain-driven (api/v1 router: agent/auth/ingest/internal_bot/memory/payments/system/transcribe). api_server.py — legacy монолит (1365 строк). При разработке новых эндпоинтов использовать core_api, не api_server.py.
- **transcribe_client:** 6 адаптеров (deepinfra, openrouter, di_worker, gpu, local, stub). Унификация вызовов ASR — приоритетный пробел MVP #2. `TRANSCRIBE_DEFAULT_MODE=deepinfra` в compose.
- **content_processor.py — ПЕРЕМЕЩЁН:** Processing Module находится в `core_api/domains/agent/core/content_processor.py` (366 строк), НЕ в `transkribator_modules/beta/content_processor.py` (перемещён в commit 3e469c3). ARCHITECTURE_AGENT_FIRST.md всё ещё ссылается на старый путь — устаревшая ссылка. Приоритет MVP #3.
- **Сломанный тест:** `tests/test_content_processor.py` импортирует `from transkribator_modules.beta.content_processor import _unwrap_json_content` — файл перемещён, импорт сломан. Функция `_unwrap_json_content` теперь в `core_api/domains/agent/core/content_processor.py` (строка 76). Тест не пройдёт без исправления импорта.
- **agent/dialog.py — ПРОТОТИП:** Agent Orchestrator не реализован. 190 строк, промпты зашиты в код. Требуется decision policy + audit trail. Приоритет MVP #4.
- **LTM:** pgvector упомянут, search/ модуль есть, но ingestion pipeline и миграции для memory entries не завершены. Приоритет MVP #5.
- **Вложенный дублирующий пакет:** `transkribator_modules/transkribator_modules/` существовал в git-истории (добавлен в коммитах, виден через `git log --all --diff-filter=A`). В текущем worktree (commit dfb2465) УДАЛЁН — директория отсутствует. Однако при рефакторинге импортов необходимо проверить, что ни один модуль не ссылается на вложенный путь (риск silent legacy import).
- **Root `bot/` пакет:** существует отдельный от `transkribator_modules/bot/` пакет `bot/` в корне репозитория (handlers.py 1287 строк, main.py, config.py, db.py, core_api_client.py). Не является основным entrypoint продакшена. Используется только из `bot/main.py` и patch-скриптов.
- **Логи:** не стандартизированы. ADR-2026-001 требует `job_id`, `user_id`, `media_id` в одном сообщении для traceability. Текущее состояние — ключевые события разнесены, трудно собирать полную трассу.
- **Тесты:** pytest.ini: `testpaths=tests`, `asyncio_mode=auto`, `python_files=test_*.py`. 15 файлов в tests/. Не покрывают: длинные транскрипции с артефактами, искажение фактов/дат в LLM-формате, регресс на повторы токенов. Один тест сломан (test_content_processor.py — см. выше).
- **Файлы в корне (untracked в реальном репо, отсутствуют в worktree):** `openapi.yaml`, `branch_protection.json`, `deploy_proxy.sh`, `deploy_proxy_sync.sh` — не в git, не в текущем worktree. `docs/GITHUB_ACTIONS_SETUP.md` — единственный untracked файл в текущем worktree.
- **Docker:** `.dockerignore` исключает `audio/`, `*.mp3`, `*.wav`, `*.ogg`, `telegram-bot-api-data/`, `*.mp4`, `*.mkv`, `.venv*`. 4 prod-сервиса: bot, worker, core-api, postgres. Volumes: media, data, core_api, transkribator_modules, transcribe_client, audio, telegram-bot-api-data (ro).
- **Git:** branch protection настроена (branch_protection.json — untracked в реальном репо), GitHub Actions CI есть (`.github/workflows/ci.yml`, `pr-review.yml`), pre-commit config (`.pre-commit-config.yaml`). Base commit worktree: a4b499e. Git warning: `Makefile:161: overriding recipe for target 'test'`.
- **CI/CD:** GitHub Actions workflows — `ci.yml` (основной CI), `pr-review.yml` (review automation). Copilot instructions в `.github/COPILOT_INSTRUCTIONS.md`, Codex instructions в `.github/CODEX_INSTRUCTIONS.md`.
- **Не трогать без необходимости:** `.env` (секреты: BOT_TOKEN, DEEPINFRA_API_KEY, TELEGRAM_API_ID/HASH, POSTGRES_PASSWORD, OpenRouter keys, YooKassa, Google OAuth client_secret). `client_secret_*.json` в реальном репо — Google OAuth credentials.