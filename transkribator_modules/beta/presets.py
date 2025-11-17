"""Preset catalog loader and suggestion helpers for beta mode."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from transkribator_modules.config import logger


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    description: str
    content_types: tuple[str, ...]
    kind: str
    detail: str
    tone: str
    output_format: str
    priority: int
    match_hints: tuple[str, ...]
    min_characters: Optional[int]
    max_characters: Optional[int]
    requires_timecodes: bool
    system_prompt: str
    user_prompt_template: str
    post_actions: Dict[str, bool]

    @property
    def is_free_prompt(self) -> bool:
        return self.kind == "custom" or self.id.endswith("free") or self.id.endswith("free_prompt")


_CATALOG_FILENAME = "prompts_catalog.json"
_TIME_CODE_PATTERN = re.compile(r"\[(?:\d{1,2}:)?\d{1,2}:\d{2}\]")


class _SafeDict(dict):
    def __missing__(self, key):  # pragma: no cover - defensive, shouldn't happen
        return ""


@lru_cache(maxsize=1)
def _load_catalog() -> Dict[str, Preset]:
    root = Path(__file__).resolve().parents[2]
    path = root / _CATALOG_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover - config error
        logger.error("Файл каталога промтов не найден: %s", path)
        return {}
    except json.JSONDecodeError as exc:  # pragma: no cover - config error
        logger.error("Не удалось разобрать каталог промтов: %s", exc)
        return {}

    items = {}
    for raw in data.get("items", []):
        try:
            preset = Preset(
                id=raw["id"],
                title=raw["title"],
                description=raw.get("description", ""),
                content_types=tuple(raw.get("content_types") or ("other",)),
                kind=raw.get("kind", "other"),
                detail=raw.get("detail", "normal"),
                tone=raw.get("tone", "neutral"),
                output_format=raw.get("output_format", "md"),
                priority=int(raw.get("priority", 50)),
                match_hints=tuple(h.lower() for h in raw.get("match_hints", [])),
                min_characters=raw.get("min_characters"),
                max_characters=raw.get("max_characters"),
                requires_timecodes=bool(raw.get("requires_timecodes", False)),
                system_prompt=raw.get("system_prompt", "Ты обрабатываешь заметки."),
                user_prompt_template=raw.get("user_prompt_template", "{text}"),
                post_actions={k: bool(v) for k, v in (raw.get("post_actions") or {}).items()},
            )
        except Exception as exc:  # pragma: no cover - config error
            logger.error("Не удалось загрузить пресет %s: %s", raw.get("id"), exc)
            continue
        items[preset.id] = preset
    return items


def _all_presets() -> Iterable[Preset]:
    return _load_catalog().values()


def get_preset_by_id(preset_id: str) -> Optional[Preset]:
    return _load_catalog().get(preset_id)


def get_free_prompt() -> Optional[Preset]:
    for preset in _all_presets():
        if preset.is_free_prompt:
            return preset
    return None


def get_default_preset_for_action(action: str, note_type: str, preferred_id: Optional[str] = None) -> Optional[Preset]:
    """Return preset best suited for a command action."""

    if preferred_id:
        preset = get_preset_by_id(preferred_id)
        if preset:
            return preset

    slug = (note_type or "other").lower()
    candidates: list[Preset] = []
    for preset in _all_presets():
        if not preset.post_actions.get(action):
            continue
        if slug in preset.content_types or (slug != "other" and "other" in preset.content_types):
            candidates.append(preset)

    if candidates:
        candidates.sort(key=lambda p: p.priority, reverse=True)
        return candidates[0]

    fallback_map = {
        'summary': 'summary.quick_notes',
        'protocol': 'meeting.protocol',
        'bullets': 'idea.outline',
        'tasks_split': 'task.breakdown',
        'post': 'post.social',
        'quotes': 'insight.quotes',
        'timed_outline': 'insight.timeline',
        'task_from_note': 'task.single_card',
    }
    fallback_id = fallback_map.get(action)
    if fallback_id:
        return get_preset_by_id(fallback_id)
    return None


def _has_timecodes(text: str) -> bool:
    if not text:
        return False
    return bool(_TIME_CODE_PATTERN.search(text))


def _text_length(text: str) -> int:
    return len(text or "")


def get_presets(type_hint: str) -> List[Preset]:
    """Returns all presets applicable for a given type, sorted by priority."""

    slug = (type_hint or "other").lower()
    candidates = [
        preset
        for preset in _all_presets()
        if (slug in preset.content_types or (slug != "other" and "other" in preset.content_types))
        and not preset.is_free_prompt
    ]
    if not candidates:
        candidates = [preset for preset in _all_presets() if not preset.is_free_prompt]

    candidates.sort(key=lambda p: p.priority, reverse=True)

    free_prompt = get_free_prompt()
    if free_prompt:
        candidates.append(free_prompt)
    return candidates


def suggest_presets(note_text: str, type_hint: str, top_n: int = 3) -> List[Preset]:
    """Return top presets for the note text, respecting catalog constraints."""

    text = note_text or ""
    normalized = text.lower()
    length = _text_length(text)
    has_timecodes = _has_timecodes(text)

    slug = (type_hint or "other").lower()
    candidates: List[tuple[float, Preset]] = []

    for preset in _all_presets():
        if preset.is_free_prompt:
            continue
        if slug not in preset.content_types and not (
            slug != "other" and "other" in preset.content_types
        ):
            continue
        if preset.requires_timecodes and not has_timecodes:
            continue
        if preset.min_characters and length < preset.min_characters:
            continue
        if preset.max_characters and length > preset.max_characters:
            continue

        score = float(preset.priority)
        if preset.match_hints:
            matches = sum(1 for hint in preset.match_hints if hint and hint in normalized)
            score += matches * 12
        candidates.append((score, preset))

    if not candidates:
        filtered = []
        for preset in _all_presets():
            if preset.is_free_prompt:
                continue
            if slug not in preset.content_types and not (
                slug != "other" and "other" in preset.content_types
            ):
                continue
            if preset.requires_timecodes and not has_timecodes:
                continue
            if preset.min_characters and length < preset.min_characters:
                continue
            if preset.max_characters and length > preset.max_characters:
                continue
            filtered.append(preset)
        candidates = [(float(p.priority), p) for p in filtered]

    if not candidates:
        candidates = [(float(p.priority), p) for p in get_presets(type_hint) if not p.is_free_prompt]

    candidates.sort(key=lambda item: item[0], reverse=True)
    top = [preset for _, preset in candidates[:top_n]]

    free_prompt = get_free_prompt()
    if free_prompt:
        top.append(free_prompt)

    return top


def render_user_prompt(preset: Preset, *, note_text: str, user_prompt: str | None = None) -> str:
    """Render user prompt template with safe substitution."""

    template = preset.user_prompt_template or "{text}"
    values = _SafeDict(text=note_text, user_prompt=user_prompt or "")

    if preset.is_free_prompt and user_prompt:
        # Пользовательский режим: не перезаписываем запрос, а дополняем его транскриптом.
        return f"{user_prompt.strip()}\n\nТекст:\n<<<\n{note_text}\n>>>"

    try:
        return template.format_map(values)
    except Exception as exc:  # pragma: no cover - защитный fallback
        logger.warning("Не удалось подставить шаблон для пресета %s: %s", preset.id, exc)
        return f"{template}\n\nТекст:\n<<<\n{note_text}\n>>>"


__all__ = [
    "Preset",
    "get_presets",
    "suggest_presets",
    "get_preset_by_id",
    "render_user_prompt",
    "get_free_prompt",
]
