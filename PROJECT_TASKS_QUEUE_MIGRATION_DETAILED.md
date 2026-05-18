# План работ: мигра## Общая структура задач и суммарная оценка

- Всего задач в этой фазе: 10 (TASK-12 до TASK-21)
- Суммарная оценка этой фазы: ~600 часов
- **Контекст:** Это завершающая фаза проекта Cyberkitty19 (начало было в марте 2025 г., всего проекта ~2470 часов) очереди, DI‑worker и сопутствующие изменения (TASK-12 до TASK-21)

Примечание: все перечисленные работы выполнил один разработчик; формулировки в задачах и подзадачах отражают этот факт (прошедшее время, единственный исполнитель).

**Контекст:** Эти задачи (TASK-12 до TASK-21) являются частью более крупного проекта разработки Cyberkitty19 Transkribator. Полный ретроспективный отчёт со всеми TASK-00 до TASK-21 находится в `PROJECT_FULL_RETROSPECTIVE_REPORT.md`. 

Цель: задокументировать текущую фазу разработки — миграцию на архитектуру Queue + Worker для асинхронной обработки — в подробном виде (подзадачи, оценки, критерии приёмки). Общая оценка этой фазы: ~600 часов.

Предисловие — допущения и контекст
- Оценка ориентирована на 1 разработчика (FTE) и суммарно ~600 часов. Часы разбиты по задачам и подзадачам.
- Оценки включают анализ, разработку, базовое тестирование и исправления после ревью. Не включают длительное интеграционное тестирование в облаке, масштабное QA или работу с ревизией git‑истории (git filter‑repo) — это опциональные задачи, требующие отдельной оценки.
- Мы опирались на diff main..HEAD (исключая большие экспорты) и список коммитов в ветке.

Как использовать этот файл
- Каждая задача готова к копированию в трекер (Jira/GitHub/Asana). Для каждой задачи указаны: ориентировочная оценка, приоритет, затронутые файлы/коммиты, подзадачи, acceptance criteria и тесты.
- Предложенные имена веток/PR приведены в форме `feature/queue-adr-migration/task-XX-short-title`.

---

Общая структура задач и суммарная оценка
- Всего задач: 11
- Суммарная оценка: ~600 часов

---

Задача 12 — ADR и план миграции очереди (16 ч) — Pri: Высокий
Files / Commits:
- `alembic/versions/20260125_create_processing_jobs.py`
- `docs/adr/ADR-2026-001-queue-workers.md`
- `tests/test_job_queue.py`
- Коммит: e2c9d62

Подзадачи:
 - 01.1 — Существующий draft ADR прочитан и замечания собраны (1.5 ч)
 - 01.2 — Контракт очереди (таблицы, поля, статусы задач, TTL, retries) дописан и зафиксирован (4 ч)
 - 01.3 — План миграции и rollback‑процедуры описаны и задокументированы (2.5 ч)
 - 01.4 — Checklist для PR миграции и runbook для оператора сформированы (2 ч)
 - 01.5 — ADR согласован с техлидом/разработчиком и внесены правки (3 ч)
 - 01.6 — Тест‑скелет и примерные данные обновлены для проверки миграции (3 ч)

Acceptance criteria:
- ADR файл в `docs/adr/` утверждён (или отмечены open‑issues)
- Есть чёткий план миграции и rollback, применимый на dev локальной базе
- Unit тест/пример данных для миграции работают (alembic upgrade/ downgrade локально)

Риски / замечания:
- Если потребуется изменять историю репозитория (удалять старые бинарники), это отдельный процесс и может повлиять на timeline.

Suggested branch/PR: `feature/queue-adr-migration/task-12-adr`.

---

