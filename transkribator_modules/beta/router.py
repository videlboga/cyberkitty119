"""Маршрутизатор для бета-режима: вызов LLM и валидация ответа."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from transkribator_modules.config import (
    logger,
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    DATA_DIR,
)
from .feature_flags import ROUTER_MODEL

# OpenRouter требует referer и название приложения
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "https://transkribator.local")
OPENROUTER_APP = os.getenv("OPENROUTER_APP_NAME", "CyberKitty")


class RouterTimeRange(BaseModel):
    """Диапазон времени / период."""

    from_time: Optional[str] = Field(None, alias="from")
    to: Optional[str] = None
    preset: Optional[str] = None

    model_config = dict(populate_by_name=True)


class RouterCommandArgs(BaseModel):
    query: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    type: Optional[str] = None
    time_range: RouterTimeRange = Field(default_factory=RouterTimeRange)
    k: int = 8
    action: Optional[str] = None
    note_id: Optional[str] = None


class RouterCommand(BaseModel):
    intent: Optional[str] = None
    args: RouterCommandArgs = Field(default_factory=RouterCommandArgs)


class RouterContent(BaseModel):
    type_hint: str = "other"
    type_confidence: float = 0.0


class RouterPayload(BaseModel):
    version: str = "1.0"
    mode: str = "content"
    confidence: float = 0.0
    command: RouterCommand = Field(default_factory=RouterCommand)
    content: RouterContent = Field(default_factory=RouterContent)


@dataclass(slots=True)
class RouterResult:
    payload: RouterPayload
    mode: str
    confidence: float
    raw_text: str
    error: Optional[str] = None

    @property
    def content(self) -> RouterContent:
        return self.payload.content

    @property
    def command(self) -> RouterCommand:
        return self.payload.command


def _clip(text: str, limit: int = 400) -> str:
    if not text:
        return ''
    if len(text) <= limit:
        return text
    return text[: limit - 1] + '…'


def _normalize_null(value):
    if isinstance(value, str) and value.strip().lower() == 'null':
        return None
    return value


def _sanitize_payload_dict(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}

    data.setdefault('version', '1.0')
    data.setdefault('mode', 'content')
    data.setdefault('confidence', 0.0)

    command = data.get('command') or {}
    if not isinstance(command, dict):
        command = {}
    args = command.get('args') or {}
    if not isinstance(args, dict):
        args = {}

    # normalize simple fields
    for key in ('intent',):
        if key in command:
            command[key] = _normalize_null(command[key])

    for key in ('query', 'type', 'action', 'note_id'):
        if key in args:
            args[key] = _normalize_null(args[key])

    for key in ('tags',):
        if not isinstance(args.get(key), list):
            args[key] = []

    time_range = args.get('time_range') or {}
    if not isinstance(time_range, dict):
        time_range = {}
    for key in ('from', 'to', 'preset'):
        if key in time_range:
            time_range[key] = _normalize_null(time_range[key])
    args['time_range'] = time_range
    args.setdefault('k', 8)

    command['args'] = args
    data['command'] = command

    content = data.get('content')
    if not isinstance(content, dict):
        content = {}
    content.setdefault('type_hint', 'other')
    content.setdefault('type_confidence', 0.0)
    content['type_hint'] = _normalize_null(content.get('type_hint')) or 'other'
    content['type_confidence'] = content.get('type_confidence') or 0.0
    data['content'] = content

    return data


ROUTER_PROMPT = (
    "Ты — маршрутизатор. Верни ТОЛЬКО валидный JSON строго по схеме. "
    "Одно из полей mode должно быть 'command' или 'content'. Если сомневаешься — mode='content' и низкий confidence. "
    "Структура:\n"
    "{\n"
    "  \"version\": \"1.0\",\n"
    "  \"mode\": \"command|content\",\n"
    "  \"confidence\": 0.0,\n"
    "  \"command\": {\n"
    "    \"intent\": \"qa|filter|digest|calendar|action|help|null\",\n"
    "    \"args\": {\n"
    "      \"query\": null,\n"
    "      \"tags\": [],\n"
    "      \"type\": \"meeting|idea|task|media|recipe|journal|any|null\",\n"
    "      \"time_range\": {\"from\": null, \"to\": null, \"preset\": \"last_week|this_week|this_month|null\"},\n"
    "      \"k\": 8,\n"
    "      \"action\": \"summary|protocol|bullets|tasks_split|task_from_note|post|quotes|timed_outline|retag|move|save_drive|create_doc|update_index|free_prompt|null\",\n"
    "      \"note_id\": null\n"
    "    }\n"
    "  },\n"
    "  \"content\": {\n"
    "    \"type_hint\": \"meeting|idea|task|media|recipe|journal|other\",\n"
    "    \"type_confidence\": 0.0\n"
    "  }\n"
    "}\n"
    "Всегда возвращай JSON без комментариев и текстов вокруг."
)


async def route_message(payload: Dict[str, Any]) -> RouterResult:
    """Запрашивает LLM и возвращает структурированный результат."""

    text = (payload.get("text") or "").strip()
    metadata = payload.get("metadata", {})

    if not text:
        fallback = RouterPayload()
        return RouterResult(
            payload=fallback,
            mode=fallback.mode,
            confidence=fallback.confidence,
            raw_text="{}",
            error="empty_text",
        )

    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API ключ не настроен, Router LLM не доступен")
        fallback = RouterPayload()
        return RouterResult(
            payload=fallback,
            mode=fallback.mode,
            confidence=fallback.confidence,
            raw_text="{}",
            error="missing_api_key",
        )

    user_message = f"Текст: <<<{text}>>>"
    logger.info(
        "Router LLM request: len=%s preview=%s metadata=%s",
        len(text),
        _clip(text),
        metadata,
    )
    tries = 0
    last_error = None
    failure_log = Path(DATA_DIR) / 'router_failures.log'
    while tries < 3:
        tries += 1
        response_text = ''
        try:
            response_text = await _call_openrouter(user_message)
            logger.info(
                "Router LLM response attempt=%s preview=%s",
                tries,
                _clip(response_text, 600),
            )
            cleaned = _extract_json(response_text)
            sanitized = _sanitize_payload_dict(json.loads(cleaned))
            payload_obj = RouterPayload.model_validate(sanitized)
            if payload_obj.mode not in {"command", "content"}:
                raise ValueError("mode must be command or content")
            return RouterResult(
                payload=payload_obj,
                mode=payload_obj.mode,
                confidence=payload_obj.confidence,
                raw_text=json.dumps(sanitized, ensure_ascii=False),
            )
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_error = str(exc)
            logger.warning(
                "Не удалось распарсить ответ Router LLM: attempt=%s error=%s preview=%s",
                tries,
                last_error,
                _clip(response_text, 600),
            )
            try:
                failure_log.parent.mkdir(parents=True, exist_ok=True)
                with failure_log.open('a', encoding='utf-8') as fp:
                    fp.write(
                        f"attempt={tries} error={last_error}\nresponse={response_text}\n---\n"
                    )
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.2 * tries)
        except aiohttp.ClientError as exc:
            last_error = str(exc)
            logger.error("Ошибка сети при обращении к Router LLM", extra={"error": last_error})
            break

    fallback = RouterPayload()
    return RouterResult(
        payload=fallback,
        mode=fallback.mode,
        confidence=fallback.confidence,
        raw_text="{}",
        error=last_error or "router_failure",
    )


async def _call_openrouter(user_content: str) -> str:
    """Выполняет вызов OpenRouter."""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_APP,
    }

    body = {
        "model": ROUTER_MODEL or OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "top_p": 0.1,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            response.raise_for_status()
            data = await response.json()

    choices = data.get("choices") or []
    if not choices:
        raise ValueError("No choices returned from OpenRouter")

    content = choices[0].get("message", {}).get("content")
    if not content:
        raise ValueError("Empty content returned from OpenRouter")

    return content


def _extract_json(raw_text: str) -> str:
    """Выделяет JSON из ответа модели."""

    if not raw_text:
        raise ValueError("Пустой ответ модели")

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("JSON not found in model output")

    snippet = raw_text[start : end + 1]
    return snippet


__all__ = ["RouterResult", "route_message", "RouterPayload"]
