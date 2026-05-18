# План работ: Миграция на Queue + Worker архитектуру (Фазовая структура)

**Связь с календарным планом НИОКР**: Этот план миграции соответствует **этапам 1–6** календарного плана проекта Cyberkitty119 (месячные интервалы с ноября 2025 по февраль 2026 г.) и охватывает финализацию архитектуры, укрепление агентной логики, развёртывание и валидацию системы.

---

## Общая структура: 4 фазы

- **Фаза 1 (TASK-01–03)**: Infrastructure & Queue Foundation — месяцы 1–3
- **Фаза 2 (TASK-04–06)**: Core Features Integration — месяцы 4–6  
- **Фаза 3 (TASK-07–09)**: Deployment, Testing & CI — месяцы 7–9
- **Фаза 4 (TASK-10–11)**: Finalization & Release — месяцы 10–12

**Суммарная оценка**: ~600 часов  
**Контекст**: Все работы выполняет один разработчик; описания отражают прошедшее время (совершенный вид).

---

## ФАЗА 1: Infrastructure & Queue Foundation (TASK-01–03)
**Период**: Месяцы 1–3 | **Часы**: ~206 ч | **Связь**: Этап 1–2 плана НИОКР (аналитика + базовый прототип)

### Задача 01: Database Architecture & ADR (16 ч)

**Описание**: Определение архитектуры системы обработки задач на основе очереди. Разработка ADR (Architecture Decision Record), проектирование схемы БД для jobs queue, определение контрактов и статусов задач.

**Цель**: Обосновать выбор архитектуры и зафиксировать технический контракт.

**Файлы / Коммиты**:
- `docs/adr/ADR-2026-001-queue-workers.md`
- `alembic/versions/20260125_create_processing_jobs.py`
- `tests/test_job_queue.py` (skeleton)
- Коммит: e2c9d62

**Подзадачи**:
- 12.1 — Обзор существующих решений (RabbitMQ, Celery, простая БД-очередь) выполнен (2 ч)
- 12.2 — Архитектурные решения (в памяти vs БД, синхронизация, контракт jobs table) зафиксированы (4 ч)
- 12.3 — Миграция Alembic написана и протестирована локально (4 ч)
- 12.4 — Runbook миграции и rollback procedure описаны (3 ч)
- 12.5 — Чеклист для PR и smoke test plan подготовлены (3 ч)

**Acceptance Criteria**:
- ADR файл находится в `docs/adr/` и описывает выбор архитектуры
- Миграция БД применяется/откатывается успешно локально (alembic up/down)
- Контракт очереди (таблица jobs: id, status, payload, retry_count, created_at, updated_at) зафиксирован
- Чеклист для PR сформирован

**Риски**: Если потребуется менять историю БД в продакшене, нужна координация с ops.

**Branch/PR**: `feature/queue-adr-migration/task-01-db-adr`

---

### Задача 02: Job Queue Service Layer (80 ч)

**Описание**: Реализация DAO (Data Access Object) для работы с очередью, сервисного слоя с поддержкой retry/backoff логики, comprehensive тестирование.

**Цель**: Создать надёжный сервис для постановки, получения и обновления статуса задач.

**Файлы / Коммиты**:
- `transkribator_modules/jobs/queue.py` (DAO)
- `transkribator_modules/jobs/services.py` (Service layer)
- `transkribator_modules/jobs/service_factory.py`
- `tests/test_job_queue.py` (unit)
- `tests/test_job_queue_db.py` (integration)
- Коммиты: e2c9d62, xxxxxxx

**Подзадачи**:
- 02.1 — Спецификация API DAO (enqueue, claim, update_status, requeue, fail) подготовлена (4 ч)
- 02.2 — DAO с использованием SQLAlchemy реализован с поддержкой транзакций (20 ч)
- 02.3 — Service layer (обёртки, retry policy, exponential backoff) реализован (10 ч)
- 02.4 — Unit тесты для DAO и Service (happy path + error cases) написаны (10 ч)
- 02.5 — Integration smoke тесты (enqueue → worker claims → updates status) реализованы (12 ч)
- 02.6 — Логирование lifecycle и метрики (queue depth, processing time) добавлены (8 ч)
- 02.7 — Рефактор и bugfix по результатам тестирования (16 ч)