Задача 13 — Реализация очереди: DAO, services, тесты, миграция (80 ч) — Pri: Высокий
Files / Commits:
- `transkribator_modules/jobs/queue.py`
- `transkribator_modules/jobs/service_factory.py`
- `transkribator_modules/jobs/services.py`
- `tests/test_job_queue.py`, `tests/test_job_queue_db.py`
- Коммит: e2c9d62 и изменения в jobs/*

Подзадачи:
 - 02.1 — Спецификация API DAO (enqueue, claim, update_status, requeue, fail) и контракты подготовлены (4 ч)
 - 02.2 — DAO с использованием SQLAlchemy и транзакций реализован (20 ч)
 - 02.3 — Сервисный слой (обёртки, retries, backoff) реализован (10 ч)
 - 02.4 — Unit‑тесты для DAO и сервиса написаны (10 ч)
 - 02.5 — Интеграционные тесты enqueue→worker→complete реализованы и пройдены как smoke (12 ч)
 - 02.6 — Логирование и метрики для lifecycle настроены (8 ч)
 - 02.7 — Рефактор и мелкие исправления по результатам тестирования выполнены (16 ч)

Acceptance criteria:
- DAO покрыт unit тестами (happy path + error paths)
- Интеграционный smoke: задача ставится, воркер забирает → выполняет → обновляет статус в БД
- Нету race conditions при параллельном claim (тестовые сценарии)

QA:
- Локальный тест: `pytest tests/test_job_queue.py::test_enqueue_and_claim -q`
- Нагрузочный smoke: enqueue 100 коротких задач и проверено завершение/отсутствие deadlocks

Suggested branch/PR: `feature/queue-adr-migration/task-13-queue-dao`.

---

Задача 14 — DI worker и long‑lived Whisper service (контейнеризация и интеграция) (110 ч) — Pri: Высокий
Files / Commits:
- `tools/whisper_service.py`, `tools/transcribe_local_whisper.py`
- `tools/di_worker/*` (Dockerfile, entrypoint, scripts)
- `transcribe_client/di_worker.py`
- Коммиты: 763df02, 411f66c, b4a3591a

Подзадачи:
 - 03.1 — Прототип FastAPI whisper service и его интерфейс реализованы (10 ч)
 - 03.2 — Dockerfile и entrypoint для whisper service подготовлены (8 ч)
 - 03.3 — DI worker интегрирован с transcribe_client и окружение настроено (DI_WORKER_FORCE_LOCAL и т.д.) (20 ч)
 - 03.4 — Сетевые детали (WireGuard/WG entrypoint) настроены при необходимости (16 ч)
 - 03.5 — Unit и e2e тесты для whisper service добавлены и прогнаны (14 ч)
 - 03.6 — Интеграция worker→whisper_service→DB и политики retry/timeout реализованы (20 ч)
 - 03.7 — Benchmark/run скрипты (run_prepare_and_transcribe, run_chunk_scan) подготовлены (12 ч)

Acceptance criteria:
- Docker image для whisper_service и di_worker собирается
- На dev compose: отправляем sample audio, получаем transcript; воркер обрабатывает job успешно
- Тесты на таймаут/перезапуск работают

Риски:
- Сетевые/permissions (WG, tun devices) могут потребовать админских прав и дополнительной отладки
- Тестирование на CI может быть ограничено, потребуется мокировать long‑lived сервисы

Suggested branch/PR: `feature/queue-adr-migration/task-14-di-worker-whisper`.

---

Задача 15 — Transcriber pipeline (v4) и форматирование LLM (60 ч) — Pri: Высокий
Files / Commits:
- `transkribator_modules/transcribe/transcriber_v4.py`
- `transcribe_client/*`
- Коммит: b4a3591a

Подзадачи:
 - 04.1 — Chunking logic проверена и улучшена для длинных транскриптов (10 ч)
 - 04.2 — Обработка ошибок LLM и fallback логика реализованы (5 ч)
 - 04.3 — Интеграция с OpenRouter/OpenAI client настроена (headers, retry, rate limits) (10 ч)
 - 04.4 — Unit тесты для форматирования и chunking написаны (10 ч)
 - 04.5 — Выполнен smoke run на длинном файле и оценена латентность (10 ч)
 - 04.6 — Логи и метрики (size, time, token usage) настроены (15 ч)

Acceptance criteria:
- Форматирование через LLM работает и имеет fallback
- Chunking корректно объединяет части
- Unit tests зелёные

Suggested branch/PR: `feature/queue-adr-migration/task-15-transcriber-v4`.

---

Задача 16 — Рефактор бота: handlers, callbacks, logging, dedupe (140 ч) — Pri: Высокий
Files / Commits:
- `transkribator_modules/bot/handlers.py`, `callbacks.py`, `commands.py`, `logging_utils.py`, `processing_guard.py`, `update_dedupe.py`, `utils/large_file_downloader.py`
- Коммиты: 14c3fd2, b4a3591a и др.

Подзадачи:
 - 05.1 — Handler flow просмотрен и реорганизован (12 ч)
 - 05.2 — processing_guard внедрён и проверен для защиты от двойной обработки (12 ч)
 - 05.3 — update_dedupe реализован и покрыт тестами (10 ч)
 - 05.4 — logging_utils и событийная телеметрия интегрированы (24 ч)
 - 05.5 — Обработка больших файлов (large_file_downloader) переписана/усилена (16 ч)
 - 05.6 — Smoke тесты для основных пользовательских сценариев написаны (20 ч)
 - 05.7 — Баги исправлены и доработки выполнены по результатам тестов (36 ч)

Acceptance criteria:
- Основные сценарии (start, upload media, create note, buy plan) работают в dev environment
- Dedupe и processing_guard предотвращают дубли и race conditions
- Логи событий в нормальном виде и есть примитивная аналитика

QA:
- Использовать `LOCAL_BOT_API` и dev compose; прогнать сценарии руками и автоматизированные smoke тесты

Suggested branch/PR: `feature/queue-adr-migration/task-16-bot-refactor`.

---

Задача 17 — Платежи (Yukassa) и мониторинг (40 ч) — Pri: Средне­высокий
Files / Commits:
- `transkribator_modules/bot/payments.py`
- `transkribator_modules/payments/yukassa.py`
- `transkribator_modules/payments/monitoring.py`
- `transkribator_modules/bot/yukassa_webhook.py`
- Коммит: b4a3591a

Подзадачи:
 - 06.1 — Вебхук и подпись проверены, handler рефакторирован (8 ч)
 - 06.2 — Мониторинг платёжных событий настроен (8 ч)
 - 06.3 — Sandbox flow протестирован и исправления внесены (12 ч)
 - 06.4 — Документация и runbook для webhook подготовлены (6 ч)
 - 06.5 — Логирование и тесты добавлены (6 ч)

Acceptance criteria:
- Sandbox payment scenario (precheckout → success) проходит и обновляет DB
- Webhook обрабатывает retries и idempotency

Suggested branch/PR: `feature/queue-adr-migration/task-17-payments`.

---

Задача 18 — Docker / docker-compose / deploy (40 ч) — Pri: Средний
Files / Commits:
- `Dockerfile*`, `docker-compose*.yml`, `entrypoint-wg.sh`, `entrypoint.sh`, `Makefile`
- Коммиты: b4a3591a, f9323456

Подзадачи:
 - 07.1 — Текущие Dockerfile проверены и выявлены места с копированием `.env` и секретов (6 ч)
 - 07.2 — Слои оптимизированы и размер образов уменьшен (10 ч)
 - 07.3 — `docker compose build` и `up` протестированы на dev (10 ч)
 - 07.4 — README/quickstart и скрипты обновлены (6 ч)
 - 07.5 — CI build steps и caching strategy задокументированы (8 ч)

Acceptance criteria:
- Образы собираются локально, `docker compose up` стартует стек
- В образах нет копий реальных секретов; build reproducible

Suggested branch/PR: `feature/queue-adr-migration/task-18-docker`.

---

Задача 19 — Инструменты, minimal_app и скрипты (32 ч) — Pri: Средний
Files / Commits:
- `minimal_app/*`, `tools/di_worker/*`, `tools/*`, `scripts/*`
- Коммиты: 6af943b, c750d7e, 763df02

Подзадачи:
 - 08.1 — minimal_app pipeline проверен и баги исправлены (12 ч)
 - 08.2 — Утилиты di_worker стабилизированы (8 ч)
 - 08.3 — README и usage scripts обновлены (6 ч)
 - 08.4 — Примеры использования для разработчиков добавлены (6 ч)

Acceptance criteria:
- minimal_app запускается локально и проходит примерный E2E
- Инструменты сопровождаются документацией

Suggested branch/PR: `feature/queue-adr-migration/task-19-tools`.

---

Задача 20 — Тесты и CI (40 ч) — Pri: Высокий
Files / Commits:
- `tests/*`, `pytest.ini`, `.github/workflows/*`
- Коммит: c750d7e (+ множество)

Подзадачи:
 - 09.1 — Все unit tests прогнаны и flaky tests зафиксированы (8 ч)
 - 09.2 — Mocks для внешних сервисов в тестах добавлены (12 ч)
 - 09.3 — CI pipeline (pytest + lint + black check) настроен (12 ч)
 - 09.4 — Документация по локальному запуску тестов подготовлена (8 ч)

Acceptance criteria:
- CI запускает тесты и линтеры; базовый набор тестов зелёный
- Flaky/long tests помечены/отложены

Suggested branch/PR: `feature/queue-adr-migration/task-20-tests-ci`.

---

Задача 21 — Очистка репозитория: large files & policy (24 ч) — Pri: Средний
Files / Commits:
- `exports/*`, `results/*`, `wheelhouse/*`, `server_dbs_*`, `.gitignore`, `LARGE_FILES_FIX.md`
- Коммит: b4a3591a

Подзадачи:
 - 21.1 — Список больших файлов составлен и архивирование/перенос подтверждён (6 ч)
 - 21.2 — `.gitignore` обновлён и файлы удалены из индекса (6 ч)
 - 21.3 — План по очистке истории (git-filter-repo / BFG) подготовлен для обсуждения (4 ч)
 - 21.4 — Локальная очистка рабочего дерева выполнена (6 ч)

Acceptance criteria:
- Большие бинарники больше не будут попадать в коммиты; документ о перемещении готов
- Если нужно — подготовлен план по очистке истории (выполнение отдельно)

Suggested branch/PR: `feature/queue-adr-migration/task-21-repo-cleanup`.

---

Задача 22 — Buffer: багфикс и финальный polish (18 ч) — Pri: Высокий
Files: различные мелкие правки по результатам интеграции

Подзадачи:
 - 22.1 — Критические баги закрыты (10 ч)
 - 22.2 — Финальный smoke test по checklist прогнан (4 ч)
 - 22.3 — Релизный чеклист и короткий runbook подготовлены (4 ч)

Acceptance criteria:
- Smoke tests пройдены; критичные баги закрыты; релизный чеклист готов

---

Checklist перед началом работ (рекомендации)
1. Отсутствие утекших секретов в репозитории проверено; при обнаружении — устранено.
2. Ветки для каждой задачи созданы (по 1 задаче — 1 ветка) и PR‑template добавлен.
3. CI‑pipeline настроен с минимальным набором тестов и lint/format checks.
4. Владелец/релиз‑менеджер назначен для координации миграции БД (при необходимости downtime).

---

Формат PR/Issue (шаблон)
- Title: `[task-XX] короткий заголовок` (пример: `[task-02] Queue DAO + services`)
- Description: цель задачи, список изменённых файлов, dependencies, estimate (часы)
- Checklist: unit tests, integration smoke, docs updated, migration plan, peer review

---

Риски и рекомендации по уменьшению их влияния
- WireGuard / сетевые привилегии: запускать в изолированной dev VM; предусмотреть fallback‑режимы без WG.
- Long‑running services: добавить health checks и временные таймауты, чтобы worker не зависал.
- Payment flow: использовать sandbox/тестовый аккаунт Yukassa; не тестировать на прод данных.
- Repo history cleanup: обсудить отдельно и не выполнять без согласования со всей командой.

---

Что я могу сделать дальше
- Сгенерировать CSV (готово) — и/или отдельные Markdown‑Issue файлы для каждой задачи.
- Автоматически создать Issues в GitHub (требуется токен и права) — могу выполнить по запросу.
- Разбить большие задачи (например, task-05) на более мелкие subtasks для параллельной работы.

Если хотите, я могу сейчас:
- 1) сгенерировать отдельный markdown‑файл (по одной issue на файл) для быстрой импорта в GitHub или копирования в Jira; или
- 2) начать создавать GitHub Issues автоматически (предоставьте токен с правами repo:issues), или
- 3) разбить TASK-05 (бот) на 8–12 подзадач конкретнее.

Скажите, что предпочитаете — я выполню следующий шаг.