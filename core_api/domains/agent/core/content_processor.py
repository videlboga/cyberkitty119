"""Content processing utilities for generating summaries and tags."""

from __future__ import annotations

import ast
import json
import os
from typing import Optional, Any, Iterable

import aiohttp
import socket

from transkribator_modules.config import logger

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

# Drive sync configuration
FOLDER_MAP = {
    'meeting': 'Meetings',
    'idea': 'Ideas',
    'task': 'Tasks',
    'media': 'Resources',
    'recipe': 'Resources',
    'journal': 'Journal',
}


def _front_matter(type_hint: str, tags: list[str], summary: str) -> str:
    """Generate YAML front matter for note export."""
    tags_yaml = '\n'.join(f'  - {tag}' for tag in (tags or []))
    return f"""---
type: {type_hint or 'other'}
tags:
{tags_yaml if tags_yaml else '  - uncategorized'}
summary: {summary or 'No summary'}
---

"""


def _ensure_signature(text: str) -> str:
    """Ensure text ends with @CyberKitty19_bot signature."""
    if not text:
        return text
    signature = "\n\n@CyberKitty19_bot"
    if signature not in text:
        return text + signature
    return text


class ContentProcessor:
    """Legacy stub for backward compatibility."""
    
    async def process(
        self,
        user: Any,
        text: str,
        type_hint: str,
        preset: Any,
        status: str,
        custom_prompt: Optional[str] = None,
        tags: Optional[list[str]] = None,
        type_confidence: Optional[float] = None,
        existing_note_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """Process note with custom prompt (stub implementation)."""
        logger.warning("ContentProcessor.process() is a stub - feature not fully implemented")
        return {
            "summary": "Обработка выполнена",
            "tags": tags or [],
            "status": status,
        }


def _unwrap_json_content(raw: str) -> str:
    """Strip common Markdown fences around JSON payload."""
    if not raw:
        return raw
    text = raw.strip()
    if text.lower().startswith("json"):
        after_prefix = text[4:]
        if after_prefix.startswith(("\n", "\r\n")):
            text = after_prefix.lstrip("\r\n")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            fence = lines[0]
            body_lines = lines[1:]
            if fence.lower().startswith("```json"):
                text = "\n".join(body_lines)
            elif fence == "```":
                text = "\n".join(body_lines)
        if "```" in text:
            text = text.rsplit("```", 1)[0]
    return text.strip()


_TAG_KEYS = {"tags", "taglist", "теги", "тегизаметки", "ключевыеслова"}


def _coerce_tag_values(value: Any) -> list[str]:
    """Normalize tag payloads into a trimmed list of strings."""
    result: list[str] = []
    tokens: Iterable[Any]
    if isinstance(value, (list, tuple, set)):
        tokens = value
    elif isinstance(value, str):
        translated = value.replace("#", "").replace(";", ",")
        tokens = [chunk.strip() for chunk in translated.split(",") if chunk.strip()]
    else:
        tokens = [value]

    for token in tokens:
        if token is None:
            continue
        cleaned = str(token).strip()
        if cleaned:
            result.append(cleaned[:48])
    return result


def _collect_structured_tags(payload: Any) -> list[str]:
    """Collect and remove tag fields from a structured payload."""
    tags: list[str] = []
    if isinstance(payload, dict):
        to_delete = []
        for key, value in payload.items():
            normalized = str(key).strip().lower().replace(" ", "")
            if normalized in _TAG_KEYS:
                tags.extend(_coerce_tag_values(value))
                to_delete.append(key)
            else:
                tags.extend(_collect_structured_tags(value))
        for key in to_delete:
            payload.pop(key, None)
    elif isinstance(payload, list):
        for item in payload:
            tags.extend(_collect_structured_tags(item))
    return tags


def _format_structured_summary(payload: Any) -> str:
    """Convert nested dict/list payloads into readable bullet blocks."""
    lines: list[str] = []

    def bullet(depth: int) -> str:
        return "•" if depth == 0 else "-"

    def indent(depth: int) -> str:
        return "" if depth == 0 else "  " * depth

    def visit(value: Any, key: Optional[str] = None, depth: int = 0) -> None:
        if isinstance(value, dict):
            if not value:
                return
            if key:
                lines.append(f"{indent(depth)}{bullet(depth)} {key.strip()}:")
                depth += 1
            for sub_key, sub_val in value.items():
                visit(sub_val, str(sub_key), depth)
            return

        if isinstance(value, list):
            if not value:
                return
            if key:
                lines.append(f"{indent(depth)}{bullet(depth)} {key.strip()}:")
                depth += 1
            for item in value:
                visit(item, None, depth)
            return

        text = str(value).strip()
        label = f"{key.strip()}: " if key else ""
        if text or label:
            lines.append(f"{indent(depth)}{bullet(depth)} {label}{text}".rstrip())

    visit(payload)
    return "\n".join(line for line in lines if line).strip()


def _parse_structured_summary(raw: str) -> tuple[str, list[str]]:
    """Parse JSON/dict-like payloads into text and tags."""
    if not raw:
        return "", []

    cleaned = _unwrap_json_content(raw)
    if not cleaned:
        return "", []

    candidate = cleaned.strip()
    if not candidate or candidate[0] not in "{[":
        return "", []

    parsed: Any = None
    for loader in (json.loads, ast.literal_eval):
        print(f"DEBUG: calling openrouter API with model={OPENROUTER_MODEL}, payload_len={len(payload)}", flush=True)
        try:
            parsed = loader(candidate)
            break
        except Exception:  # noqa: BLE001
            continue

    if parsed is None:
        return "", []

    tags = _collect_structured_tags(parsed)
    text = _format_structured_summary(parsed)
    return text, tags


async def _build_summary_and_tags(
    text: str,
    full_text: str,
    existing_tags: Optional[list[str]] = None,
) -> tuple[str, list[str]]:
    print(f"DEBUG: OPENROUTER_API_KEY is_set={bool(OPENROUTER_API_KEY)}, text_length={len(text.strip())}", flush=True)
    if not OPENROUTER_API_KEY or not text.strip():
        return "", existing_tags or []

    system_prompt = (
        "Ты универсальный ассистент по заметкам. Твоя задача — коротко и понятно передавать смысл любых материалов, подчёркивая "
        "ключевые мысли, выводы и факты без шаблонных структур. Подбирай формат под содержание (абзацы, списки, мини-блоки) и "
        "избегай лишней разметки."
    )

    def _split_text_and_tags(raw: str) -> tuple[str, list[str]]:
        raw = raw.strip()
        if not raw:
            return "", []

        structured_text, structured_tags = _parse_structured_summary(raw)
        if structured_text:
            return structured_text, structured_tags

        cleaned = _unwrap_json_content(raw)
        lines = cleaned.splitlines()
        while lines and not lines[-1].strip():
            lines.pop()

        tags: list[str] = []
        if lines and lines[-1].strip().lower().startswith("tags:"):
            tag_line = lines.pop().split(':', 1)[-1]
            tags = _coerce_tag_values(tag_line)

        text_body = "\n".join(lines).strip()
        return text_body, tags

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://transkribator.local"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "Transkribator"),
    }

    async def call_openrouter(prompt: str, max_tokens: int = 1500) -> tuple[str, list[str]]:
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        print(f"DEBUG: calling openrouter API with model={OPENROUTER_MODEL}, payload_len={len(payload)}", flush=True)
        try:
            conn = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status != 200:
                        text_error = await response.text()
                        logger.error(f"OpenRouter non-200 response: {response.status} {text_error}")
                        return "", []
                    data = await response.json()
                    raw = data["choices"][0]["message"]["content"]
                    return _split_text_and_tags(raw)
        except Exception as e:
            print(f"DEBUG: exception in call_openrouter {e}", flush=True)
            logger.exception(f"Exception in call_openrouter: {e}")
            return "", []

    def segment_prompt(body: str, idx: int, total: int) -> str:
        return (
            f"Ты пересказываешь часть ({idx}/{total}) длинного материала. Передай ключевые идеи, факты, выводы и акценты, сохраняя имена, даты и цифры.\n"
            "Выбери структуру, которая лучше раскрывает смысл (абзацы, списки, короткие блоки, цитаты) и избегай шаблонов наподобие «Повестка» или «Открытые вопросы», если они не вытекают из текста.\n"
            "Не копируй реплики дословно, но сохраняй намерения и решения. В конце добавь строку 'Tags: ...' с 3–6 короткими тегами.\n\n"
            f"Сегмент (длина {len(body)}):\n{body}"
        )

    def final_prompt(blocks_text: str) -> str:
        return (
            "Собери целостное саммари по сводкам ниже так, чтобы читатель быстро понял, о чём был материал и какие выводы важны.\n"
            "Используй свободную структуру: абзацы, списки, короткие тематические блоки — что угодно, лишь бы текст читался естественно. "
            "Не зацикливайся на формате встреч или задач: ориентируйся по содержанию, сохраняя факты, решения и договорённости.\n"
            "В конце добавь строку 'Tags: ...' с основными темами.\n\n"
            f"Сводки:\n{blocks_text}"
        )

    if len(text) <= 8000:
        summary, tags = await call_openrouter(segment_prompt(text, 1, 1))
        summary = summary or f"Заметка содержит {len(text)} символов текста."
        tags = tags or existing_tags or []
        return summary, tags[:10]

    CHUNK = 7000
    OVERLAP = 500
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        end = min(pos + CHUNK, len(text))
        cut = text.rfind('\n', pos, end)
        if cut == -1 or cut <= pos + 1000:
            cut = end
        parts.append(text[pos:cut])
        if cut >= len(text):
            break
        pos = max(cut - OVERLAP, pos + 1)

    segment_blocks: list[str] = []
    collected_tags: list[str] = []
    for idx, part in enumerate(parts, 1):
        seg_text, seg_tags = await call_openrouter(segment_prompt(part, idx, len(parts)), max_tokens=900)
        if seg_text:
            segment_blocks.append(seg_text)
        collected_tags.extend(seg_tags)

    combined = "\n\n".join(segment_blocks)
    final_text, final_tags = await call_openrouter(final_prompt(combined), max_tokens=1400)
    if not final_text:
        final_text = combined[:1500]
    if not final_tags:
        seen = set()
        final_tags = []
        for t in collected_tags:
            key = t.casefold()
            if key and key not in seen:
                seen.add(key)
                final_tags.append(t)

    final_tags = final_tags or existing_tags or []

    seen = set()
    unique_tags: list[str] = []
    for tag in final_tags:
        lower = tag.casefold()
        if lower and lower not in seen:
            seen.add(lower)
            unique_tags.append(tag)
    final_text = final_text.strip()
    return final_text, unique_tags[:10]


__all__ = [
    "_build_summary_and_tags",
    "ContentProcessor",
    "FOLDER_MAP",
    "_front_matter",
    "_ensure_signature",
    "_parse_structured_summary",
]
