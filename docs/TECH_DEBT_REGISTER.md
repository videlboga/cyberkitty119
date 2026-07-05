---
title: "Technical Debt Register — Cyberkitty119"
author: "Docs Team"
date: 2026-01-23
status: Draft
tags: [tech-debt, refactor, inventory]
related: [INVENTORY.md, RESEARCH.md]
---

# Реестр технического долга — Cyberkitty119

Действенный реестр, производный от `docs/INVENTORY.md`. Каждая запись: путь, статус, проблема, запланированное действие, приоритет.

Статусы:
- `core` — текущая опорная часть системы, трогать осторожно
- `legacy` — легаси, используется по минимуму или не должен развиваться
- `dup` — дубликат / альтернативная реализация
- `remove` — кандидат на удаление после проверки
- `mixed` — смесь active/legacy, требует расчленения
- `verified-removed` — подтверждённо удалено из репозитория; запись оставлена как историческая пометка, чтобы будущие работы не реинвестигировали эти пути

Приоритеты:
- `H` — высокий: блокирует развитие, высокий риск регресса, либо активно копит долг
- `M` — средний: заметный долг, не блокирующий, плановая уборка
- `L` — низкий: косметика, исторические пометки, разовый клин

## Разрешённые элементы (verified-removed)

Эти записи зафиксированы как уже разрешённые — файлы/пакеты физически отсутствуют в репозитории (проверено через `ls` и `git ls-files` в worktree). Не реинвестигировать.

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| ~~`handlers.py` (корень)~~ | remove / verified-removed | Легаси root-entrypoint бота. Дублировал `transkribator_modules/bot/handlers.py`. Файл отсутствует: `ls handlers.py` → нет, `git ls-files handlers.py` → пусто. | Канонический entrypoint единственный: `transkribator_modules/bot/handlers.py`. Действий не требуется. Запись оставлена как историческая пометка. | L |
| ~~`transkribator_modules/transkribator_modules/**`~~ (вложенный дублирующий пакет — `bot/**` и `transcribe/*`) | dup / verified-removed | Двойная структура пакетов `transkribator_modules/.../transkribator_modules/...` — риск случайного использования легаси-импортов. Каталог отсутствует: `ls transkribator_modules/transkribator_modules` → нет. | Пакет подтверждённо удалён из репозитория. Канонический путь — `transkribator_modules/bot/` и `transkribator_modules/transcribe/`. Действий не требуется. При будущих археологических находках — не восстанавливать. | L |

## 1. Сервисы и entrypoints

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `docker-compose.bot-v2.yml` (`bot`, `worker`, `core-api`, `postgres`; `telegram-bot-api` с `profiles: [donotstart]`) | core | Несколько compose-файлов в корне, есть следы старых флагов (DeepInfra и др.). | Зафиксировать `docker-compose.bot-v2.yml` как эталонный prod-compose, остальные явно пометить dev/legacy или удалить. | M |
| `transkribator_modules/bot/handlers.py` | core | Смешаны старые/новые ветки, много флагов (`AGENT_FIRST`, beta и т.п.); 2262 строки. Пересечение video/audio-флоу. | Разбить на подмодули (`video.py`, `audio.py`, `text.py`, `agent.py`), вычистить неиспользуемые/устаревшие обработчики. (Совпадает с записью в секции 4 — единая работа.) | H |
| `job_worker.py` | core | В логах видно только «plan reminders» — фактическая нагрузка по медиа не очевидна. | Проинвентаризировать `job_type` и обработчики, отключить/удалить неиспользуемые джобы. | M |
| `core_api/main.py` + `Dockerfile.api` | core | Возможны мёртвые эндпоинты, пересечение логики с ботом. `internal_bot.py:61` и `media_service.py:104` отдают `job.error` raw. | Составить список эндпоинтов и их реальное использование, выделить чистый API для miniapp; не показывать traceback пользователю. | M |
| `transkribator_modules/main.py` | core | `application.add_error_handler(_on_error)` exists at line 170 and logs `context.error` with `exc_info`. It does **not** send a user-visible message. Handlers still dereference `update.message.from_user` / `update.callback_query.from_user` without None-checks. | Keep `_on_error`; add user-visible `send_message` when `update.effective_chat` exists; add early-return guard in `handle_message` when `update.effective_user is None` or `update.message is None` (RESEARCH.md AC3.1–AC3.3). | H |

