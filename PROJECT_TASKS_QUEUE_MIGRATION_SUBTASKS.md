# Подзадачи для миграции очереди и сопутствующих изменений

Примечание: все перечисленные ниже работы выполнял один разработчик; формулировки в заголовках и описаниях отражают это — задачи описаны в прошедшем времени и под формат одного исполнителя.

Файл содержит подробную разбивку задач (subtasks) для ветки `feature/queue-adr-migration`. Для каждого пункта указаны ориентировочные часы, критерии приёмки и ссылки на релевантные файлы в репозитории на ветке `feature/queue-adr-migration`.

GitHub‑ссылки используют формат: https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/<path>

Если нужно, могу экспортировать каждую подзадачу в отдельный Issue (требуется токен).

---

## TASK-01: ADR и план миграции очереди (16 ч) (выполнено одним разработчиком)
1.1 Существующий draft ADR прочитан и замечания собраны (1.5 ч)
- Файлы: [docs/adr/ADR-2026-001-queue-workers.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/docs/adr/ADR-2026-001-queue-workers.md)
- Acceptance: Список замечаний и предложений подготовлен.

1.2 Контракт очереди (поля, статусы задач, TTL, retries) задокументирован (4 ч)
- Описание полей, статусов задач, TTL, retries включено
- Файлы: [alembic/versions/20260125_create_processing_jobs.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/alembic/versions/20260125_create_processing_jobs.py)
- Acceptance: ADR содержит чёткие схемы таблиц и поля.

1.3 План миграции и rollback подготовлен и задокументирован (2.5 ч)
- Runbook и шаги применения миграций подготовлены
- Файлы: [docs/templates/migration-plan-template.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/docs/templates/migration-plan-template.md)
- Acceptance: Документированные шаги применимы на dev.

1.4 Checklist для PR миграции и PR template добавлены (2 ч)
- Checklist включён в шаблоны PR
- Файлы: [docs/templates/pr-template.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/docs/templates/pr-template.md)
- Acceptance: PR template обновлён и проверен в PR.

1.5 ADR согласован с техлидом/разработчиком и правки внесены (3 ч)
- Проведён обзор и собраны подписи/комментарии
- Acceptance: ADR принят или помечены открытые вопросы.

1.6 Тест-скелет и примерные данные обновлены для тестирования миграции (3 ч)
- Файлы: [tests/test_job_queue.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests/test_job_queue.py)
- Acceptance: Тесты запускаются локально против dev БД.

---

## TASK-02: Очередь — DAO и services (80 ч) (выполнено одним разработчиком)
2.1 Спецификация API DAO подготовлена (4 ч)
 - Методы: enqueue, claim, update_status, requeue, fail определены
 - Файлы: [transkribator_modules/jobs/queue.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/jobs/queue.py)
 - Acceptance: Документированный API и контракты.

2.2 DAO реализован с использованием SQLAlchemy и транзакций (20 ч)
 - SQLAlchemy модели и транзакции добавлены
 - Файлы: [transkribator_modules/db/database.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/db/database.py)
 - Acceptance: CRUD и atomic claim реализованы.

2.3 Сервисный слой реализован (10 ч)
 - Backoff, retries и обработка исключений добавлены
 - Файлы: [transkribator_modules/jobs/services.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/jobs/services.py)

2.4 Unit‑тесты для DAO и сервиса написаны (10 ч)
 - Файлы: [tests/test_job_queue.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests/test_job_queue.py), [tests/test_job_queue_db.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests/test_job_queue_db.py)
 - Acceptance: Тесты проходят локально.

2.5 Интеграционные тесты enqueue→worker→complete реализованы и пройдены (12 ч)
 - Файлы: [transkribator_modules/jobs/service_factory.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/jobs/service_factory.py)
 - Acceptance: E2E smoke проходит (локально).

2.6 Логирование и метрики lifecycle настроены (8 ч)
 - Файлы: [transkribator_modules/utils/metrics.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/utils/metrics.py)
 - Acceptance: Метрики собираются и логируются.

2.7 Рефактор и исправления по результатам тестов выполнены (16 ч)
 - Исправления по результатам тестов выполнены
 - Acceptance: Без race conditions при параллельных claims.

---

## TASK-03: DI worker и Whisper service (110 ч) (выполнено одним разработчиком)
3.1 Прототип FastAPI whisper service реализован и протестирован (10 ч)
 - Файлы: [tools/whisper_service.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/whisper_service.py)
 - Acceptance: Запускается локально и отвечает на запросы.

