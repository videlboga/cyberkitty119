from contextlib import asynccontextmanager
from typing import AsyncIterator
import time

from transkribator_modules.config import logger

"""
Guard to prevent duplicate processing of the same (chat_id, message_id).

Behavior:
- If the configured DB backend is PostgreSQL, use pg_try_advisory_lock to
  acquire a cross-process advisory lock keyed by (chat_id, message_id).
- If Postgres is not available or advisory locks fail, fall back to a
  lightweight in-process TTL-based dedupe to avoid immediate duplicates.

This provides best-effort protection against multiple bot instances
processing the same message concurrently.
"""

# In-process fallback map: (chat_id, message_id) -> timestamp
_SEEN_MSG: dict[tuple[int, int], float] = {}
_TTL = 600.0


@asynccontextmanager
async def guard(chat_id: int, message_id: int) -> AsyncIterator[bool]:
    # Try Postgres advisory lock if available to coordinate across processes.
    try:
        # Import lazily to avoid import-time DB initialization in some contexts
        from transkribator_modules.db.database import engine
        from sqlalchemy import text

        backend = engine.url.get_backend_name()
        logger.debug("processing_guard: backend=%s for chat=%s message=%s", backend, chat_id, message_id)
        if backend == "postgresql":
            # Use two-int advisory lock (safe for combined keys)
            high = int(chat_id) & 0x7FFFFFFF
            low = int(message_id) & 0x7FFFFFFF
            conn = engine.connect()
            try:
                logger.debug("processing_guard: attempting pg_try_advisory_lock (h=%s,l=%s)", high, low)
                res = conn.execute(text("SELECT pg_try_advisory_lock(:h, :l)"), {"h": high, "l": low}).scalar()
                if res:
                    logger.info("processing_guard: advisory lock acquired for chat=%s message=%s (h=%s,l=%s)", chat_id, message_id, high, low)
                    try:
                        yield True
                    finally:
                        try:
                            conn.execute(text("SELECT pg_advisory_unlock(:h, :l)"), {"h": high, "l": low})
                            logger.debug("processing_guard: advisory lock released for chat=%s message=%s", chat_id, message_id)
                        except Exception:
                            logger.exception("processing_guard: Failed to release advisory lock for chat=%s message=%s", chat_id, message_id)
                        conn.close()
                    return
                else:
                    # Could not acquire advisory lock - another process is handling it
                    logger.info("processing_guard: advisory lock busy for chat=%s message=%s", chat_id, message_id)
                    conn.close()
                    yield False
                    return
            except Exception:
                # Fall through to in-process fallback if advisory lock queries fail
                logger.exception("processing_guard: advisory lock attempt failed, falling back to in-memory for chat=%s message=%s", chat_id, message_id)
                try:
                    conn.close()
                except Exception:
                    pass
    except Exception:
        # Any import/DB errors -> fall back to in-process guard
        pass

    # In-process TTL-based dedupe fallback
    now = time.time()
    # Purge old entries occasionally
    if _SEEN_MSG and len(_SEEN_MSG) % 64 == 0:
        cutoff = now - _TTL
        for k in list(_SEEN_MSG.keys()):
            if _SEEN_MSG[k] < cutoff:
                _SEEN_MSG.pop(k, None)

    key = (chat_id, message_id)
    if key in _SEEN_MSG:
        yield False
        return
    _SEEN_MSG[key] = now
    try:
        yield True
    finally:
        # Leave the key in the map until TTL expires to avoid immediate duplicates
        return

