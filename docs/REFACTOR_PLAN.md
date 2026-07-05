---
title: "Refactor Plan — Cyberkitty119 (Transkribator)"
author: "Engineering"
date: 2026-07-05
status: Draft
tags: [refactor, roadmap, tech-debt, mvp, phased]
related: [RESEARCH.md, docs/TECH_DEBT_REGISTER.md, docs/MVP_GAPS.md, docs/PROJECT_OVERVIEW.md]
---

# Refactor Plan — Cyberkitty119 (Transkribator)

Phased roadmap derived from `docs/TECH_DEBT_REGISTER.md` (TDR) and
`docs/MVP_GAPS.md` (MVP). Phases are ordered by dependency and risk:
low-risk prune first, cross-cutting hygiene next, monolith splits last,
MVP-feature wiring on top of the cleaned substrate.

Each phase lists: scope, affected files, debt-register / MVP-gap
references, and an acceptance check. A phase is "done" when its
acceptance check passes and `make test` is green.

## Conventions

- Paths are repo-relative and were verified against the worktree at base
  commit `2d3e1fd6`.
- "TDR §N" refers to section N of `docs/TECH_DEBT_REGISTER.md`.
- "MVP #N" refers to gap N in `docs/MVP_GAPS.md`.
- "AC x.y" refers to acceptance criteria in `RESEARCH.md`.
- Every phase MUST keep `make test` (`pytest -q`) green and must not
  break the production DeepInfra primary path
  (`TRANSCRIBE_DEFAULT_MODE=deepinfra`).
- No commit / push in these phases unless explicitly requested; changes
  stay in the worktree.

---

## Phase 0 — Dead-code & artifact prune (low risk)

**Goal:** remove verifiably-unused code and historical artifacts so the
repo surface shrinks before any structural work. No runtime behaviour
change for production paths.

**Scope:**
- Delete the duplicated dead chunked-transcription block in
  `transcribe_client/openrouter.py` if it is still present (RESEARCH.md
  Engineering Notes and TDR §2 flagged lines ~256–314 as unreachable after
  the `return` on line 243). Re-verify after each run because the file has
  already been edited by previous engineering commits.
- Classify and remove one-shot patch/fix scripts at repo root:
  `patch_*.py`, `fix_*.py`, `insert_qa_callback.py`, `patcher.py`,
  `strangel.py`, `test3.py`, `tmp_core.py`, and stray `*.bak` /
  `*.new` / `*.disabled` files that are confirmed unused. Keep a short
  deletion log in the PR description.
- Remove stale `miniapp_dist/**` build artifacts if a different build
  is the one served in prod (TDR §6). If the served build is unclear,
  defer to Phase 1 and only delete here what is unambiguous.
- Leave `verified-removed` TDR entries alone (root `handlers.py`,
  nested `transkribator_modules/transkribator_modules/**`) — they are
  already gone; this phase only prunes what is still present.

**Affected files:**
- `transcribe_client/openrouter.py` (re-check dead block)
- repo-root `patch_*.py`, `fix_*.py`, misc one-off scripts
- `miniapp_dist/**` (conditional)

**References:**
- TDR §2 (`transcribe_client/` dead block)
- TDR §6 (`miniapp/**`, `miniapp_dist/**`)
- TDR §7 (`setup_and_build.sh`, `deploy*.sh`, `scripts/**`)
- RESEARCH.md Engineering Notes (`openrouter.py` lines 256–314)

**Acceptance check:**
- `make test` green.
- `grep -n "def transcribe" transcribe_client/openrouter.py` shows a
  single `transcribe` method with no unreachable second chunked block.
- No production import path references a deleted script (verified via
  `grep -R` over `transkribator_modules/`, `core_api/`, `transcribe_client/`).
- Deletion log lists every removed file with a one-line reason.

---

## Phase 1 — Compose & Dockerfile unification

**Goal:** collapse the sprawl of `docker-compose.*.yml` and
`Dockerfile*` variants to one canonical prod topology plus clearly
labelled dev/test files.

**Scope:**
- Designate `docker-compose.bot-v2.yml` as the single prod compose
  (already canonical per `docs/PROJECT_OVERVIEW.md`).
- For every other `docker-compose.*.yml` in the repo: either move it
  under `docker/` with a `dev/` / `test/` / `legacy/` prefix, or delete
  if truly unused. `.disabled` files are the primary deletion
  candidates.
