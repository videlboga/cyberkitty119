"""Utilities for reporting job progress."""

from __future__ import annotations

from typing import Optional

from transkribator_modules.config import logger

from .queue import mark_job_progress


class JobNotifier:
    """Helper that updates progress and logs status messages."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self._last_progress: Optional[int] = None

    def set_progress(self, progress: Optional[int]) -> None:
        """Persist progress value (0..100)."""
        if progress is None:
            normalized = None
        else:
            normalized = max(0, min(100, int(progress)))
        if normalized == self._last_progress:
            return
        mark_job_progress(self.job_id, progress=normalized)
        self._last_progress = normalized
        logger.debug(
            "Job progress updated",
            extra={"job_id": self.job_id, "progress": normalized},
        )

    def notify(self, message: str, *, level: str = "info") -> None:
        """Emit a status message (currently logs, hook for Telegram updates later)."""
        log_method = getattr(logger, level.lower(), None)
        if log_method is None:
            log_method = logger.info
        log_method(
            "Job notification",
            extra={"job_id": self.job_id, "detail": message},
        )


__all__ = ["JobNotifier"]
