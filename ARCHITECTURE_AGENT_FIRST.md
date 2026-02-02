# Архитектура: Agent‑First персональный ассистент (Wearable)

Дата: 2026-01-31

Цель документа
- Зафиксировать практическую архитектуру agent‑first ассистента, ориентированного на носимые устройства и companion‑clients.  
- Подготовить однозначную карту сервисов, контрактов и приоритетных задач для ближайшей разработки ядра.

Краткая идея
- Система проектируется вокруг автономного персонального агента (Agent Orchestrator). Транскрипция, извлечение задач, семантический поиск и интеграции — это инструменты агента, а не главная ценность.  
- Поддерживается гибкий «privacy first» подход: лёгкая on‑device обработка + облачные воркеры для тяжёлых задач и накопления долговременной памяти.

Контракт (Inputs / Outputs / Success)
- Входы: raw audio/video (stream/file), краткие заметки, метаданные встречи (участники, время), согласия и политики ПДн.  
- Выходы: timecoded transcripts, structured summaries, task objects, meeting proposals, memory entries, audit trail (decision rationale).  
- Условия успеха (примеры, параметры задаются проектом): P95 обработки ≤ N минут; precision(tasks) ≥ 0.8; top‑3 recall ≥ 0.85; ручная обработка снижается ≥ 60%.

Основные компоненты
1) Device Agent (Wearable / Companion App)
  - Capture: запись аудио/видео, локальная сегментация, шумоподавление.
  - Local minimal ASR (опционально) для приватных сценариев.
  - Secure sync: пакетирование артефактов и безопасная отправка в Sync Gateway.
  - Ограничение: энергоэффективность, минимум сетевого трафика.

2) Sync Gateway / Ingest API
  - Аутентификация/авторизация, проверка согласий ПДн.
  - Валидация артефактов, формирование job и вставка в очередь.
  - Exposes OpenAPI для device clients.

3) File Preparer (Preprocessing)
  - Конвертация, нормализация, сегментация, извлечения каналов и checksum.
  - Отдаёт metadata + ссылку на артефакт (S3/FS).

4) Queue + Job Workers
  - Очередь реализована как таблица jobs в Postgres (ADR‑2026‑001) с семантикой транзакций и retry.
  - Воркеры: горизонтально масштабируемые процессы, забирают job и вызывают ASR и Processing.

5) Core Transcriber (ASR)
  - Режимы: on‑device (faster_whisper), локальный microservice (whisper_service.py), cloud worker (tools/di_worker с контролируемым egress).
  - Выдаёт: segments[] {start,end,text,confidence}, model_info, nbest (опционально).

6) Processing Module (LLM Pipeline / Formatter)
  - Chunking/overlap, prompt templates (prompts_catalog.json), LLM orchestration, scoring.
  - Outputs: summaries (multi‑granularity), highlights, candidate tasks, decisions, mapping timestamps → summary.
  - Control loop: score output, request re‑ASR or human review if below threshold.

7) Agent Orchestrator (Decision Layer)
  - LLM‑based controller + rule engine: принимает стратегические решения (compress/expand, create_task/propose_meeting, save_to_LTM).
  - Записывает rationale (why this action) в audit trail для валидации/объяснимости.
  - Интеграции: calendar, task manager, notification channels.

8) Long‑Term Memory (LTM) & Semantic Search
  - Postgres + pgvector (embeddings), memory entries with provenance and links между событиями.
  - API: similarity search, temporal queries, provenance filters.

9) API / Bot / UI Layer
  - `api_server.py` / bot handlers — пользовательский доступ к диалоговому интерфейсу, ручной ревью и запуску agent actions.

10) Governance & Privacy Manager
  - Consent store, privacy profiles: local‑only / embeddings‑only / full‑sync.
  - Data retention policies, key management, audit logs.

Observability & Testing
- Метрики: processing_time P50/P95, cost_per_min, task_precision, recall, job_failure_rate.  
- E2E smoke tests: упрощённый pipeline для одного sample.wav → task suggestion → память создана.