- Same for `Dockerfile.*`: keep `Dockerfile.bot-v2`, `Dockerfile.api`,
  `Dockerfile` (worker). Remove or archive `Dockerfile.apt-cacher`,
  `Dockerfile.knowledge`, `Dockerfile.local`, `Dockerfile.simple-bot`,
  `Dockerfile.telegram-bot-api`, `Dockerfile.gpu-worker`,
  `Dockerfile.postgres`, `Dockerfile.whisper-gpu` if unused in prod.
- Update `Makefile` docker targets to reference only the canonical
  compose file; remove dead targets.

**Affected files:**
- `docker-compose.*.yml`, `Dockerfile*`
- `Makefile` (docker targets)
- `docs/PROJECT_OVERVIEW.md` (deploy topology table — refresh if
  files move)

**References:**
- TDR §1 (`docker-compose.yml` row)
- TDR §7 (`Dockerfile*`, `docker-compose.*.yml`)
- MVP #1 (stable deploy topology underpins the OpenAPI contract)

**Acceptance check:**
- `docker compose -f docker-compose.bot-v2.yml config` validates
  without warnings about missing files.
- Exactly one compose file at repo root for prod; all others are under
  `docker/` or deleted.
- `make start-docker` / `make stop-docker` still work against the
  canonical file.
- `make test` green.

---

## Phase 2 — Logging standardization

**Goal:** make every key log line in the transcription and job flows
carry `user_id`, `media_id` / `job_id`, and a stage tag in a single
structured message so a full trace can be reconstructed from logs
alone.

**Scope:**
- Define a logging convention: `logger.info("stage ...", extra={
  "user_id": ..., "job_id": ..., "media_id": ..., "stage": ...})`
  using the existing `logger` from `transkribator_modules.config`.
- Audit and align log calls in:
  `job_worker.py` (`_handle_failure`, `dispatch_job`),
  `transkribator_modules/jobs/pipeline.py` (`run_media_pipeline`
  stage boundaries),
  `transkribator_modules/jobs/services.py`
  (`default_transcribe_media`, `default_deliver_results`),
  `transcribe_client/__init__.py` (`TranscribeClient.transcribe`),
  `transcribe_client/openrouter.py` and `deepinfra.py` retry lines,
  `transkribator_modules/transcribe/transcriber_v4.py`
  (`_try_transcribe_with_client`, gemini 429 path).
- Do NOT introduce a new logging library; reuse `logging` + `extra=`.
- Document the convention in `docs/PROJECT_OVERVIEW.md` (or a short
  `docs/LOGGING.md` if the team prefers).

**Affected files:**
- `job_worker.py`
- `transkribator_modules/jobs/pipeline.py`
- `transkribator_modules/jobs/services.py`
- `transkribator_modules/jobs/queue.py`
- `transcribe_client/__init__.py`, `openrouter.py`, `deepinfra.py`
- `transkribator_modules/transcribe/transcriber_v4.py`

**References:**
- TDR §7 (`LOGGING_IMPROVEMENTS.md`, `logs/*`, `docker_journal.log`)
- AC1.3 (retry logging with `extra={...}`)
- MVP #2 (observability around adapter failures)

**Acceptance check:**
- A simulated job (stub adapter) produces log lines where every
  stage-transition message contains `user_id`, `job_id`, and `stage`.
- `make test` green.
- No new logging dependency added.

---

## Phase 3 — Error / traceback hygiene (cross-cutting)

**Goal:** stop leaking raw tracebacks to users and register the missing
PTB error handler. This is lower risk than the monolith splits and
unblocks safer iterations of handlers afterwards.

**Scope:**
- `job_worker.py:_handle_failure` — store
  `f"{type(exc).__name__}: {str(exc)[:500]}"` in `job.error` instead of
  the full traceback. Full traceback stays in `logger.exception` (AC2.1).
- `transkribator_modules/jobs/queue.py:fail_job` — sanitize: if
  `"Traceback (most recent call last)" in error_message` → replace
  with `"Internal processing error"` (AC2.2, defence-in-depth).
- Replace raw `job.error` display with friendly messages:
  `max_bot/native_handlers.py:203`, `max_bot/native_service.py:63`,
  `transkribator_modules/bot/handlers.py:1358,1360` (AC2.3).
- `transkribator_modules/main.py` — register
  `application.add_error_handler(_error_handler)` after the last
  handler; handler logs via `logger.exception` and sends a friendly
  message only when `update.effective_chat` is present (AC3.1–AC3.2).
- Add early-return guards in `handle_message` and the
  `update.message.from_user` call sites in `bot/commands.py` for
  `update.effective_user is None` / `update.message is None` (AC3.3).
