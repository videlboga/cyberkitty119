"""Minimal metrics helper for structured logging."""

from __future__ import annotations

from transkribator_modules.config import logger


def record_event(name: str, **fields) -> None:
    payload = {"event": name, **fields}
    logger.info("METRIC", extra={"metric": payload})