## 2. Транскрипция и форматирование

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `transkribator_modules/transcribe/transcriber_v4.py` | core | Большой монолитный модуль (1987 строк), содержит закомментированную DeepInfra-логику и много ответвлений. | Выделить отдельные функции: ASR, чанкинг, форматирование, заголовки; удалить/архивировать DeepInfra и неиспользуемые ветки. | H |
| `format_transcript_with_llm` (в `transcriber_v4.py`) | core | Нет защиты от артефактов типа повторяющегося «та-та-та…», модель может искажать факты и переносить контекст. | Добавить валидацию результата (повторы, сильное искажение длины/содержания), fallback на локальное форматирование. | H |
| `transcribe_segment_with_openrouter_gemini` (`transcriber_v4.py`) | core | 429/500/502/503/504 retry на line ~1953 выполняет `continue` без `asyncio.sleep`; нет агрегированного мониторинга по ошибкам. | Добавить `await asyncio.sleep(min(2 ** attempt, 30))` перед retry-continue при 429/5xx; собрать метрики по статусам (успешно/timeout/HTTP ошибки), добавить короткий отчёт в логи/метрики. | M |
| `transcribe_client/` (адаптеры: openrouter, deepinfra, gpu, local, di_worker, stub) | core | `TranscribeClient` выбирает ОДИН адаптер через `_resolve_default_adapter` — fallback между адаптерами при ошибке НЕ реализован. `openrouter.py`: retries on 429/502/503/504 up to 5 hardcoded attempts with exponential backoff capped at 30s, but lacks jitter, `Retry-After` handling, `OPENROUTER_MAX_RETRIES` env override, and the `rate_limited=True` envelope. Chunk-level 429 throttle uses `OPENROUTER_429_THROTTLE_SEC` (default 30s). Дублирующий мёртвый код chunked transcription (строки 256–314) — проверить актуальность. | Реализовать fallback на DeepInfra при OpenRouter failure (в `default_transcribe_media`); вынести `max_retries` в env `OPENROUTER_MAX_RETRIES` (default 6); добавить jitter и обработку `Retry-After`; возвращать `{"status":"error","meta":{"rate_limited":True}}`; удалить/подтвердить мёртвый дублирующий блок. | H |
| Тесты транскрипции: `test_raw_transcript.py`, `test_process_video.py`, `test_formatting.py` | core | Не покрывают кейсы длинных транскриптов с артефактами и искажением смысла. | Добавить тесты на: длинные встречи, повторяющиеся токены, корректность дат/фактов в LLM-формате. | M |

## 3. LLM вокруг заметок и саммари

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `transkribator_modules/agent/dialog.py` | core | Хранит key-логику работы с `notes` и Google Docs, промпты зашиты в код. | Вынести промпты и конфиг в отдельный модуль/настройки, чётко задокументировать контракт по входу/выходу. | M |
| `core_api/domains/agent/core/content_processor.py` | core/stub | Класс `ContentProcessor` помечен как stub; реальная логика `_build_summary_and_tags` отдельно. | Привести к единообразию: либо дописать `ContentProcessor`, либо явно использовать только `_build_summary_and_tags`. | M |
| Саммари `notes.summary` (например заметка 1494) | core | Потенциальная подмена фактов (пример с датой 1 февраля, «цена слова», формализация решений). | Ужесточить промпты (запрет выдумывать/менять факты), добавить пост-валидацию и, по возможности, diff с исходным текстом. | H |

## 4. Telegram-бот и диалоги

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `transkribator_modules/bot/handlers.py` (диалоги/меню) | core | Дубли с уже удалённым корневым `handlers.py` (см. verified-removed выше). Много флагов (`AGENT_FIRST`, beta), пересечение video/audio-флоу. | Разбить на подмодули (`video.py`, `audio.py`, `text.py`, `agent.py`), вычистить неиспользуемые/устаревшие обработчики. (Совпадает с записью в секции 1 — единая работа.) | H |
| Beta-ветки и меню (`beta/handlers`, beta-флаги) | mixed | Могут тянуть старые подходы, которые уже не соответствуют текущему LLM/транскрипции. | Описать реальное использование beta, отключить/удалить мёртвые сценарии. | M |

