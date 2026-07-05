---
title: "MVP Gaps — Cyberkitty119 (Transkribator)"
author: "Engineering"
date: 2026-07-05
status: Draft
tags: [mvp, gaps, roadmap, agent, openapi, transcribe_client, ltm]
related: [RESEARCH.md, docs/INVENTORY.md, docs/PROJECT_OVERVIEW.md]
---

# MVP Gaps — Cyberkitty119 (Transkribator)

Five priority gaps between the current codebase and the MVP target for the
"Second Brain" headless API + cognitive agent. Each gap lists its canonical
file paths (verified against the worktree at base commit `0a6273d1`), the
current implementation state, and what remains to close it.

Paths are repo-relative. All paths below were confirmed present in the
worktree unless explicitly marked `(missing)`.

---

## 1. OpenAPI contracts

Canonical path: `openapi.yaml` (missing — no file named `openapi*` exists in
the repo at this commit).

Related real paths:
- `core_api/main.py` — FastAPI app, `title="Second Brain Core API"`,
  `version="2.0.0"`. Routers mounted under `/api/v1/{system,agent,memory,
  ingest,transcribe,internal_bot,payments}`. FastAPI exposes an auto-generated
  spec at `/openapi.json` and Swagger UI at `/docs`, but no static
  `openapi.yaml` is committed, versioned, or consumed by clients.
- `core_api/api/v1/agent.py` — `POST /api/v1/agent/chat` (ReAct loop),
  pydantic models `AgentMessageRequest` / `AgentMessageResponse`.
- `core_api/api/v1/memory.py` — `POST /api/v1/memory/search` (service-token
  guarded), `SearchRequest` model.
- `core_api/api/v1/ingest.py`, `core_api/api/v1/transcribe.py` — ingestion +
  transcription endpoints.
- `core_api/api/v1/internal_bot.py` — `GET /jobs/{job_id}` (raw `job.error`,
  see RESEARCH.md AC2.4).
- `core_api/schemes/` — pydantic response schemas (`system.py`, `auth.py`).

Current state: contracts live only as FastAPI route annotations + pydantic
models inside the Python source. There is no machine-readable, frozen contract
that the miniapp / external clients can pin against. Renaming a field or
changing a status code silently breaks consumers.

Gap to close:
- Export `openapi.json` from the running app (`core_api.main:app`) and commit
  a canonical `openapi.yaml` snapshot under repo root (or `docs/contracts/`).
- Pin the spec in CI: a test that fails when the committed spec diverges from
  the app's live `app.openapi()`.
- Document which fields are stable vs. experimental (e.g. `job.error` raw
  traceback leak — RESEARCH.md AC2.1–AC2.4).
- Add response examples + error envelopes for the 4xx/5xx paths currently
  inlined in routers.

---

## 2. transcribe_client adapter unification

Canonical path: `transcribe_client/__init__.py` — `TranscribeClient`,
`_resolve_default_adapter`, `TranscriptionError`.

Adapter files (all present):
- `transcribe_client/openrouter.py` — `OpenRouterAdapter`
  (`_transcribe_bytes` with retry, chunked `transcribe`).
- `transcribe_client/deepinfra.py` — `DeepInfraAdapter`
  (`_transcribe_file` with retry + own fallback to local whisper).
- `transcribe_client/gpu.py` — `GPUAdapter`.
- `transcribe_client/local.py` — `LocalAdapter` (HTTP whisper via
  `WHISPER_SERVICE_URL`).
- `transcribe_client/di_worker.py` — `DiWorkerAdapter` (container runner).
- `transcribe_client/stub.py` — `StubAdapter` (tests).

Related call sites:
- `transkribator_modules/jobs/services.py:120` — `default_transcribe_media`
  constructs `TranscribeClient(default_mode=TRANSCRIBE_DEFAULT_MODE)` and
  raises `RuntimeError` on `status=error`.
- `transkribator_modules/transcribe/transcriber_v4.py:183` —
  `_try_transcribe_with_client` (the parallel Gemini path lives at line 1799).

Current state: `TranscribeClient.transcribe` (line 126–138) catches exceptions
into `TranscriptionError` but performs **no fallback** between adapters.
`_resolve_default_adapter` picks one adapter in auto-mode (OpenRouter →
DeepInfra → GPU → Local → di_worker → stub) and stops. DeepInfra's own
in-adapter fallback to local whisper is the only cross-provider fallback that
exists today. In `openrouter.py`, `_transcribe_bytes` already retries on
429/502/503/504 for up to 5 attempts with exponential backoff capped at 30s;
however it still lacks jitter, `Retry-After` handling, and the
`{"status": "error", "meta": {"rate_limited": True, ...}}` envelope. The
parallel OpenRouter Gemini path in `transcriber_v4.py:1953` still does a plain
`continue` on 429/500/502/503/504 without any sleep. RESEARCH.md AC1.4–AC1.5
specifies that on persistent 429 / `rate_limited=True` from OpenRouter, the
caller should retry on DeepInfra when `DEEPINFRA_API_KEY` is set — this is not
implemented.