- API endpoints (`internal_bot.py:61`, `media_service.py:104`) — keep
  returning `job.error` (now sanitized) but document that miniapp
  should show it only in debug mode (AC2.4 — recommendation, not
  blocking).

**Affected files:**
- `job_worker.py`
- `transkribator_modules/jobs/queue.py`
- `max_bot/native_handlers.py`, `max_bot/native_service.py`
- `transkribator_modules/bot/handlers.py`
- `transkribator_modules/main.py`
- `transkribator_modules/bot/commands.py`
- `core_api/api/v1/internal_bot.py`,
  `core_api/domains/ingestion/media_service.py` (doc only)

**References:**
- TDR §5 (`processing_jobs` `job.error` raw traceback)
- TDR §8 (`main.py` error handler, `max_bot` raw error, handlers 1358/1360)
- AC2.1–AC2.4, AC3.1–AC3.3
- MVP #1 (`job.error` field stability for the OpenAPI contract)

**Acceptance check:**
- New tests pass:
  `tests/test_fail_job_sanitize.py` (traceback input → no "Traceback"
  in `job.error`),
  `tests/test_error_handler.py` (mock Application, `_error_handler`
  logs and does not crash on `update is None`).
- Manual / scripted check: a forced transcription failure produces a
  `job.error` like `RuntimeError: Transcription failed: ...` with no
  `Traceback (most recent call last)` substring.
- `make test` green.

---

## Phase 4 — transcribe_client hardening (429 backoff + fallback)

**Goal:** make OpenRouter retry resilient and add the missing
DeepInfra fallback, closing the reliability half of MVP #2 before the
transcriber split touches the same code.

**Scope:**
- `transcribe_client/openrouter.py`:
  - `max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "6"))`
    (AC1.1).
  - Retry explicitly on 429/502/503/504 with exponential backoff
    `min(2 ** attempt, 30)` + jitter `random.uniform(0, backoff*0.1)`,
    respecting `Retry-After` (cap 60s) (AC1.2).
  - Each retry logged via `logger.warning(extra={"attempt": N,
    "status": ..., "backoff_sec": X})` (AC1.3, builds on Phase 2
    logging).
  - On exhausted retries return
    `{"status": "error", "meta": {"rate_limited": True, ...}}`
    instead of raising (AC1.4).
  - Keep chunking sequential — do NOT introduce `asyncio.gather`
    (AC1.6).
- `transkribator_modules/jobs/services.py:default_transcribe_media` —
  on `result["status"] == "error"` with
  `result["meta"].get("rate_limited")` and `DEEPINFRA_API_KEY` set,
  construct `TranscribeClient(default_mode="deepinfra")` and retry.
  Log the fallback (AC1.5).
- `transkribator_modules/transcribe/transcriber_v4.py:1953` — add
  `await asyncio.sleep(min(2 ** attempt, 30))` before `continue` on
  429 in the parallel Gemini path (RESEARCH.md Engineering Notes).

**Affected files:**
- `transcribe_client/openrouter.py`
- `transkribator_modules/jobs/services.py`
- `transkribator_modules/transcribe/transcriber_v4.py` (only the 429
  site at ~line 1953; full split is Phase 5)

**References:**
- TDR §2 (`transcribe_client/`, `transcribe_segment_with_openrouter_gemini`)
- MVP #2 (transcribe_client adapter unification)
- AC1.1–AC1.6

**Acceptance check:**
- New test `tests/test_openrouter_retry.py` passes: mock `requests.post`
  returning 429 N times → retry count, backoff delays (mocked
  `time.sleep`), final return `{"status": "error", "meta":
  {"rate_limited": True}}`.
- New test for fallback: stub OpenRouter returning `rate_limited=True`
  → `default_transcribe_media` invokes DeepInfra adapter.
- `make test` green; production DeepInfra primary path unchanged.

---

## Phase 5 — Split `transcriber_v4.py`

**Goal:** decompose the 1987-line monolith into focused modules so
ASR, chunking, formatting, and header logic can evolve and be tested
independently. This is a high-risk structural change, so it comes after
the reliability and hygiene phases that touch the same file.

**Scope:**
- Extract from `transkribator_modules/transcribe/transcriber_v4.py`
  into sibling modules under `transkribator_modules/transcribe/`:
  - `asr.py` — `_try_transcribe_with_client` and the
    `transcribe_segment_with_openrouter_gemini` /
    `transcribe_whole_audio_with_gemini` path.
  - `chunking.py` — audio chunk preparation / splitting helpers.
  - `formatting.py` — `format_transcript_with_openrouter` (line 590)
    and related LLM formatting.
  - `headers.py` — transcript header / metadata assembly.
