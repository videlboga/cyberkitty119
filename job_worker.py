"""Simple CLI entry point for background job workers."""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
import traceback
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from transkribator_modules.config import logger
from transkribator_modules.db import init_db
from transkribator_modules.db.models import ProcessingJob
from transkribator_modules.jobs import (
    acquire_job,
    complete_job,
    fail_job,
    release_job,
)
from transkribator_modules.jobs.handlers import (
    UnknownJobTypeError,
    dispatch_job,
    registry,
)
from transkribator_modules.jobs.queue import mark_job_progress
from transkribator_modules.jobs.bootstrap import register_builtin_handlers
from transkribator_modules.jobs.plan_reminders import send_plan_reminders


class GracefulExit(SystemExit):
    """Sentinel exception used to break out of the worker loop."""


@dataclass(frozen=True)
class WorkerConfig:
    worker_id: str
    poll_interval: float
    job_types: Optional[list[str]] = None
    run_once: bool = False
    service_overrides: Optional[str] = None
    dry_run: bool = False
    max_jobs: Optional[int] = None
    backoff_min: float = 1.0
    backoff_max: float = 30.0
    plan_reminder_interval: float = 1800.0
    enable_plan_reminders: bool = True


class JobWorker:
    """Background worker that pulls jobs from the queue."""

    def __init__(self, config: WorkerConfig) -> None:
        self.config = config
        self._shutdown = False
        self._current_job_id: Optional[int] = None
        self._processed_jobs = 0
        self._failed_jobs = 0
        self._total_job_time = 0.0
        self._start_monotonic = time.monotonic()
        self._last_idle_log = time.monotonic()
        self._max_jobs = config.max_jobs
        self._current_backoff = max(config.backoff_min, 0.1)
        self._next_plan_reminder_check = 0.0

    def start(self) -> None:
        logger.info(
            "Worker starting",
            extra={
                "worker_id": self.config.worker_id,
                "poll_interval": self.config.poll_interval,
                "job_types": self.config.job_types,
            },
        )
        self._start_monotonic = time.monotonic()
        try:
            while not self._shutdown:
                self._maybe_send_plan_reminders()
                job = acquire_job(
                    worker_id=self.config.worker_id,
                    job_types=self.config.job_types,
                )
                if not job:
                    self._sleep()
                    continue

                self._current_job_id = job.id
                self._reset_backoff()
                job_started_at = time.monotonic()
                try:
                    duration = self._process(job)
                    if not self.config.dry_run:
                        complete_job(job.id)
                    else:
                        logger.info(
                            "Dry run enabled; job left in-progress",
                            extra={"job_id": job.id},
                        )
                    self._record_success(duration)
                except GracefulExit:
                    raise
                except Exception as exc:  # noqa: BLE001 - log full traceback
                    failure_duration = time.monotonic() - job_started_at
                    self._record_failure(failure_duration)
                    self._handle_failure(job, exc)
                finally:
                    self._current_job_id = None

                if self.config.run_once:
                    logger.info("Processed single job; stopping as requested.")
                    break
                if self._max_jobs and self._processed_jobs >= self._max_jobs:
                    logger.info(
                        "Max jobs reached; stopping worker",
                        extra={
                            "worker_id": self.config.worker_id,
                            "max_jobs": self._max_jobs,
                        },
                    )
                    break
        except GracefulExit:
            logger.info("Worker received shutdown request.")
        finally:
            self._release_current_job()
            self._log_summary()

    def _sleep(self) -> None:
        timeout = self._current_backoff
        time.sleep(timeout)
        self._increase_backoff()
        now = time.monotonic()
        if now - self._last_idle_log >= max(timeout * 5, 30):
            logger.debug(
                "Worker idle",
                extra={
                    "worker_id": self.config.worker_id,
                    "since_seconds": round(now - self._last_idle_log, 3),
                },
            )
            self._last_idle_log = now

    def _maybe_send_plan_reminders(self) -> None:
        if not self.config.enable_plan_reminders:
            return
        now_monotonic = time.monotonic()
        if now_monotonic < self._next_plan_reminder_check:
            return

        interval = max(self.config.plan_reminder_interval, 300.0)
        try:
            sent = send_plan_reminders()
            if sent:
                logger.info(
                    "Plan reminders dispatched",
                    extra={"count": sent},
                )
        except Exception:  # noqa: BLE001 - log full traceback
            logger.exception("Failed to dispatch plan reminders")
        finally:
            self._next_plan_reminder_check = time.monotonic() + interval

    def _increase_backoff(self) -> None:
        next_value = min(
            self._current_backoff * 2,
            max(self.config.backoff_max, self.config.backoff_min),
        )
        self._current_backoff = max(next_value, self.config.backoff_min)

    def _reset_backoff(self) -> None:
        self._current_backoff = max(self.config.backoff_min, 0.1)

    def _process(self, job: ProcessingJob) -> float:
        logger.info(
            "Processing job",
            extra={"job_id": job.id, "job_type": job.job_type, "user_id": job.user_id},
        )
        mark_job_progress(job.id, progress=0)
        started = time.monotonic()
        if self.config.dry_run:
            logger.info(
                "Dry run: skipping dispatch",
                extra={"job_id": job.id, "job_type": job.job_type},
            )
        else:
            dispatch_job(job)
        duration = time.monotonic() - started
        logger.info(
            "Job processed",
            extra={"job_id": job.id, "duration_seconds": round(duration, 3)},
        )
        return duration

    def _handle_failure(self, job: ProcessingJob, exc: Exception) -> None:
        if isinstance(exc, UnknownJobTypeError):
            available = ", ".join(registry.available()) or "none"
            error_message = f"Unknown job type {exc.job_type}. Registered handlers: {available}"
            logger.error(
                "Job failed: unknown type",
                extra={
                    "job_id": job.id,
                    "job_type": exc.job_type,
                    "worker_id": self.config.worker_id,
                },
            )
        else:
            error_message = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            logger.exception(
                "Job failed",
                extra={"job_id": job.id, "worker_id": self.config.worker_id},
            )
        fail_job(job.id, error_message=error_message)

    def _release_current_job(self) -> None:
        if self._current_job_id is None:
            return
        logger.info(
            "Releasing in-progress job due to shutdown",
            extra={"job_id": self._current_job_id},
        )
        release_job(self._current_job_id)
        self._current_job_id = None

    def request_shutdown(self) -> None:
        self._shutdown = True

    def _record_success(self, duration: float) -> None:
        self._processed_jobs += 1
        self._total_job_time += duration

    def _record_failure(self, duration: float) -> None:
        self._failed_jobs += 1
        self._total_job_time += duration

    def _log_summary(self) -> None:
        runtime = time.monotonic() - self._start_monotonic
        total_jobs = self._processed_jobs + self._failed_jobs
        avg_duration = (
            self._total_job_time / total_jobs if total_jobs else 0.0
        )
        logger.info(
            "Worker summary",
            extra={
                "worker_id": self.config.worker_id,
                "processed_jobs": self._processed_jobs,
                "failed_jobs": self._failed_jobs,
                "total_jobs": total_jobs,
                "runtime_seconds": round(runtime, 3),
                "average_duration_seconds": round(avg_duration, 3),
            },
        )