Gap to close:
- Implement OpenRouter 429 retry with exponential backoff + jitter + respect
  `Retry-After` (AC1.1–AC1.3) in `openrouter.py`.
- Return `{"status": "error", "meta": {"rate_limited": True, ...}}` instead
  of raising on exhausted retries (AC1.4).
- Add fallback to DeepInfra in `default_transcribe_media` (services.py) — the
  location recommended by RESEARCH.md Engineering Notes — when
  `result["meta"].get("rate_limited")` is true and `DEEPINFRA_API_KEY` is
  available (AC1.5).
- Backfill the parallel 429 path in `transcriber_v4.py:1953`
  (`transcribe_segment_with_openrouter_gemini`) with
  `await asyncio.sleep(min(2 ** attempt, 30))` before `continue`.
- Keep chunking sequential (AC1.6) — do not introduce `asyncio.gather`.

---

## 3. Processing Module

Canonical path: `core_api/domains/agent/core/content_processor.py`.

Related paths:
- `transkribator_modules/agent/dialog.py` — `ingest_and_prompt`, instantiates
  `ContentProcessor()` at module load (line 19) and drives note creation from
  transcripts / text.
- `core_api/domains/agent/core/presets.py` — preset lookup used by
  `ContentProcessor.process`.
- `core_api/domains/agent/core/llm.py` — `call_agent_llm` / `call_agent_llm_
  with_retry` (OpenRouter chat client shared with the agent).
- `tests/test_content_processor.py` — existing tests for this module.

Current state: `ContentProcessor.process()` (line 55–73) is an explicit stub:
it logs `"ContentProcessor.process() is a stub - feature not fully
implemented"` and returns a placeholder `{"summary": "Обработка выполнена",
"tags": tags or [], "status": status}`. Real summary/tag generation logic
(`_build_summary_and_tags`, `_unwrap_json_content`, front-matter helpers)
lives as module-level functions further down the same file (line 76+). The
INVENTORY.md row for this file marks status `core/stub` and flags the split.

Gap to close:
- Wire `ContentProcessor.process()` to the real `_build_summary_and_tags`
  path (or mark the class deprecated and route `dialog.py` directly to the
  functions) — pick one shape and make it consistent.
- Tighten summary prompts to forbid fact invention (INVENTORY.md §3,
  "Саммари `notes.summary`" risk: date/price fabrication).
- Add post-validation: detect repeated-token artefacts ("та-та-та") and
  gross length/content drift between source and summary.
- Expand `tests/test_content_processor.py` with long-meeting + repeated-token
  regressions.

---

## 4. Agent Orchestrator

Canonical path: `core_api/domains/agent/core/agent_runtime.py` —
`AgentSession`, `AgentManager` (exported as `AGENT_MANAGER`), ReAct loop.

Related paths:
- `core_api/api/v1/agent.py` — `POST /api/v1/agent/chat` calls
  `AGENT_MANAGER` with a `TelegramUserProxy`.
- `core_api/domains/agent/core/tools.py` — `AgentTool`, `ToolResult`,
  `get_tool_specs`, `resolve_tool`, `_looks_like_question`.
- `core_api/domains/agent/core/prompts.py` — `build_system_prompt`,
  `build_event_message` (JSON contract: `response` / `actions` /
  `suggestions`).
- `core_api/domains/agent/core/llm.py` — OpenRouter chat client for the
  agent (separate from the ASR OpenRouter path).
- `core_api/domains/agent/persistence.py` — `AgentPersistenceGateway`,
  `NoteSnapshot` (DB read/write for notes).
- `core_api/domains/agent/session_store.py` — `AgentSessionStore` +
  `InMemoryAgentSessionStore` (+ optional Redis backend).
- `transkribator_modules/agent/dialog.py` — legacy Telegram-side
  `ingest_and_prompt` that predates the headless orchestrator.

Current state: a MemGPT-inspired `AgentSession` + `AgentManager` already
implements a ReAct loop with tool dispatch, persistence via
`AgentPersistenceGateway`, session state via `AgentSessionStore`, and a
strict JSON response contract. It is exposed headlessly through
`/api/v1/agent/chat`. The Telegram path (`dialog.py`) still runs its own
`ingest_and_prompt` flow in parallel, so there are two entry points into
agent behaviour that need to converge.