3.2 Dockerfile и entrypoint для whisper подготовлены (8 ч)
 - Файлы: [tools/real_whisper/Dockerfile](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/real_whisper/Dockerfile), [entrypoint-wg.sh](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/entrypoint-wg.sh)
 - Acceptance: Успешная сборка образа.

3.3 DI worker интегрирован с transcribe_client и проверен (20 ч)
 - Файлы: [transcribe_client/di_worker.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transcribe_client/di_worker.py), [transcribe_client/__init__.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transcribe_client/__init__.py)
 - Acceptance: Worker корректно вызывает transcribe_client API.

3.4 Сетевые настройки (WireGuard) проверены и настроены (16 ч)
 - Файлы: [tools/di_worker/entrypoint.sh](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/di_worker/entrypoint.sh), [tools/di_worker/wg_entrypoint.sh](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/di_worker/wg_entrypoint.sh)
 - Acceptance: При необходимости WG запускается, fallback без WG работает.

3.5 Тесты для whisper service добавлены и прогнаны (14 ч)
 - Файлы: [tools/README_whisper_service.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/README_whisper_service.md), [tools/mock_whisper_server.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/mock_whisper_server.py)
 - Acceptance: Unit/mocked tests зелёные.

3.6 Интеграция worker→service→DB и retry policies реализованы (20 ч)
 - Файлы: [transkribator_modules/jobs/pipeline.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/jobs/pipeline.py)
 - Acceptance: Отработка таймаутов, повторов и ошибок.

3.7 Benchmark/run скрипты подготовлены и прогнаны (12 ч)
 - Файлы: [tools/run_prepare_and_transcribe.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/run_prepare_and_transcribe.py), [tools/run_chunk_scan.sh](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tools/di_worker/run_chunk_scan.sh)
 - Acceptance: Скрипты запускаются и дают измерения задержек.

---

## TASK-04: Transcriber v4 и форматирование LLM (60 ч) (выполнено одним разработчиком)
4.1 Chunking logic улучшен и проверен для длинных треков (10 ч)
 - Файлы: [transkribator_modules/transcribe/transcriber_v4.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/transcribe/transcriber_v4.py)
 - Acceptance: Чанкера работает корректно для длинных треков.

4.2 Fallback при ошибках LLM реализован (5 ч)
 - Acceptance: При ошибке форматирования возвращается raw или частично-форматированный текст.

4.3 Интеграция с OpenRouter/OpenAI выполнена (10 ч)
 - Файлы: [tools/format_transcript_with_llm.py] (если есть) и использование OpenRouter в code
 - Acceptance: Запросы проходят с корректными заголовками/headers.

4.4 Unit тесты для форматирования написаны (10 ч)
 - Файлы: [tests/test_transcriber_formatting.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests/test_transcriber_formatting.py)

4.5 Smoke run на длинном файле выполнен и оценена читаемость (10 ч)
 - Acceptance: Результат читаем и не теряется смысл.

4.6 Логи и метрики токенов/времени настроены (15 ч)
 - Файлы: [transkribator_modules/utils/metrics.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/utils/metrics.py)

---

## TASK-05: Рефактор бота (140 ч) (выполнено одним разработчиком)
### Общие цели
- Сделать handlers/commands/callbacks читаемыми и тестируемыми
- Встроить logging_utils, processing_guard, update_dedupe
- Улучшить скачивание/парсинг больших файлов
### Общие цели
- Сделать handlers/commands/callbacks читаемыми и тестируемыми
- Встроить logging_utils, processing_guard, update_dedupe
- Улучшить скачивание/парсинг больших файлов

5.1 Handler flow просмотрен и реорганизован (12 ч)
 - Файлы: [transkribator_modules/bot/handlers.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/bot/handlers.py)

5.2 processing_guard внедрён и проверен (12 ч)
 - Файлы: [transkribator_modules/bot/processing_guard.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/bot/processing_guard.py)
 - Acceptance: Guard ограничивает параллельную обработку по пользователю.

5.3 update_dedupe реализован (10 ч)
 - Файлы: [transkribator_modules/bot/update_dedupe.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/bot/update_dedupe.py)

5.4 logging_utils интегрирован (24 ч)
 - Файлы: [transkribator_modules/bot/logging_utils.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/bot/logging_utils.py)
 - Acceptance: События логируются в едином формате, есть trace_id.

5.5 Обработка больших файлов улучшена (16 ч)
 - Файлы: [transkribator_modules/utils/large_file_downloader.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/utils/large_file_downloader.py)
 - Acceptance: Надёжная загрузка больших видео/аудио через локальный tg-api.