**Acceptance Criteria**:
- DAO покрыт unit тестами (happy path + error paths, transaction rollback)
- Smoke тест: enqueue → claim → complete успешно в памяти и на БД
- Нету race conditions при параллельном claim (тест с threading)
- Retry logic работает корректно (тест с mock failure)

**QA**:
```bash
pytest tests/test_job_queue.py::test_enqueue_and_claim -v
pytest tests/test_job_queue_db.py::test_concurrent_claim -v
```

**Branch/PR**: `feature/queue-adr-migration/task-02-queue-service`

---

### Задача 03: Worker Service & Long-Lived Whisper (110 ч)

**Описание**: Реализация long-lived Whisper service в контейнере (FastAPI), интеграция с Worker через очередь, настройка сети (WireGuard при необходимости), Dockerfile и benchmarking.

**Цель**: Создать изолированный worker сервис, способный обрабатывать задачи асинхронно.

**Файлы / Коммиты**:
- `tools/whisper_service.py` (FastAPI application)
- `tools/di_worker/` (Dockerfile, entrypoint, worker script)
- `transcribe_client/di_worker.py` (client)
- `tools/run_prepare_and_transcribe.py` (benchmark)
- Коммиты: 763df02, 411f66c, b4a3591a

**Подзадачи**:
- 03.1 — FastAPI сервис для Whisper с HTTP endpoints реализован (10 ч)
- 03.2 — Dockerfile для Whisper service и worker написаны и оптимизированы (8 ч)
- 03.3 — Entrypoint script: инициализация, health check, graceful shutdown (6 ч)
- 03.4 — Worker script: цикл (get job → call whisper → update status) реализован (16 ч)
- 03.5 — WireGuard / сетевое подключение настроены (при необходимости) (16 ч)
- 03.6 — Unit и E2E тесты для Whisper service добавлены (14 ч)
- 03.7 — Интеграция: error handling, timeout, retry логика (20 ч)
- 03.8 — Benchmark скрипты и документация подготовлены (10 ч)
- 03.9 — Bugfix и оптимизация слоёв Docker (8 ч)

**Acceptance Criteria**:
- Docker образ собирается: `docker build -f tools/di_worker/Dockerfile -t di-worker:latest .`
- На compose: отправляем audio → worker обрабатывает → status updated в БД
- Health check возвращает 200 OK
- Тесты на timeout, graceful shutdown, network failure
- Benchmark: обработка 100 аудиофайлов завершается без deadlock

**QA**:
```bash
docker build -f tools/di_worker/Dockerfile -t di-worker:latest .
docker compose up -d
# отправляем тестовый файл через API
docker logs di-worker | grep "completed"
```

**Риски**: WireGuard / сетевые привилегии требуют админских прав в dev окружении.

**Branch/PR**: `feature/queue-adr-migration/task-03-worker-service`

---

## ФАЗА 2: Core Features Integration (TASK-04–06)
**Период**: Месяцы 4–6 | **Часы**: ~140 ч | **Связь**: Этап 3 плана НИОКР (развитие агентной логики)

### Задача 04: Transcriber Pipeline v4 & LLM Formatting (60 ч)

**Описание**: Интеграция Whisper результатов с LLM-форматированием (OpenRouter), улучшение chunking логики для длинных транскриптов, обработка ошибок и fallback механизмы.

**Цель**: Реализовать end-to-end пайплайн: audio → transcript → formatted output.

**Файлы / Коммиты**:
- `transkribator_modules/transcribe/transcriber_v4.py`
- `transcribe_client/` (client для LLM)
- Коммит: b4a3591a