Gap to close:
- Unify the Telegram path (`dialog.py`) onto the headless
  `AGENT_MANAGER.chat()` so the orchestrator is the single source of truth
  for both Web UI and bot.
- Stabilise the tool registry contract (input/output schemas) so it can be
  reflected into the OpenAPI spec (gap #1).
- Add orchestrator-level tests: multi-turn ReAct, tool failure handling,
  session eviction, and the fallback-message builders at
  `agent_runtime.py:776+` (`_build_fallback_message`,
  `_fallback_for_ingest`, `_fallback_for_user`).
- Decide and document session TTL / storage backend (in-memory vs Redis vs
  DB) for production.

---

## 5. LTM (Long-Term Memory / vector store)

Canonical paths:
- `alembic/versions/0003_pgvector_note_chunks.py` — creates `note_chunks`
  table with `pgvector` `Vector(256)` + `CREATE EXTENSION vector`.
- `alembic/versions/0004_pgvector_dim_1536.py` — widens `embedding` column
  to `Vector(1536)` (matches OpenAI text-embedding dimension).
- `alembic/versions/0009_note_qa_sessions.py` — `note_qa_sessions` +
  `note_qa_messages` (per-note conversational memory).
- `wheelhouse/pgvector-0.2.4-py2.py3-none-any.whl` — vendored pgvector
  client wheel.

Service paths:
- `core_api/domains/memory/search_service.py` — `MemorySearchService`
  (domain wrapper) with `MemorySearchResult`, error taxonomy
  (`MemorySearchError` / `ValidationError` / `ServiceError`).
- `core_api/api/v1/memory.py` — `POST /api/v1/memory/search`
  (service-token guarded).
- `transkribator_modules/search/service.py` — `run_note_search`,
  `NoteSearchSpec`, `NoteSearchError` (legacy search core that
  `MemorySearchService` delegates to).
- `transkribator_modules/search/index.py` — `IndexService`
  (embedding/index maintenance).
- `transkribator_modules/search/embeddings.py` — embedding generation.
- `transkribator_modules/search/reranker.py` — reranker.

Current state: the vector store is real and migrated. `note_chunks` exists
with 1536-dim embeddings; `note_qa_sessions` gives notes their own Q&A
threads. `MemorySearchService` is a thin domain layer over the legacy
`run_note_search`, exposed via a guarded endpoint. What is missing for MVP
is not the storage but the operational layer around it.

Gap to close:
- Add ingestion-side wiring: every saved note must be chunked + embedded
  into `note_chunks` automatically (verify the write path in
  `IndexService` / `dialog.py` — currently best-effort, not guaranteed).
- Expose LTM recall as an agent tool (so the orchestrator in gap #4 can pull
  memories during ReAct) instead of only via the standalone
  `/api/v1/memory/search` endpoint.
- Add pgvector health/migration test: assert `0003` + `0004` apply cleanly
  on a fresh DB and that `Vector(1536)` is the live dimension.
- Document the embedding model + dimension contract (1536 implies
  `text-embedding-3-small` / `text-embedding-ada-002` family) so a model
  swap is a flagged migration, not a silent dimension mismatch.
- Add recall-quality regression tests (recall@k for known queries) so
  prompt/embedding drift is caught.

---

## Summary table

| # | Gap | Canonical path | Status |
|---|-----|----------------|--------|
| 1 | OpenAPI contracts | `openapi.yaml` (missing) → `core_api/main.py` + `core_api/api/v1/*.py` | No committed spec; only FastAPI auto-gen |
| 2 | transcribe_client unification | `transcribe_client/__init__.py` + adapters | Adapters exist; `openrouter.py` now retries on 429/502/503/504 with exponential backoff capped at 30s (max 5 attempts). `transcriber_v4.py` gemini 429 path still has no backoff sleep. No cross-adapter fallback to DeepInfra yet. |
| 3 | Processing Module | `core_api/domains/agent/core/content_processor.py` | `ContentProcessor.process()` is a stub; real logic sits in module functions |
| 4 | Agent Orchestrator | `core_api/domains/agent/core/agent_runtime.py` | ReAct loop + headless endpoint exist; Telegram path not yet unified |
| 5 | LTM | `alembic/versions/0003_*`, `0004_*`, `0009_*` + `core_api/domains/memory/search_service.py` | Vector store migrated; agent-tool wiring + ingestion guarantee missing |