"""Registry for background job handlers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional

from transkribator_modules.db.models import ProcessingJob


class UnknownJobTypeError(KeyError):
    """Raised when no handler is registered for the requested job type."""

    def __init__(self, job_type: str) -> None:
        super().__init__(job_type)
        self.job_type = job_type


JobHandler = Callable[[ProcessingJob], None]


@dataclass
class JobHandlerRegistry:
    """Holds mapping of job types to callables."""

    _handlers: MutableMapping[str, JobHandler] = field(default_factory=dict)

    def register(self, job_type: str, handler: JobHandler, *, force: bool = False) -> None:
        """Register a handler."""
        if not force and job_type in self._handlers:
            raise ValueError(f"Handler for job type '{job_type}' already registered.")
        self._handlers[job_type] = handler

    def unregister(self, job_type: str) -> None:
        self._handlers.pop(job_type, None)

    def dispatch(self, job: ProcessingJob) -> None:
        handler = self._handlers.get(job.job_type)
        if not handler:
            raise UnknownJobTypeError(job.job_type)
        handler(job)

    def get(self, job_type: str) -> Optional[JobHandler]:
        return self._handlers.get(job_type)

    def available(self) -> Iterable[str]:
        return tuple(sorted(self._handlers.keys()))

    def snapshot(self) -> Mapping[str, JobHandler]:
        return dict(self._handlers)


registry = JobHandlerRegistry()


def register_handler(job_type: str, handler: JobHandler, *, force: bool = False) -> None:
    registry.register(job_type, handler, force=force)


def unregister_handler(job_type: str) -> None:
    registry.unregister(job_type)


def dispatch_job(job: ProcessingJob) -> None:
    registry.dispatch(job)


def get_handler(job_type: str) -> Optional[JobHandler]:
    return registry.get(job_type)


__all__ = [
    "JobHandler",
    "JobHandlerRegistry",
    "UnknownJobTypeError",
    "dispatch_job",
    "get_handler",
    "register_handler",
    "registry",
    "unregister_handler",
]