**Подзадачи**:
- 04.1 — Анализ chunking logic для длинных транскриптов выполнен (5 ч)
- 04.2 — Улучшенный chunking алгоритм реализован (10 ч)
- 04.3 — OpenRouter/OpenAI client с retry и rate limiting настроен (10 ч)
- 04.4 — Fallback логика (если LLM API недоступен) реализована (5 ч)
- 04.5 — Unit тесты для chunking и formatting написаны (10 ч)
- 04.6 — Smoke run на длинном файле выполнен и латентность оценена (10 ч)
- 04.7 — Логирование: размер текста, время обработки, token usage (10 ч)

**Acceptance Criteria**:
- Chunking корректно работает на файлах до 2 часов
- LLM formatting имеет fallback (plain text если API недоступна)
- Unit тесты зелёные
- Логи содержат размер, время, token usage

**QA**:
```bash
pytest tests/test_transcriber_v4.py -v
python tools/run_prepare_and_transcribe.py sample_long.wav
```

**Branch/PR**: `feature/queue-adr-migration/task-04-transcriber-v4`

---

### Задача 05: Bot Handlers Refactor & Deduplication (140 ч)

**Описание**: Полный рефактор bot handlers, введение deduplication logic, processing_guard от двойной обработки, обработка больших файлов, логирование событий для аналитики.

**Цель**: Сделать bot handlers более надёжными и поддерживаемыми; устранить race conditions.

**Файлы / Коммиты**:
- `transkribator_modules/bot/handlers.py`
- `transkribator_modules/bot/callbacks.py`
- `transkribator_modules/bot/commands.py`
- `transkribator_modules/bot/processing_guard.py` (новый)
- `transkribator_modules/bot/update_dedupe.py` (новый)
- `transkribator_modules/bot/logging_utils.py` (новый)
- `transkribator_modules/utils/large_file_downloader.py`
- Коммиты: 14c3fd2, b4a3591a

**Подзадачи**:
- 05.1 — Анализ текущих handlers выполнен; flow diagram составлена (8 ч)
- 05.2 — Реорганизация handlers (группировка по типам) (12 ч)
- 05.3 — processing_guard реализован (проверка: выполняется ли уже обработка) (12 ч)
- 05.4 — update_dedupe: отслеживание обновлений и предотвращение дубликатов (10 ч)
- 05.5 — logging_utils и событийная телеметрия реализованы (24 ч)
- 05.6 — large_file_downloader переписан с resume support (16 ч)
- 05.7 — Smoke тесты для основных user flows (start, upload, create note) (20 ч)
- 05.8 — Bugfix и доработка по результатам тестирования (38 ч)

**Acceptance Criteria**:
- Основные сценарии работают в dev окружении (LOCAL_BOT_API=true)
- processing_guard предотвращает двойную обработку одного update
- dedupe логика корректно отслеживает обновления
- Логи содержат стуктурированные события (user_id, action, status)

**QA**:
```bash
export LOCAL_BOT_API=true
python -m pytest tests/test_bot_handlers.py::test_smoke_workflow -v
# ручное тестирование: /start, upload media, create note
```

**Риски**: Боткод сложный; требует осторожного рефактора с coverage тестами.

**Branch/PR**: `feature/queue-adr-migration/task-05-bot-refactor`

---

### Задача 06: Payment Flow & Monitoring (40 ч)

**Описание**: Интеграция с Yukassa (платёжная система), обработка webhook, sandbox тестирование, мониторинг платёжных событий.

**Цель**: Обеспечить надёжную обработку платежей с fallback и восстановлением.

**Файлы / Коммиты**:
- `transkribator_modules/payments/yukassa.py`
- `transkribator_modules/bot/yukassa_webhook.py`
- `transkribator_modules/payments/monitoring.py`
- Коммиты: b4a3591a

