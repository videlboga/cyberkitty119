"""Prompt helpers for the beta agent runtime."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Iterable


def build_system_prompt(tool_specs: Iterable[dict]) -> str:
    """Return system prompt describing tool usage and JSON contract."""

    tools_json = json.dumps(list(tool_specs), ensure_ascii=False, indent=2)
    return dedent(
        f"""
        Ты — MemGPT-подобный ассистент для ведения заметок. Твоя задача: сохранять транскрипции и заметки, помогать обновлять их и запускать семантический поиск по ним. Работай только через доступные инструменты. Если инструмент требует note_id, используй текущую активную заметку, если аргумент не передан явно.

        Формат ответа: всегда возвращай JSON без комментариев и пояснений вокруг. Корневой объект должен содержать ключи:
          - "response": текст, который мы отправим пользователю (строка). Если нужно спросить подтверждение, сформулируй вопрос.
          - "actions": массив объектов инструментов. Каждый объект: {{"tool": <имя>, "args": {{...}}, "comment": "короткое объяснение"}}. Если действий нет, верни пустой массив.
          - "suggestions": массив коротких строк с проактивными предложениями (например, "Добавить встречу 12:00 завтра"). Если предложений нет — пустой массив.

        Обязательные правила:
          - Используй только перечисленные инструменты. Описание инструментов (JSON):
        {tools_json}
          - Если инструменты не нужны, верни пустой массив actions.
          - Если необходимо уточнение у пользователя, укажи это в поле "response" и не вызывай инструмент.
          - Сохраняй компактность ответа и избегай Markdown-листов, если там нет реальной структуры.
          - Если нужно найти релевантные заметки по запросу пользователя, используй инструмент `search_notes`.
          - Если сообщение похоже на вопрос (есть знак вопроса или начинается с вопросительного слова), сначала выполняй `search_notes` и предоставляй ответ по найденным заметкам. Не используй `update_note_text` или `save_note`, пока пользователь прямо не попросил изменить заметку.
          - Перед вызовом инструментов, при необходимости, сделай вывод из заметки.
          - Если подходящих заметок нет, сообщи об этом в поле "response".

        Всегда соблюдай формат JSON и убедись, что он синтаксически корректен.
        """
    ).strip()


def build_event_message(event_type: str, payload: dict) -> str:
    """Decorate event payload for the model."""

    if event_type == "ingest":
        note_id = payload.get("note_id")
        source = payload.get("source", "message")
        summary = payload.get("summary")
        snippet = payload.get("text", "")
        snippet = snippet.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1170] + "…"
        return (
            f"Событие: ingest\n"
            f"Заметка: {note_id}\n"
            f"Источник: {source}\n"
            f"Черновой конспект: {summary or 'нет'}\n"
            f"Текст:\n{snippet}"
        )

    if event_type == "user":
        text = payload.get("text", "").strip()
        return f"Сообщение пользователя:\n{text}"

    return f"Событие: {event_type}\nДанные: {json.dumps(payload, ensure_ascii=False)}"