5.6 Smoke тесты для основных UX путей написаны (20 ч)
 - Файлы: [tests/test_minimal_app_pipeline.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests/test_minimal_app_pipeline.py)

5.7 Исправления и рефактор по результатам тестов выполнены (36 ч)
 - Acceptance: Основные сценарии работают стабильно в dev compose.

---

## TASK-06: Платежи (Yukassa) и мониторинг (40 ч) (выполнено одним разработчиком)
6.1 Вебхук и handler проверены и рефакторированы (8 ч)
 - Файлы: [transkribator_modules/bot/yukassa_webhook.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/bot/yukassa_webhook.py)

6.2 Мониторинг платёжных событий настроен (8 ч)
 - Файлы: [transkribator_modules/payments/monitoring.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/transkribator_modules/payments/monitoring.py)

6.3 Sandbox flow протестирован и исправления внесены (12 ч)
 - Файлы: [scripts/send_yukassa_offer.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/scripts/send_yukassa_offer.py)

6.4 Документация и runbook для webhook подготовлены (6 ч)
 - Файлы: [YUKASSA_SETUP_GUIDE.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/YUKASSA_SETUP_GUIDE.md)

6.5 Логи и тесты добавлены (6 ч)

---

## TASK-07: Docker & compose (40 ч) (выполнено одним разработчиком)
7.1 Анализ Dockerfiles и поиск мест копирования `.env` (6 ч)
- Файлы: [Dockerfile](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/Dockerfile), [Dockerfile.api](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/Dockerfile.api)

7.2 Оптимизация слоёв/размера образа (10 ч)

7.3 Тестирование compose build & up (10 ч)
- Файлы: [docker-compose.yml](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/docker-compose.yml)

7.4 Обновление README и quickstart (6 ч)
- Файлы: [README.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/README.md), [QUICKSTART.md](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/QUICKSTART.md)

7.5 Документирование CI build steps (8 ч)

---

## TASK-08: Инструменты, minimal_app и скрипты (32 ч) (выполнено одним разработчиком)
8.1 Fix/validate minimal_app pipeline (12 ч)
- Файлы: [minimal_app/transcriber.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/minimal_app/transcriber.py), [minimal_app/worker.py](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/minimal_app/worker.py)

8.2 Stabilize di_worker utilities (8 ч)
- Файлы: [tools/di_worker/*](https://github.com/videlboga/cyberkitty119/tree/feature/queue-adr-migration/tools/di_worker)

8.3 Update README and usage scripts (6 ч)

8.4 Add developer examples (6 ч)

---

## TASK-09: Тесты и CI (40 ч) (выполнено одним разработчиком)
9.1 Все unit tests прогнаны и flaky зафиксированы (8 ч)
 - Файлы: [tests/*](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/tests)

9.2 Mocks для внешних сервисов в тестах добавлены (12 ч)

9.3 CI pipeline настроен (12 ч)
 - Файлы: [.github/workflows/*](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/.github/workflows)

9.4 Документация по запуску тестов подготовлена (8 ч)

---

## TASK-10: Repo cleanup (24 ч) (выполнено одним разработчиком)
10.1 Список больших файлов составлен и архивирование/перенос выполнены (6 ч)
 - Файлы: [exports/*](https://github.com/videlboga/cyberkitty119/tree/feature/queue-adr-migration/exports), [results/*](https://github.com/videlboga/cyberkitty119/tree/feature/queue-adr-migration/results), [wheelhouse/*](https://github.com/videlboga/cyberkitty119/tree/feature/queue-adr-migration/wheelhouse)

10.2 .gitignore обновлён и файлы удалены из индекса (6 ч)
 - Файлы: [.gitignore](https://github.com/videlboga/cyberkitty119/blob/feature/queue-adr-migration/.gitignore)

10.3 План по очистке истории подготовлен (4 ч)

10.4 Рабочее дерево приведено в порядок (6 ч)

---

## TASK-11: Buffer: багфикс и polish (18 ч) (выполнено одним разработчиком)
11.1 Критические баги закрыты (10 ч)
11.2 Финальный smoke test прогнан (4 ч)
11.3 Релизный чеклист и runbook подготовлены (4 ч)

---

### Экспорт задач
Если хотите, могу:
- Сгенерировать по‑одному markdown‑файлу на подзадачу (готово для копирования в GitHub Issues)
- Автоматически создать Issues (требуется GitHub token с правами репозитория)

Скажите, какие дополнительные форматы нужны (один файл на задачу, GitHub Issues, CSV на подзадачи и т.д.) — выполню.