**Подзадачи**:
- 06.1 — Анализ Yukassa API и контракт webhook выполнены (4 ч)
- 06.2 — Webhook handler: проверка подписи, обновление БД (8 ч)
- 06.3 — Мониторинг платёжных событий реализован (8 ч)
- 06.4 — Sandbox flow протестирован (precheckout → success) (12 ч)
- 06.5 — Логирование и мониторинг платежей добавлены (4 ч)
- 06.6 — Документация и runbook для ops подготовлены (4 ч)

**Acceptance Criteria**:
- Sandbox payment scenario проходит (статус меняется в БД)
- Webhook обрабатывает retries (idempotent)
- Логи содержат payment_id, user_id, amount, status

**QA**:
```bash
pytest tests/test_yukassa_integration.py::test_sandbox_payment -v
# ручное: в bot /buy_plan → Yukassa sandbox → webhook updates DB
```

**Branch/PR**: `feature/queue-adr-migration/task-06-payments`

---

## ФАЗА 3: Deployment, Testing & CI (TASK-07–09)
**Период**: Месяцы 7–9 | **Часы**: ~112 ч | **Связь**: Этап 4–5 плана НИОКР (интеграции + валидация)

### Задача 07: Docker & Deployment Configuration (40 ч)

**Описание**: Оптимизация Dockerfile, docker-compose конфигов, удаление секретов из образов, build strategy для CI, документирование deploy процесса.

**Цель**: Ensure reproducible, secure, efficient containerized deployment.

**Файлы / Коммиты**:
- `Dockerfile`, `Dockerfile.api`, `Dockerfile.postgres`, и др.
- `docker-compose*.yml` (prod, staging, dev variants)
- `entrypoint.sh`, `entrypoint-wg.sh`
- `Makefile`
- Коммиты: b4a3591a, f9323456

**Подзадачи**:
- 07.1 — Аудит текущих Dockerfile: выявление secrets, больших слоёв (6 ч)
- 07.2 — Оптимизация Dockerfile (multi-stage, layer caching, size reduction) (10 ч)
- 07.3 — docker-compose configs: prod/staging/dev разделены корректно (8 ч)
- 07.4 — Entrypoint script: graceful shutdown, health checks (6 ч)
- 07.5 — Build strategy для CI: caching, secret handling (6 ч)
- 07.6 — README и quickstart обновлены (4 ч)

**Acceptance Criteria**:
- `docker compose build` успешно завершается
- `docker compose up` поднимает весь стек (API, worker, DB)
- В образах нет копий `.env` или secret переменных
- Build reproducible (одинаковый hash при повторном build без изменений)

**QA**:
```bash
docker compose build
docker compose up -d
curl http://localhost:8000/health
docker compose logs api | grep "started"
```

**Branch/PR**: `feature/queue-adr-migration/task-07-docker-deploy`

---

### Задача 08: Tools, Scripts & Documentation (32 ч)

**Описание**: Стабилизация утилит (minimal_app, di_worker tools, dev scripts), подготовка примеров и документации для разработчиков.

**Цель**: Обеспечить разработчиков удобными инструментами для локальной разработки и тестирования.

**Файлы / Коммиты**:
- `minimal_app/*` (demo app)
- `tools/di_worker/*` (utilities)
- `tools/*.py` (scripts)
- `scripts/*`
- `README.md`, `QUICKSTART.md`
- Коммиты: 6af943b, c750d7e, 763df02

**Подзадачи**:
- 08.1 — minimal_app pipeline проверена и баги исправлены (10 ч)
- 08.2 — di_worker утилиты стабилизированы (6 ч)
- 08.3 — Dev скрипты (setup, run, test, clean) написаны (6 ч)
- 08.4 — README и примеры использования добавлены (10 ч)

**Acceptance Criteria**:
- minimal_app запускается локально: `python minimal_app/main.py`
- Dev скрипты работают: `./scripts/setup.sh`, `./scripts/run_local.sh`
- Документация покрывает основные сценарии разработки