## 5. База данных и фоновые задания

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| Таблицы: `users`, `transcriptions`, `notes` | core | Есть поля и таблицы под старые фичи (DeepInfra, старые планы), часть может не использоваться. | Для каждой таблицы собрать карту чтений/записей, пометить неиспользуемые поля/таблицы как кандидатов на удаление. | M |
| `processing_jobs` | core/mixed | По пользователю 274232565 за 2026-01-06 нет джоб — часть логики может обходиться без очереди. `job.error` хранит сырой traceback (утечка в API/miniapp/MAX-бот). `fail_job` in `queue.py` truncates to 4000 chars but does not strip/sanitize tracebacks. | Проверить, какие `job_type` реально создаются/обрабатываются, отключить/удалить неиспользуемые; хранить в `job.error` краткое сообщение, а не traceback (см. RESEARCH.md AC2.1–AC2.2); добавить defence-in-depth sanitize в `fail_job` для substring `Traceback (most recent call last)`. | M |
| `transkribator_modules/db/**` | core | Возможны дубли/старые сервисы, неиспользуемые методы. | Инвентаризировать классы/методы, удалить dead code, унифицировать работу с сессиями и транзакциями. | M |

## 6. API / miniapp

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `api_server.py`, `transkribator_modules/api/**` | core | Неочевидно, какие эндпоинты реально используются miniapp/клиентами. `internal_bot.py:61` и `media_service.py:104` отдают `job.error` raw (traceback) — утечка пользователю. | Составить список эндпоинтов и маппинг на клиентов; пометить мёртвые/deprecated маршруты; для users — generic message, raw error только в debug-режиме (RESEARCH.md AC2.4). | M |
| `miniapp/**`, `miniapp_dist/**` | mixed | Возможно старые сборки/артефакты, дубли фронта. | Выяснить, какая сборка реально отдается в проде, остальные пометить как legacy или удалить. | L |

## 7. Инфраструктура, логи и тесты

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `Dockerfile*`, `docker-compose.*.yml` | core/mixed | Много вариантов Dockerfile/compose, часть может быть историческим багажом. | Явно классифицировать (prod/dev/test), удалить дубли и устаревшие файлы. | M |
| `setup_and_build.sh`, `deploy*.sh`, `scripts/**` | mixed | Есть одноразовые скрипты и старые пайплайны. | Описать текущий реальный деплой, остальное пометить как legacy. | L |
| `LOGGING_IMPROVEMENTS.md`, `logs/*`, `docker_journal.log` | core | Логи не всегда содержат user_id/media_id/job_id в одном сообщении; трудно собирать полную трассу. | Стандартизировать формат логов для ключевых потоков, добавить структурный контекст. | M |
| `tests/**`, `test_*.py`, `test_*.sh` | core | Не покрывают новые LLM-артефакты (как «та-та-та»), нет регресса на искажение фактов. | Добавить тесты для длинных транскриптов, проверки формата и соответствия саммари исходному содержанию. | M |

## 8. Дополнительные долги из RESEARCH.md (не в INVENTORY, но активные)

| Path | Status | Problem | Planned Action | Priority |
|------|--------|---------|----------------|----------|
| `max_bot/native_service.py:63`, `max_bot/native_handlers.py:203` | core | Отдаёт raw `job.error` (traceback) пользователю через sendMessage/editMessageText. | Заменить на дружелюбное сообщение без `job.error` (RESEARCH.md AC2.3). | M |
| `transkribator_modules/bot/handlers.py:1358,1360` and the matching Mega/Dropbox/Yandex.Disk sites at 1438/1440, 1512/1514, 1590/1592 | core | `await _safe_edit_message(status_msg, str(exc))` — утечка `str(exc)` для GDrive/Dropbox/Mega/Yandex.Disk ошибок скачивания. Exception strings are currently user-friendly Russian text raised by the downloader modules, but they bypass the bot's generic error wrapper. | Заменить `str(exc)` на дружелюбное generic сообщение, либо гарантировать что downloader исключения не содержат технических деталей (RESEARCH.md AC2.3). | M |

## Источник и сопровождение

- Производный документ от `docs/INVENTORY.md` (верхнеуровневая инвентаризация) и `docs/RESEARCH.md` (стек, архитектура, acceptance criteria).
- Записи `verified-removed` оставлены намеренно: они фиксируют уже выполненную уборку, чтобы будущие археологические работы не реинвестигировали эти пути и не «восстанавливали» удалённые дубликаты.
- При выполнении действия — переносить запись в раздел «Разрешённые» с пометкой даты/коммита, не удалять.