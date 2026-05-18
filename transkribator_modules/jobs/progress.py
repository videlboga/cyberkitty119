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
        self._stage_window: Optional[tuple[int, int]] = None

    def set_progress(self, progress: Optional[int]) -> None:
        """Persist progress value (0..100)."""
        if progress is None:
            normalized = None
        else:
            normalized = max(0, min(100, int(progress)))
        stage_progress_update: Optional[int] = None
        if normalized is not None and self._stage_window is not None:
            start, end = self._stage_window
            span = max(end - start, 1)
            if normalized <= start:
                stage_progress_update = 0
            elif normalized >= end:
                stage_progress_update = 100
            else:
                stage_progress_update = int((normalized - start) / span * 100)
        if normalized == self._last_progress and stage_progress_update == self._stage_progress:
            return
        mark_job_progress(
            self.job_id,
            progress=normalized,
            stage_progress=stage_progress_update,
        )
        self._last_progress = normalized
        if stage_progress_update is not None:
            self._stage_progress = stage_progress_update
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
        window: Optional[tuple[int, int]] = None,
    ) -> None:
        """Update current stage metadata for richer UI feedback."""
        normalized = None if progress is None else max(0, min(100, int(progress)))
        window_tuple: Optional[tuple[int, int]] = None
        if window is not None:
            window_tuple = (int(window[0]), int(window[1]))

        if (
            stage == self._current_stage
            and normalized == self._stage_progress
            and (label is None or label == self._stage_label)
            and (window_tuple is None or window_tuple == self._stage_window)
        ):
            return

        if window_tuple is not None:
            self._stage_window = window_tuple
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
            stage_window=window_tuple,
        )
        logger.debug(
            "Job stage updated",
            extra={
                "job_id": self.job_id,
                "stage": stage,
                "stage_progress": normalized,
                "stage_window": window_tuple or self._stage_window,
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
