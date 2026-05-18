from __future__ import annotations
import httpx
import os
from typing import Any, Dict

CORE_API_BASE_URL = os.getenv("CORE_API_URL", "http://bot-v2-core-api:8000")
CORE_API_TIMEOUT = 30.0

class CoreAPIError(Exception):
    pass

def core_api_headers() -> dict[str, str]:
    # Prefer CORE_API_SERVICE_TOKEN for containers using that env var, fall back to SERVICE_TOKEN.
    token = os.getenv("CORE_API_SERVICE_TOKEN") or os.getenv("SERVICE_TOKEN") or "super-secret-service-token-123"
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _build_url(path: str) -> str:
    base = CORE_API_BASE_URL.rstrip("/")
    # Normalize double "/api/v1" occurrences: if the base already includes the
    # API prefix and the path also starts with it, strip the duplicate from
    # the path so we don't end up with "/api/v1/api/v1/...".
    api_prefix = "/api/v1"
    if not path.startswith("/"):
        path = "/" + path
    if base.lower().endswith(api_prefix) and path.startswith(api_prefix):
        path = path[len(api_prefix):]
        if not path.startswith("/"):
            path = "/" + path
    return f"{base}{path}"

async def _request(method: str, path: str, **kwargs) -> httpx.Response:
    url = _build_url(path)
    headers = core_api_headers()
    extra_headers = kwargs.pop("headers", None)
    if extra_headers:
        headers.update(extra_headers)
    try:
        async with httpx.AsyncClient(timeout=CORE_API_TIMEOUT) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp
    except httpx.HTTPStatusError as exc:
        detail = None
        try:
            payload = exc.response.json()
            if isinstance(payload, dict):
                detail = payload.get("detail")
            if not detail:
                detail = exc.response.text
        except Exception:
            detail = exc.response.text
        raise CoreAPIError(detail or f"Core API returned status {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise CoreAPIError("Core API недоступен, попробуйте позже.") from exc

async def agent_chat(telegram_id: int, text: str, name: str = "", username: str = "") -> str:
    payload = {"telegram_id": telegram_id, "text": text}
    if name:
        payload["name"] = name
    if username:
        payload["username"] = username
    resp = await _request("POST", "/api/v1/agent/chat", json=payload)
    return resp.json().get("text", "")

async def agent_set_active_note(telegram_id: int, note_id: int, local_artifact: bool = False) -> None:
    payload = {"telegram_id": telegram_id, "note_id": note_id, "local_artifact": local_artifact}
    await _request("POST", "/api/v1/agent/active_note", json=payload)

def set_active_note_sync(telegram_id: int, note_id: int, local_artifact: bool = False) -> None:
    """Synchronous helper for non-async callers (native handlers thread)."""
    import requests
    url = _build_url("/api/v1/agent/active_note")
    headers = core_api_headers()
    payload = {"telegram_id": telegram_id, "note_id": note_id, "local_artifact": local_artifact}
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    r.raise_for_status()

async def search_memory(telegram_id: int, query: str) -> str:
    payload = {"telegram_id": telegram_id, "query": query}
    resp = await _request("POST", "/memory/search", json=payload)
    return resp.json().get("response", "Ничего не найдено.")

async def enqueue_media_job(telegram_id: int, file_id: str, audio_path: str, message_id: int | None = None) -> int:
    payload = {
        "telegram_id": telegram_id,
        "file_id": str(file_id),
        "audio_path": str(audio_path),
        "message_id": message_id,
    }
    resp = await _request("POST", "/api/v1/ingest/media", json=payload)
    data = resp.json()
    if not data.get("success"):
        raise CoreAPIError(data.get("error", "Не удалось создать задачу"))
    return int(data.get("job_id", 0))

async def activate_promo_code(telegram_id: int, promo_code: str) -> Dict[str, Any]:
    payload = {"telegram_id": telegram_id, "promo_code": promo_code}
    resp = await _request("POST", "/system/promo/activate", json=payload)
    return resp.json()

def get_job_status_sync(job_id: int) -> Dict[str, Any] | None:
    import requests
    url = f"{CORE_API_BASE_URL.rstrip('/')}/api/v1/internal_bot/jobs/{job_id}"
    token = os.getenv("SERVICE_TOKEN", "super-secret-service-token-123")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("job")
    except Exception:
        return None

def get_note_for_job_sync(job_id: int) -> Dict[str, Any] | None:
    import requests
    url = f"{CORE_API_BASE_URL.rstrip('/')}/api/v1/internal_bot/jobs/{job_id}/note"
    token = os.getenv("SERVICE_TOKEN", "super-secret-service-token-123")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json().get("note")
    except Exception:
        return None