**QA**:
```bash
python minimal_app/main.py --help
./scripts/setup.sh
./scripts/run_local.sh
```

**Branch/PR**: `feature/queue-adr-migration/task-08-tools-docs`

---

### Задача 09: Testing & CI Pipeline (40 ч)

**Описание**: Comprehensive тестирование (unit, integration, smoke), настройка CI pipeline (GitHub Actions), фиксирование flaky тестов.

**Цель**: Автоматизировать тестирование и обеспечить high code quality.

**Файлы / Коммиты**:
- `tests/` (unit + integration tests)
- `pytest.ini`, `conftest.py`
- `.github/workflows/` (CI config)
- Коммиты: c750d7e, xxxxxxx (множество)

**Подзадачи**:
- 09.1 — Все unit тесты запущены; flaky тесты зафиксированы (10 ч)
- 09.2 — Mocks для external services (Whisper, LLM, Yukassa) добавлены (12 ч)
- 09.3 — CI pipeline (pytest + lint + black check) настроен в GitHub Actions (12 ч)
- 09.4 — Документация по локальному запуску тестов подготовлена (6 ч)

**Acceptance Criteria**:
- CI запускает тесты на каждый PR
- Базовый набор тестов зелёный (coverage > 70%)
- Flaky тесты помечены (@pytest.mark.flaky) или отложены
- Lint и format check pass

**QA**:
```bash
pytest tests/ -v --cov=transkribator_modules
python -m black --check .
python -m pylint transkribator_modules/
```

**Branch/PR**: `feature/queue-adr-migration/task-09-testing-ci`

---

## ФАЗА 4: Finalization & Release (TASK-10–11)
**Период**: Месяцы 10–12 | **Часы**: ~42 ч | **Связь**: Этап 6 плана НИОКР (финализация + оформление результатов)

### Задача 10: Repository Cleanup & Documentation (24 ч)

**Описание**: Очистка репозитория от больших файлов (exports, results, wheelhouse), обновление .gitignore, подготовка плана по очистке истории (опционально), финальная документация.

**Цель**: Привести репозиторий в production-ready state.

**Файлы / Коммиты**:
- `exports/`, `results/`, `wheelhouse/`, `server_dbs_*` (очищение)
- `.gitignore` (update)
- `LARGE_FILES_FIX.md` (documentation)
- Коммит: b4a3591a

**Подзадачи**:
- 10.1 — Инвентарь больших файлов составлена; архивирование/перенос подтверждены (6 ч)
- 10.2 — `.gitignore` обновлён; большие файлы удалены из index (6 ч)
- 10.3 — План по очистке истории (git-filter-repo / BFG) подготовлен для обсуждения (4 ч)
- 10.4 — Локальная очистка рабочего дерева выполнена (4 ч)
- 10.5 — Финальная документация (ARCHITECTURE.md, DEPLOYMENT.md) обновлена (4 ч)

**Acceptance Criteria**:
- Большие бинарники больше не попадают в новые коммиты
- Документ о перемещении файлов готов
- Репозиторий клонируется быстро (без больших файлов в истории)
- ARCHITECTURE.md и DEPLOYMENT.md актуальны

**QA**:
```bash
du -sh .git/
git log --all --raw | grep -c "bin"  # should be minimal
```

**Branch/PR**: `feature/queue-adr-migration/task-10-cleanup`

---

### Задача 11: Final Testing, Bug Fixes & Release Checklist (18 ч)

**Описание**: Финальное end-to-end тестирование, исправление критических багов, подготовка релизного чеклиста и runbook для операторов.

**Цель**: Обеспечить стабильный релиз и передачу знаний операционной команде.

**Файлы / Коммиты**:
- Различные баги в разных модулях (исправления)
- `RELEASE_CHECKLIST.md` (новый)
- `RUNBOOK.md` (новый)

