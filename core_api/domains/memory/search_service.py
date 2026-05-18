from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from sqlalchemy.orm import Session

from transkribator_modules.db.database import UserService
from transkribator_modules.search.service import run_note_search, NoteSearchError

logger = logging.getLogger(__name__)


class MemorySearchError(Exception):
    """Base exception for memory search domain."""


class MemorySearchValidationError(MemorySearchError):
    """Raised when user input is invalid."""


class MemorySearchServiceError(MemorySearchError):
    """Raised for unexpected service failures."""


@dataclass(slots=True)
class MemorySearchResult:
    """Normalized response returned to API layer."""

    response_text: str
    raw_payload: Dict[str, Any]


class MemorySearchService:
    """Thin domain-layer wrapper around legacy search implementation.

    Этот сервис инкапсулирует всю работу с БД/легаси функциями и возвращает
    нейтральный объект, чтобы роутеры FastAPI оставались тонкими.
    """

    def __init__(self, db: Session):
        self.db = db
        self._user_service = UserService(db)

    async def search(self, *, telegram_id: int, query: str) -> MemorySearchResult:
        if not query or not query.strip():
            raise MemorySearchValidationError("Запрос не должен быть пустым.")

        user = self._user_service.get_or_create_user(telegram_id=telegram_id)

        try:
            search_payload = await run_note_search(user_id=user.id, query=query)
        except NoteSearchError as exc:
            # доменная ошибка поиска (лимиты, невалидные параметры и т.д.)
            raise MemorySearchError(str(exc)) from exc
        except Exception as exc:  # pragma: no cover - защитный блок
            logger.exception("Memory search failed", extra={"telegram_id": telegram_id})
            raise MemorySearchServiceError("Не удалось выполнить поиск, попробуйте позже.") from exc

        response_text = search_payload.get("response") or "Ничего не найдено."
        return MemorySearchResult(response_text=response_text, raw_payload=search_payload)