- Remove/commented-out DeepInfra logic that is dead since
  `transcribe_client` became the path (TDR §2).
- Keep a thin `transcriber_v4.py` as the public façade re-exporting the
  previous public names so existing import sites
  (`services.py`, `pipeline.py`) do not break.

**Affected files:**
- `transkribator_modules/transcribe/transcriber_v4.py` (shrunk to façade)
- new `transkribator_modules/transcribe/asr.py`, `chunking.py`,
  `formatting.py`, `headers.py`
- `transkribator_modules/jobs/services.py` (imports unchanged if façade
  re-exports)

**References:**
- TDR §2 (`transcriber_v4.py` monolith, `format_transcript_with_llm`
  artefact risk)
- MVP #2 (parallel 429 path lives here)

**Acceptance check:**
- `transcriber_v4.py` ≤ ~300 lines (façade only).
- Each new module ≤ ~500 lines and has at least one focused unit test.
- Existing tests (`tests/test_transcribe_client.py`,
  `tests/test_formatting.py`, `tests/test_raw_transcript.py`) pass
  unchanged against the façade.
- `make test` green.
- No public symbol rename without a deprecation alias for one release.

---

## Phase 6 — Split `bot/handlers.py`

**Goal:** break the 2262-line handler file into per-flow submodules so
the bot can be maintained without cross-flow conflicts. Depends on
Phase 3 (error handler + guards) being in place first.

**Scope:**
- Split `transkribator_modules/bot/handlers.py` into:
  - `transkribator_modules/bot/flows/audio.py` —
    `process_audio_file`, `_process_external_audio`.
  - `transkribator_modules/bot/flows/video.py` —
    `process_video_file`.
  - `transkribator_modules/bot/flows/text.py` —
    `handle_message` and text-only flows.
  - `transkribator_modules/bot/flows/agent.py` — agent/beta-flagged
    handlers (`AGENT_FIRST`, beta branches).
- Prune unused/obsolete handlers and dead beta flags identified in
  TDR §4.
- Keep `handlers.py` as a thin re-export shim so `main.py` handler
  registration keeps working.
- Ensure Phase 3 guards (`effective_user`/`message` None-checks) are
  present in every moved handler.

**Affected files:**
- `transkribator_modules/bot/handlers.py` (shim)
- new `transkribator_modules/bot/flows/{audio,video,text,agent}.py`
- `transkribator_modules/main.py` (imports via shim — no change
  expected)

**References:**
- TDR §1 (`bot/handlers.py` 2262 lines)
- TDR §4 (dialog/menu split, beta branches)
- AC3.3 (None-checks across handlers)

**Acceptance check:**
- `handlers.py` ≤ ~150 lines (re-export shim).
- Each flow module ≤ ~600 lines.
- A smoke test (or manual bot start) confirms `handle_message`,
  audio, video, and callback flows still route correctly.
- `make test` green; any new handler-level unit tests pass.

---

## Phase 7 — MVP feature wiring (on cleaned substrate)

**Goal:** close the five MVP gaps on top of the now-cleaned, split,
logged, and error-safe codebase. These are feature additions, not pure
refactor, but they depend on Phases 3–6 being complete.

**Sub-phases (can be parallelised after Phase 6):**