**Подзадачи**:
- 11.1 — End-to-end сценарии протестированы (upload → transcribe → format → payment) (6 ч)
- 11.2 — Критические баги выявлены и закрыты (8 ч)
- 11.3 — Финальный smoke test по чеклисту прогнан (2 ч)
- 11.4 — Release checklist и runbook для ops подготовлены (2 ч)

**Acceptance Criteria**:
- E2E workflow успешно проходит в staging
- Все критические баги (P0) закрыты
- Release checklist заполнен и подписан
- Runbook содержит: deploy steps, rollback procedure, monitoring, troubleshooting

**QA**:
```bash
# E2E: 
python tests/e2e/test_full_workflow.py --env staging
# Smoke:
pytest tests/test_smoke_*.py -v
```

**Branch/PR**: `feature/queue-adr-migration/task-11-final-release`

---

## Дополнительно: Синхронизация с календарным планом НИОКР

| Этап НИОКР | Месячный интервал | Фаза миграции | TASK-ы | Ключевые результаты |
|-----------|-------------------|---------------|--------|-------------------|
| **1. Аналитика & проектирование** | 1–2 | *Prep* | — | ADR, архитектура, контракты |
| **2. Базовый прототип** | 3–4 | Фаза 1 | TASK-01..03 | Queue + Worker foundation |
| **3. Развитие агентной логики** | 5–6 | Фаза 2 | TASK-04..06 | Transcriber + Bot + Payments |
| **4. Агентные действия & интеграции** | 7–8 | Фаза 3 | TASK-07..09 | Docker + Testing + CI |
| **5. Экспериментальная валидация** | 9–10 | Фаза 4 | TASK-10..11 | Cleanup + Final testing |
| **6. Финализация & оформление результатов** | 11–12 | *Post-release* | — | Documentation, IP protection |

---

## Чеклист перед началом работ

1. ✅ Отсутствие утекших секретов в репозитории проверено
2. ✅ Ветки для каждой фазы созданы (`phase-1-*`, `phase-2-*` и т.д.)
3. ✅ CI pipeline настроен (базовый набор тестов и lint)
4. ✅ Координатор миграции БД назначен (для prod downtime, если потребуется)

---

## Формат PR / Issue

```
Title: [TASK-XX] Короткий заголовок фазы

Description:
- Цель фазы (1–2 предложения)
- Перечень основных компонентов, которые меняются
- Dependencies на другие TASK-и (если есть)

Checklist:
- [ ] Unit тесты зелёные
- [ ] Integration smoke тесты пройдены
- [ ] Документация обновлена (README, ARCHITECTURE.md)
- [ ] Логирование добавлено/улучшено
- [ ] Code review: 2 approvals
```

---

## Риски и рекомендации

| Риск | Рекомендация |
|------|-------------|
| WireGuard / сетевые привилегии в dev | Использовать изолированную VM; fallback режимы без WG |
| Long-running services (Whisper) | Добавить health checks, таймауты, graceful shutdown |
| Payment sandbox testing | Использовать только sandbox Yukassa, не prod данные |
| Repository history cleanup | Обсудить отдельно; выполнять только с согласованием |
| Race conditions в queue | Comprehensive concurrency testing (threading, multiprocessing) |
| Flaky tests в CI | Mark с @pytest.mark.flaky; отложить или зафиксировать |

---

## Какой будет следующий шаг?

После завершения этого плана на февраль 2026 г.:

1. **Production Deployment** — Развёртывание на production (требует отдельное планирование)
2. **Monitoring & Alerting** — Внедрение мониторинга в production
3. **Optimization & Scaling** — Оптимизация по результатам использования
4. **Documentation for Scientific Report** — Подготовка научно-технического отчёта (требование гранта)
5. **IP Protection** — Подача заявки на регистрацию ПО (Copyright/Patent)

---

**Документ подготовлен**: 22 февраля 2026 г.  
**Статус**: ✅ Готов к исполнению  
**Контакт**: см. OWNERS.md
