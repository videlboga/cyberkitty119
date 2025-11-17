"""Register built-in job handlers."""

from __future__ import annotations

from transkribator_modules.config import logger

from .handlers import register_handler
from .media import MEDIA_JOB_TYPE, process_media_job


def register_builtin_handlers(*, force: bool = False) -> None:
    """Register default job handlers used by worker processes."""
    register_handler(MEDIA_JOB_TYPE, process_media_job, force=force)
    logger.debug(
        "Built-in job handlers registered",
        extra={"handlers": [MEDIA_JOB_TYPE]},
    )


__all__ = ["register_builtin_handlers"]
