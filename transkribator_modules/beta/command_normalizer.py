"""Normalizes free-form commands into structured payloads."""

from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import BaseModel, Field, ValidationError

from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL
from transkribator_modules.beta.router import _call_openrouter as call_router


class ContentCommand(BaseModel):
    version: str = '1.0'
    is_command_for_content: bool = True
    confidence: float = 0.0
    scope: Dict[str, Any] = Field(default_factory=lambda: {"target": "current", "note_id": None, "search_query": None})
    action: str = 'free_prompt'
    params: Dict[str, Any] = Field(default_factory=lambda: {"prompt": None, "tags": [], "folder": None})


async def normalize_manual_command(text: str) -> Dict[str, Any]:
    if not OPENROUTER_API_KEY:
        return ContentCommand(params={"prompt": text}).model_dump()
    prompt = (
        "Ты — нормализатор команды над контентом. Верни ТОЛЬКО валидный JSON по схеме. "
        "Если цель не указана — target='current'. Текст: <<<" + text + ">>>"
    )
    tries = 0
    last_error = None
    while tries < 2:
        tries += 1
        try:
            response = await call_router(prompt)
            data = json.loads(response)
            command = ContentCommand(**data)
            return command.model_dump()
        except (ValidationError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            logger.warning("Content command normalization failed", extra={"error": last_error, "attempt": tries})
    return ContentCommand(params={"prompt": text, "fallback_error": last_error}).model_dump()