Диаграмма (PlantUML)
```plantuml
@startuml
actor User
package "Device/Edge" {
  [Device Agent]
}
package "Backend" {
  [Sync Gateway]
  [Queue]
  [Worker]
  [Core Transcriber]
  [Processing Module]
  [Agent Orchestrator]
  [LongTerm Memory]
  [Bot/API Server]
}
Device Agent -> Sync Gateway : upload(artifact, metadata)
Sync Gateway -> Queue : create_job
Queue -> Worker : dequeue
Worker -> Core Transcriber : transcribe(file)
Core Transcriber -> Processing Module : raw_transcript
Processing Module -> Agent Orchestrator : structured_outputs
Agent Orchestrator -> LongTerm Memory : upsert(mem_entries)
Agent Orchestrator -> Bot/API Server : propose(task/meeting)
Bot/API Server -> User : notify / request confirmation
@enduml
```

Data flows (stepwise)
1. Capture on device → optional local ASR quick notes.
2. Preparer produces normalized artifact + metadata.
3. Sync Gateway authenticates and creates job in Queue.
4. Worker dequeues → invokes Core Transcriber (local/cloud) → gets segments.
5. Processing Module formats, extracts tasks and summaries.
6. Agent Orchestrator scores, decides, and issues AgentActions.
7. Memory entries saved; user notified or task created.

API contracts (short)
- Job: {id, device_id, file_uri, privacy_profile, prefs, created_at}
- TranscriptionResult: {job_id, segments[], text, model, meta}
- MemoryEntry: {id, embedding, text, source_refs, tags, created_at}
- AgentAction: {type, payload, confidence, rationale, created_at}

Mapping на текущий код (быстро)
- Device/Edge: `tools/transcribe_vpnspace.sh` (runner), нет мобильного SDK — задача.
- Preparer: `tools/audio_prep/`, ffmpeg/yt-dlp скрипты — присутствуют.
- Sync Gateway/API: `api_server.py`, `authorize_bot_api_server.py` — есть базовый сервер.
- Queue & Worker: `transkribator_modules/jobs/queue.py`, `job_worker.py`, alembic migration — есть скелет.
- Core Transcriber: `tools/whisper_service.py`, `transkribator_modules/transcribe/transcriber_v4.py`, `tools/di_worker` — локальные и контейнерные варианты.
- Processing: `transkribator_modules/beta/content_processor.py` — заглушка/чекпоинт.
- Agent: `transkribator_modules/agent/dialog.py` — прототип, требуется decision layer.
- LTM: упоминания pgvector в docs и коде, но нужны миграции/интеграция.

Приоритетные пробелы (MVP focus)
1. Контракты: OpenAPI / JSON схемы для Job / TranscriptionResult / AgentAction.  
2. transcribe_client adapter — унифицировать вызовы ASR.  
3. Processing Module: prompt orchestration + scoring + unit tests.  
4. Agent Orchestrator: простая decision policy + audit trail.  
5. LTM: миграции, ingestion, embedding pipeline.

Mиграционный roadmap (быстро)
- Step 0: Описать JSON схемы и добавить OpenAPI minimal spec в `docs/`.
- Step 1: Добавить `transcribe_client` с двумя адаптерами (local/http, di_worker cli).
- Step 2: Implement Processing pipeline (LLM calls, scoring). Add tests.
- Step 3: Agent Orchestrator (rule+LLM), audit trail, basic integrations.
- Step 4: LTM ingestion, pgvector indices, similarity APIs.

Следующие практические шаги (я могу сделать сразу)
- Записать этот файл `ARCHITECTURE_AGENT_FIRST.md` в корень репо.  
- Удалить старые файлы `ARCHITECTURE.md` и любые явные дубликаты архитектурных заметок (если есть).  
- (по запросу) создать OpenAPI starter и `transcribe_client` шаблон + smoke test.

---
Подпись: документ подготовлен для немедленной фиксации архитектурного взгляда и как основа для разработки ядра.
