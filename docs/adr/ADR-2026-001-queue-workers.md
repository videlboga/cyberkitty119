---
title: "ADR-2026-001: Queue + Worker architecture for media processing"
author: "<your-name>"
date: 2026-01-25T00:00:00Z
status: Draft
tags: [architecture, queue, workers]
related: []
---

# ADR-2026-001: Queue + Worker architecture for media processing

## Context

Currently the bot does significant synchronous work when receiving media: download, audio extraction, transcription and formatting. This couples the Telegram update loop with heavy IO/CPU tasks and is fragile to timing races (e.g. local cache not yet written by the local bot-api) and network egress issues (WireGuard/IPv6). Logs and local debugging show intermittent failures and a fragile path from upload -> cache -> bot download -> transcription.

We need a clear separation: bot stays a thin front-end, heavy processing runs in background workers. This ADR describes that design and the migration plan.

## Decision

Adopt a queue + worker architecture. The bot will enqueue media processing jobs into a durable queue (initially a Postgres table `processing_jobs`). Background worker processes will dequeue, process, update status and notify users.

Rationale:
- Minimal infra changes (use existing Postgres); easy to migrate to Redis/RabbitMQ later.
- Durable, observable job records (status, progress, error) make debugging and retries possible.
- Workers scale independently from bot.

## Consequences

- Add new DB table `processing_jobs` and DAO layer.
- Introduce `job_worker.py` process and `transkribator_modules/jobs/*` package.
- Update bot handlers to call `enqueue_job()` and return early to users.
- Add structured logging with `job_id`, `user_id`, `media_id` on key events.

## Migration plan (high level)

1. Add Alembic migration to create `processing_jobs` table (non-destructive).
2. Add DAO skeleton and unit tests for enqueue/dequeue semantics.
3. Implement `job_worker.py` (dry-run mode) and `process_media_job(job)` which reuses existing media-processing utilities.
4. Change bot handlers to enqueue jobs instead of performing long-running processing inline.
5. Run smoke tests, monitor, and roll out to staging before production.

## Rollback

If problems occur, stop enqueueing (short patch to bot to restore previous behavior) and revert worker changes. The DB migration is additive and can be dropped.

## Criteria for success

- Bot responds instantly after upload and creates a `processing_jobs` record.
- Worker(s) process jobs and create `transcriptions` records.
- Reduced occurrences of the race where bot logs show `getFile local failed` without eventual processing.
