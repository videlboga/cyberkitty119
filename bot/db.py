from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
import httpx
import logging

from bot.config import INTERNAL_BOT_API_BASE, CORE_API_TIMEOUT, core_api_headers

logger = logging.getLogger(__name__)

def _sync_post(endpoint: str, json: dict) -> dict:
    try:
        with httpx.Client(timeout=CORE_API_TIMEOUT) as client:
            resp = client.post(
                f"{INTERNAL_BOT_API_BASE}{endpoint}",
                json=json,
                headers=core_api_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Error on post {endpoint}: {e}")
        return {}

def _sync_get(endpoint: str, params: dict = None) -> dict:
    try:
        with httpx.Client(timeout=CORE_API_TIMEOUT) as client:
            resp = client.get(
                f"{INTERNAL_BOT_API_BASE}{endpoint}",
                params=params,
                headers=core_api_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Error on get {endpoint}: {e}")
        return {}

async def _async_post(endpoint: str, json: dict) -> dict:
    try:
        async with httpx.AsyncClient(timeout=CORE_API_TIMEOUT) as client:
            resp = await client.post(
                f"{INTERNAL_BOT_API_BASE}{endpoint}",
                json=json,
                headers=core_api_headers(),
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"Error on async post {endpoint}: {e}")
        return {}

async def ensure_user(telegram_id: int) -> int:
    """Найти или создать пользователя по telegram_id. Вернуть internal id."""
    data = await _async_post("/ensure_user", {"telegram_id": telegram_id})
    return data.get("user_id")

def get_user_id_by_telegram_id(telegram_id: int) -> Optional[int]:
    data = _sync_get(f"/user_id_by_tg/{telegram_id}")
    return data.get("user_id")

def get_job_row(job_id: int) -> Optional[Dict[str, Any]]:
    data = _sync_get(f"/jobs/{job_id}")
    return data.get("job")

def get_transcript_for_job(job_id: int) -> Optional[str]:
    data = _sync_get(f"/jobs/{job_id}/transcript")
    return data.get("transcript")

def get_note_for_job(job_id: int) -> Optional[Dict[str, Any]]:
    data = _sync_get(f"/jobs/{job_id}/note")
    return data.get("note")

def ensure_note_qa_session(
    *,
    user_id: int,
    note: Dict[str, Any],
    context_snapshot: str,
) -> int:
    payload = {
        "user_id": user_id,
        "note": note,
        "context_snapshot": context_snapshot
    }
    data = _sync_post("/qa/ensure", payload)
    return data.get("session_id")

def get_note_qa_session_for_user(user_id: int, note_id: int) -> Optional[int]:
    data = _sync_get("/qa/session_id", params={"user_id": user_id, "note_id": note_id})
    return data.get("session_id")

def record_note_qa_message(session_id: int, role: str, content: str) -> None:
    payload = {
        "session_id": session_id,
        "role": role,
        "content": content
    }
    _sync_post("/qa/message", payload)

def fetch_note_qa_session_payload(
    session_id: int,
    *,
    history_limit: int = 30,
) -> Optional[Dict[str, Any]]:
    data = _sync_get(f"/qa/payload/{session_id}", params={"history_limit": history_limit})
    return data.get("payload")
