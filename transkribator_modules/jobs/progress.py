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
        self._current_stage: Optional[str] = None
        self._stage_label: Optional[str] = None
        self._stage_progress: Optional[int] = None

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

    def set_stage(
        self,
        stage: str,
        *,
        progress: Optional[int] = None,
        label: Optional[str] = None,
    ) -> None:
        """Update current stage metadata for richer UI feedback."""
        normalized = None if progress is None else max(0, min(100, int(progress)))
        if (
            stage == self._current_stage
            and normalized == self._stage_progress
            and (label is None or label == self._stage_label)
        ):
            return

        self._current_stage = stage
        if label is not None:
            self._stage_label = label
        if normalized is not None:
            self._stage_progress = normalized

        mark_job_progress(
            self.job_id,
            stage=stage,
            stage_progress=normalized,
            stage_label=label or self._stage_label,
        )
        logger.debug(
            "Job stage updated",
            extra={
                "job_id": self.job_id,
                "stage": stage,
                "stage_progress": normalized,
            },
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
