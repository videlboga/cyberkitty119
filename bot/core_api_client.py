from __future__ import annotations

from typing import Any, Dict

import httpx

from bot.config import CORE_API_BASE_URL, CORE_API_TIMEOUT, core_api_headers


class CoreAPIError(Exception):
    """Raised when Core API request fails."""


def _build_url(path: str) -> str:
    base = CORE_API_BASE_URL.rstrip("/")
    # Always normalize the path by stripping the base
    if path.startswith("/api/v1/"):
        path = path[len("/api/v1/"):]
    if path.startswith("/"):
        path = path[1:]
    if base.endswith("/api/v1"):
        return f"{base}/{path}"
    else:
        return f"{base}/api/v1/{path}"


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


async def enqueue_media_job(telegram_id: int, file_id: str, audio_path: str, message_id: int | None) -> int:
    payload = {
        "telegram_id": telegram_id,
        "file_id": file_id,
        "audio_path": audio_path,
        "message_id": message_id,
    }
    resp = await _request("POST", "/api/v1/ingest/media", json=payload)
    data = resp.json()
    if not data.get("success"):
        raise CoreAPIError(data.get("error", "Не удалось создать задачу"))
    job_id = data.get("job_id")
    if not job_id:
        raise CoreAPIError("Core API не вернул идентификатор задачи")
    return int(job_id)


async def fetch_profile(telegram_id: int, first_name: str = "", last_name: str = "") -> Dict[str, Any]:
    params = {"first_name": first_name or "", "last_name": last_name or ""}
    resp = await _request("GET", f"/system/profile/tg/{telegram_id}", params=params)
    return resp.json()


async def fetch_referral_info(telegram_id: int, username: str = "", first_name: str = "", last_name: str = "") -> Dict[str, Any]:
    params = {
        "username": username or "",
        "first_name": first_name or "",
        "last_name": last_name or "",
    }
    resp = await _request("GET", f"/system/referral/tg/{telegram_id}", params=params)
    return resp.json()


async def activate_promo_code(telegram_id: int, promo_code: str) -> Dict[str, Any]:
    payload = {"telegram_id": telegram_id, "promo_code": promo_code}
    resp = await _request("POST", "/system/promo/activate", json=payload)
    return resp.json()


async def search_memory(telegram_id: int, query: str) -> str:
    payload = {"telegram_id": telegram_id, "query": query}
    resp = await _request("POST", "/memory/search", json=payload)
    data = resp.json()
    return data.get("response", "Ничего не найдено.")

async def chat_with_agent(telegram_id: int, text: str, name: str = "", username: str = "") -> str:
    payload = {"telegram_id": telegram_id, "text": text}
    if name:
        payload["name"] = name
    if username:
        payload["username"] = username
    resp = await _request("POST", "/api/v1/agent/chat", json=payload)
    data = resp.json()
    return data.get("response", data.get("text", ""))

async def set_active_note(telegram_id: int, note_id: int, local_artifact: bool = False) -> None:
    payload = {"telegram_id": telegram_id, "note_id": note_id, "local_artifact": local_artifact}
    await _request("POST", "/api/v1/agent/active_note", json=payload)

async def get_payment_plans() -> Dict[str, Any]:
    """Получает доступные тарифные планы с Core API"""
    resp = await _request("GET", "/api/v1/payments/plans")
    return resp.json()

async def create_payment_invoice(telegram_id: int, plan_id: str, currency: str) -> Dict[str, Any]:
    """Создает инвойс для оплаты"""
    payload = {
        "telegram_id": telegram_id,
        "plan_id": plan_id,
        "currency": currency,
    }
    resp = await _request("POST", "/api/v1/payments/invoice", json=payload)
    return resp.json()

async def confirm_payment_success(telegram_id: int, plan_id: str, amount: float, currency: str, payment_id: str) -> Dict[str, Any]:
    """Регистрирует успешную оплату на бэкенде"""
    payload = {
        "telegram_id": telegram_id,
        "plan_id": plan_id,
        "amount": amount,
        "currency": currency,
        "transaction_id": payment_id,
    }
    resp = await _request("POST", "/api/v1/payments/success", json=payload)
    return resp.json()