def parse_job_types(raw: Optional[str], from_flags: Optional[Iterable[str]]) -> Optional[list[str]]:
    combined: set[str] = set()
    if raw:
        combined.update(part.strip() for part in raw.split(",") if part.strip())
    if from_flags:
        combined.update(value.strip() for value in from_flags if value and value.strip())
    return sorted(combined) or None


def build_config(argv: list[str]) -> WorkerConfig:
    parser = argparse.ArgumentParser(description="Transkribator job worker")
    parser.add_argument(
        "--worker-id",
        default=os.environ.get("JOB_WORKER_ID", str(uuid.uuid4())),
        help="Identifier used to mark acquired jobs.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.environ.get("JOB_POLL_INTERVAL", "5")),
        help="Delay in seconds between queue polling attempts.",
    )
    parser.add_argument(
        "--job-type",
        action="append",
        dest="job_types",
        help="Restrict worker to specified job type (can repeat).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one job then exit.",
    )
    parser.add_argument(
        "--service-overrides",
        default=os.environ.get("MEDIA_SERVICE_OVERRIDES"),
        help="Override media services via module:attr mapping provider.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Acquire jobs but skip dispatch and completion.",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=os.environ.get("JOB_MAX_JOBS"),
        help="Stop worker after processing N jobs (useful for debugging).",
    )
    parser.add_argument(
        "--backoff-min",
        type=float,
        default=os.environ.get("JOB_BACKOFF_MIN"),
        help="Minimum idle backoff in seconds when queue is empty.",
    )
    parser.add_argument(
        "--backoff-max",
        type=float,
        default=os.environ.get("JOB_BACKOFF_MAX"),
        help="Maximum idle backoff in seconds when queue is empty.",
    )
    parser.add_argument(
        "--plan-reminder-interval",
        type=float,
        default=None,
        help="Interval in seconds between plan reminder checks (default 1800s).",
    )
    parser.add_argument(
        "--disable-plan-reminders",
        action="store_true",
        help="Disable automatic plan expiration reminders.",
    )
    args = parser.parse_args(argv)

    job_types = parse_job_types(os.environ.get("JOB_TYPES"), args.job_types)
    plan_interval_env = os.environ.get("PLAN_REMINDER_INTERVAL")
    if args.plan_reminder_interval is not None:
        plan_interval = float(args.plan_reminder_interval)
    elif plan_interval_env is not None:
        plan_interval = float(plan_interval_env)
    else:
        plan_interval = 1800.0

    disable_env = os.environ.get("DISABLE_PLAN_REMINDERS", "")
    env_disable = disable_env.lower() in ("1", "true", "yes")

    return WorkerConfig(
        worker_id=str(args.worker_id),
        poll_interval=float(args.poll_interval),
        job_types=job_types,
        run_once=bool(args.once),
        service_overrides=str(args.service_overrides)
        if args.service_overrides
        else None,
        dry_run=bool(args.dry_run),
        max_jobs=int(args.max_jobs) if args.max_jobs else None,
        backoff_min=float(
            args.backoff_min
            if args.backoff_min is not None
            else os.environ.get("JOB_BACKOFF_MIN", 1)
        ),
        backoff_max=float(
            args.backoff_max
            if args.backoff_max is not None
            else os.environ.get("JOB_BACKOFF_MAX", 30)
        ),
        plan_reminder_interval=plan_interval,
        enable_plan_reminders=not (bool(args.disable_plan_reminders) or env_disable),
    )


def install_signal_handlers(worker: JobWorker) -> None:
    def _signal_handler(signum: int, _frame: object) -> None:
        logger.info("Signal received", extra={"signal": signum})
        worker.request_shutdown()
        if worker._current_job_id is None:
            raise GracefulExit()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _signal_handler)


def main(argv: Optional[list[str]] = None) -> int:
    init_db()
    register_builtin_handlers()
    config = build_config(argv or sys.argv[1:])
    if config.service_overrides and not os.environ.get("MEDIA_SERVICE_OVERRIDES"):
        os.environ["MEDIA_SERVICE_OVERRIDES"] = config.service_overrides
    worker = JobWorker(config)
    install_signal_handlers(worker)
    try:
        worker.start()
    except GracefulExit:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

