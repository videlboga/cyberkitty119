"""Маршрутизатор для бета-режима: вызов LLM и валидация ответа."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
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
from .tools import get_tool_specs

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
    preset_id: Optional[str] = None
    prompt: Optional[str] = None
    target_type: Optional[str] = None
    target_status: Optional[str] = None
    new_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)
    task_due: Optional[str] = None

    model_config = dict(extra="ignore")


class RouterCommand(BaseModel):
    intent: Optional[str] = None
    args: RouterCommandArgs = Field(default_factory=RouterCommandArgs)

    model_config = dict(extra="ignore")


class RouterContent(BaseModel):
    type_hint: str = "other"
    type_confidence: float = 0.0

    model_config = dict(extra="ignore")


class RouterAction(BaseModel):
    """Единичное действие, которое может выполнить агент."""

    tool: str
    args: Dict[str, Any] = Field(default_factory=dict)
    comment: Optional[str] = None
    confidence: Optional[float] = None

    model_config = dict(extra="ignore")


class RouterPayload(BaseModel):
    version: str = "1.1"
    mode: str = "actions"
    confidence: float = 0.0
    actions: list[RouterAction] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    reason: Optional[str] = None
    command: Optional[RouterCommand] = None  # для обратной совместимости
    content: Optional[RouterContent] = None

    model_config = dict(extra="ignore")


@dataclass(slots=True)
class RouterResult:
    payload: RouterPayload
    mode: str
    confidence: float
    raw_text: str
    error: Optional[str] = None

    @property
    def content(self) -> RouterContent:
        return self.payload.content or RouterContent()

    @property
    def command(self) -> RouterCommand:
        return self.payload.command or RouterCommand()

    @property
    def actions(self) -> list[RouterAction]:
        return self.payload.actions

    @property
    def suggestions(self) -> list[str]:
        return self.payload.suggestions


def _clip(text: str, limit: int = 400) -> str:
    if not text:
        return ''
    if len(text) <= limit:
        return text
    return text[: limit - 1] + '…'


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return str(value)


def _sanitize_payload_dict(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}

    sanitized: dict[str, Any] = {}
    sanitized['version'] = _coerce_str(data.get('version')) or '1.1'

    mode_raw = _coerce_str(data.get('mode'))
    mode = mode_raw.lower() if mode_raw else 'actions'
    if mode not in {'actions', 'content'}:
        mode = 'actions'
    sanitized['mode'] = mode
    sanitized['confidence'] = _coerce_float(data.get('confidence'), 0.0)

    actions_raw = data.get('actions')
    actions: list[dict[str, Any]] = []
    if isinstance(actions_raw, list):
        for item in actions_raw:
            if not isinstance(item, dict):
                continue
            tool = _coerce_str(item.get('tool'))
            if not tool:
                continue
            args = item.get('args') if isinstance(item.get('args'), dict) else {}
            comment = _coerce_str(item.get('comment'))
            action_confidence = _coerce_float(item.get('confidence'), None) if item.get('confidence') is not None else None
            actions.append(
                {
                    'tool': tool,
                    'args': args,
                    'comment': comment,
                    'confidence': action_confidence,
                }
            )

    if not actions:
        fallback = _convert_legacy_command(data.get('command'))
        if fallback:
            actions.append(fallback)
            sanitized['mode'] = 'actions'

    sanitized['actions'] = actions

    suggestions_raw = data.get('suggestions')
    if isinstance(suggestions_raw, list):
        sanitized['suggestions'] = [s for item in suggestions_raw if (s := _coerce_str(item))]
    else:
        sanitized['suggestions'] = []

    sanitized['reason'] = _coerce_str(data.get('reason'))

    if sanitized['mode'] == 'content' and actions:
        sanitized['mode'] = 'actions'

    return sanitized


def _convert_legacy_command(raw_command: Any) -> Optional[dict[str, Any]]:
    if not isinstance(raw_command, dict):
        return None
    try:
        command = RouterCommand.model_validate(raw_command)
    except ValidationError:
        return None

    intent = (command.intent or '').strip().lower()
    if not intent:
        return None

    args = command.args
    if intent == 'calendar':
        action_args: dict[str, Any] = {}
        time_range = args.time_range
        if time_range and time_range.from_time:
            action_args['start'] = time_range.from_time
        if time_range and time_range.to:
            action_args['end'] = time_range.to
        if args.query and 'start' not in action_args:
            action_args['start'] = args.query
        if args.task_due and 'start' not in action_args:
            action_args['start'] = args.task_due
        if args.action:
            action_args['title'] = args.action
        if args.prompt and 'description' not in action_args:
            action_args['description'] = args.prompt
        if args.note_id:
            action_args['note_id'] = args.note_id
        if not action_args:
            return None
        return {
            'tool': 'create_calendar_event',
            'args': action_args,
            'comment': None,
            'confidence': None,
        }

    return None


def _build_router_prompt() -> str:
    tool_specs = get_tool_specs()
    tools_json = json.dumps(tool_specs, ensure_ascii=False, indent=2)
    return dedent(
        f"""
        Ты — маршрутизатор действий для агента заметок. По тексту пользователя нужно определить, какие инструменты вызвать, и вернуть только JSON по схеме.

        Формат ответа:
        {{
          "version": "1.1",
          "mode": "actions|content",
          "confidence": 0.0-1.0,
          "actions": [
            {{
              "tool": "имя_инструмента",
              "args": {{...}},
              "comment": "короткое описание зачем действие",
              "confidence": 0.0-1.0
            }}
          ],
          "suggestions": ["короткая рекомендация"]
        }}

        Правила:
        - Используй только инструменты из списка ниже. Структура и аргументы:
        {tools_json}
        - Если подходящего инструмента нет — верни пустой массив actions и низкий confidence.
        - Даты и время передавай в ISO 8601: `YYYY-MM-DDTHH:MM[:SS][+TZ]`. Для естественных выражений вроде "завтра" считай дату относительно текущего дня пользователя.
        - Для `create_calendar_event` укажи как минимум `start`. Если указан `duration_minutes`, используй его для расчёта `end`, иначе задавай длительность 60 минут. Название события — в `title`, дополнительный контекст — в `description`.
        - Для `update_calendar_event` передавай `event_id` (если известно) и новый `start/end`.
        - Если пользователь просит только предложить действие, помести его в `suggestions`, но не добавляй в actions.
        - Никогда не придумывай id заметок. Если нужен note_id, но он не указан — опусти поле.
        - Всегда возвращай строго JSON без пояснений и текста вокруг.
        """
    ).strip()


async def route_message(payload: Dict[str, Any]) -> RouterResult:
    """Запрашивает LLM и возвращает структурированный результат."""

    raw_text = payload.get("text")
    text = (raw_text or "").strip()
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

    if _looks_like_question(text):
        metadata = dict(metadata)
        boost = float(metadata.get("confidence_boost", 0.0)) + 0.20
        metadata["confidence_boost"] = boost

    now_iso = metadata.get("now_iso")
    tz_label = metadata.get("timezone")
    header_parts = []
    if tz_label and now_iso:
        header_parts.append(f"Сейчас (таймзона {tz_label}): {now_iso}")
    elif now_iso:
        header_parts.append(f"Сейчас: {now_iso}")
    if tz_label and not now_iso:
        header_parts.append(f"Таймзона пользователя: {tz_label}")
    user_id = metadata.get("user_id")
    if user_id:
        header_parts.append(f"UserID: {user_id}")
    context_header = "\n".join(header_parts)
    if context_header:
        user_message = f"{context_header}\nТекст: <<<{text}>>>"
    else:
        user_message = f"Текст: <<<{text}>>>"
    logger.info(
        "Router LLM request: len=%s preview=%s metadata=%s",
        len(text),
        _clip(text),
        metadata,
    )
    prompt = _build_router_prompt()
    tries = 0
    last_error = None
    failure_log = Path(DATA_DIR) / 'router_failures.log'
    while tries < 3:
        tries += 1
        response_text = ''
        try:
            response_text = await _call_openrouter(user_message, prompt)
            logger.info(
                "Router LLM response attempt=%s preview=%s",
                tries,
                _clip(response_text, 600),
            )
            cleaned = _extract_json(response_text)
            sanitized = _sanitize_payload_dict(json.loads(cleaned))
            payload_obj = RouterPayload.model_validate(sanitized)
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


async def _call_openrouter(user_content: str, system_prompt: str) -> str:
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
            {"role": "system", "content": system_prompt},
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