**7a — OpenAPI contracts (MVP #1)**
- Export `openapi.json` from `core_api.main:app`, commit a canonical
  `openapi.yaml` under `docs/contracts/`.
- Add a CI test that fails when the committed spec diverges from
  `app.openapi()`.
- Document stable vs. experimental fields (notably `job.error`, now
  sanitized by Phase 3).
- Add response examples + error envelopes for 4xx/5xx paths.

**7b — Processing Module (MVP #3)**
- Wire `ContentProcessor.process()` to the real `_build_summary_and_tags`
  path (or deprecate the class and route `dialog.py` to the functions
  directly — pick one).
- Tighten summary prompts to forbid fact invention (TDR §3 notes
  summary risk).
- Add post-validation: repeated-token artefacts ("та-та-та"),
  length/content drift between source and summary.
- Expand `tests/test_content_processor.py` with long-meeting +
  repeated-token regressions.

**7c — Agent Orchestrator unification (MVP #4)**
- Unify the Telegram path (`transkribator_modules/agent/dialog.py`)
  onto the headless `AGENT_MANAGER.chat()` so the orchestrator is the
  single entry point for both Web UI and bot.
- Stabilise the tool registry contract (input/output schemas) for
  reflection into the OpenAPI spec (feeds 7a).
- Add orchestrator tests: multi-turn ReAct, tool failure handling,
  session eviction, fallback-message builders
  (`agent_runtime.py:776+`).
- Decide and document session TTL / storage backend for production.

**7d — LTM wiring (MVP #5)**
- Guarantee every saved note is chunked + embedded into `note_chunks`
  (verify `IndexService` / `dialog.py` write path; make it mandatory,
  not best-effort).
- Expose LTM recall as an agent tool so the orchestrator (7c) can pull
  memories during ReAct.
- Add a pgvector health/migration test: `0003` + `0004` apply cleanly
  on a fresh DB; `Vector(1536)` is the live dimension.
- Document the embedding model + dimension contract so a model swap is
  a flagged migration.
- Add recall-quality regression tests (recall@k for known queries).

**Affected files (summary):**
- new `docs/contracts/openapi.yaml`, CI workflow
- `core_api/domains/agent/core/content_processor.py`,
  `transkribator_modules/agent/dialog.py`
- `core_api/domains/agent/core/agent_runtime.py`,
  `core_api/domains/agent/core/tools.py`
- `transkribator_modules/search/index.py`,
  `core_api/domains/memory/search_service.py`
- `tests/**` (new tests for each sub-phase)

**References:**
- MVP #1, #3, #4, #5
- TDR §3 (LLM notes / summary), TDR §5 (DB), TDR §6 (API)

**Acceptance check:**
- 7a: CI spec-divergence test passes; `openapi.yaml` committed.
- 7b: `ContentProcessor.process()` no longer logs the stub message;
  new regressions pass.
- 7c: `dialog.py` delegates to `AGENT_MANAGER.chat()`; orchestrator
  tests pass.
- 7d: a saved note produces `note_chunks` rows; recall@k test passes;
  pgvector migration test passes on a fresh DB.
- `make test` green overall.

---

## Phase ordering & dependencies

```
Phase 0 (prune) ─┐
                 ├─► Phase 1 (compose) ─► Phase 2 (logging) ─► Phase 3 (errors) ─► Phase 4 (transcribe_client) ─► Phase 5 (split transcriber_v4) ─► Phase 6 (split handlers) ─► Phase 7 (MVP wiring: 7a/7b/7c/7d)
Phase 0 (prune) ─┘
```

- Phase 0 and Phase 1 are independent of each other and can run in
  parallel.
- Phase 2 (logging) should precede Phase 4 so the retry logs land in
  the standardized format.
- Phase 3 (errors) should precede Phase 6 so moved handlers inherit
  guards.
- Phase 4 should precede Phase 5 because both touch the same
  transcribe files; hardening first avoids rework inside the split.
- Phase 5 should precede Phase 6 to reduce concurrent risk on two
  monoliths at once.
- Phase 7 depends on all of 0–6 (cleaned substrate); its sub-phases
  7a–7d can be parallelised after Phase 6.

## Risk summary

| Phase | Risk   | Why |
|-------|--------|-----|
| 0     | Low    | Pure deletion of verified-dead code. |
| 1     | Low-Med| Compose/Dockerfile moves can break deploy if misclassified; mitigated by `config` validation. |
| 2     | Low    | Log-call edits only; no behaviour change. |
| 3     | Med    | Touches user-facing error messages and adds PTB error handler; needs the new tests. |
| 4     | Med    | Changes retry/fallback behaviour of a production path; guarded by new tests and the constraint not to break DeepInfra primary. |
| 5     | High   | Splits a 1987-line monolith; mitigated by façade re-exports and existing tests. |
| 6     | High   | Splits a 2262-line monolith; mitigated by guards from Phase 3 and a re-export shim. |
| 7     | Med    | Feature additions on a cleaned base; each sub-phase isolated. |

## Source & maintenance

- Derived from `docs/TECH_DEBT_REGISTER.md` and `docs/MVP_GAPS.md`,
  cross-checked against `RESEARCH.md` acceptance criteria and
  `docs/PROJECT_OVERVIEW.md` file paths.
- When a phase completes, move its TDR rows to the "Разрешённые"
  section with commit reference (per TDR maintenance policy), and
  update `docs/MVP_GAPS.md` status column.
- This plan is a living document: re-baseline after each phase.