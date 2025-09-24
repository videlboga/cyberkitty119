"""Preset definitions for content processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    type_hint: str
    description: str


PRESETS: Dict[str, List[Preset]] = {
    'meeting': [
        Preset('meeting_protocol', 'Протокол встречи', 'meeting', 'Agenda / Decisions / Action items / Risks'),
        Preset('meeting_who_what', 'Кто-что-когда', 'meeting', 'Сводка по участникам и срокам'),
        Preset('meeting_free', 'Свободный промпт…', 'meeting', 'Свой запрос'),
    ],
    'idea': [
        Preset('idea_outline', 'Идея: тезисы', 'idea', '5–8 тезисов и 3 next steps'),
        Preset('idea_free', 'Свободный промпт…', 'idea', 'Свой запрос'),
    ],
    'task': [
        Preset('task_breakdown', 'Разбить на задачи', 'task', 'Список задач с дедлайнами'),
        Preset('task_free', 'Свободный промпт…', 'task', 'Свой запрос'),
    ],
    'media': [
        Preset('media_summary', 'Конспект с таймкодами', 'media', 'Основные идеи и [мм:сс]'),
        Preset('media_free', 'Свободный промпт…', 'media', 'Свой запрос'),
    ],
    'recipe': [
        Preset('recipe_steps', 'Рецепт', 'recipe', 'Ингредиенты и шаги'),
        Preset('recipe_free', 'Свободный промпт…', 'recipe', 'Свой запрос'),
    ],
    'journal': [
        Preset('journal_reflect', 'Журнал: 3–5 тезисов', 'journal', 'Настроение и выводы'),
        Preset('journal_free', 'Свободный промпт…', 'journal', 'Свой запрос'),
    ],
    'other': [
        Preset('other_outline', 'Структурировать', 'other', 'Основные пункты + действия'),
        Preset('other_free', 'Свободный промпт…', 'other', 'Свой запрос'),
    ],
}


def get_presets(type_hint: str) -> List[Preset]:
    return PRESETS.get(type_hint, PRESETS['other'])
