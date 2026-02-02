import time
from typing import Dict, Tuple

_SEEN: Dict[int, float] = {}
_TTL = 600.0  # seconds


def should_process(update_id: int) -> bool:
    now = time.time()
    # purge old
    if _SEEN and len(_SEEN) % 32 == 0:
        cutoff = now - _TTL
        for k in list(_SEEN.keys()):
            if _SEEN[k] < cutoff:
                _SEEN.pop(k, None)
    if update_id in _SEEN:
        return False
    _SEEN[update_id] = now
    return True

# Per-message dedupe (chat_id, message_id)
_SEEN_MSG: Dict[Tuple[int, int], float] = {}


def should_process_message(chat_id: int, message_id: int) -> bool:
    now = time.time()
    if _SEEN_MSG and len(_SEEN_MSG) % 64 == 0:
        cutoff = now - _TTL
        for k in list(_SEEN_MSG.keys()):
            if _SEEN_MSG[k] < cutoff:
                _SEEN_MSG.pop(k, None)
    key = (chat_id, message_id)
    if key in _SEEN_MSG:
        return False
    _SEEN_MSG[key] = now
    return True
