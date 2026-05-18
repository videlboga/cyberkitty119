from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover - optional dependency fallback
    redis = None

logger = logging.getLogger(__name__)


class AgentSessionStore:
    """Protocol-like base for storing session state."""

    def load(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def save(self, telegram_id: int, state: Dict[str, Any]) -> None:
        raise NotImplementedError

    def delete(self, telegram_id: int) -> None:
        raise NotImplementedError


class InMemoryAgentSessionStore(AgentSessionStore):
    def __init__(self):
        self._state: dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def load(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._state.get(int(telegram_id))
            return json.loads(json.dumps(state)) if state is not None else None

    def save(self, telegram_id: int, state: Dict[str, Any]) -> None:
        with self._lock:
            # deep copy to avoid accidental shared references
            self._state[int(telegram_id)] = json.loads(json.dumps(state))

    def delete(self, telegram_id: int) -> None:
        with self._lock:
            self._state.pop(int(telegram_id), None)


class RedisAgentSessionStore(AgentSessionStore):
    def __init__(self, client: "redis.Redis", *, ttl_seconds: int = 3600):
        self._client = client
        self._ttl = ttl_seconds

    def _key(self, telegram_id: int) -> str:
        return f"agent_session:{int(telegram_id)}"

    def load(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        raw = self._client.get(self._key(telegram_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to decode session payload from Redis", extra={"telegram_id": telegram_id})
            return None

    def save(self, telegram_id: int, state: Dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        self._client.set(self._key(telegram_id), payload, ex=self._ttl)

    def delete(self, telegram_id: int) -> None:
        self._client.delete(self._key(telegram_id))


_SESSION_STORE: Optional[AgentSessionStore] = None


def get_agent_session_store() -> AgentSessionStore:
    global _SESSION_STORE
    if _SESSION_STORE is not None:
        return _SESSION_STORE

    redis_url = os.getenv("REDIS_URL")
    ttl_seconds = int(os.getenv("AGENT_SESSION_TTL", "86400"))
    if redis_url and redis:
        try:
            client = redis.Redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("Agent sessions will be stored in Redis at %s", redis_url)
            _SESSION_STORE = RedisAgentSessionStore(client, ttl_seconds=ttl_seconds)
            return _SESSION_STORE
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis session store unavailable (%s), falling back to memory", exc)

    logger.info("Agent sessions will be stored in-memory (Redis disabled or unavailable)")
    _SESSION_STORE = InMemoryAgentSessionStore()
    return _SESSION_STORE
