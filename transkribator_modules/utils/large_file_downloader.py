"""Helpers for downloading large Telegram files with retry logic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Callable, Awaitable
import os
import shutil

import httpx

from transkribator_modules.config import (
    LOCAL_BOT_API_URL,
    USE_LOCAL_BOT_API,
    logger,
)


API_BASE = "https://api.telegram.org"


@dataclass(frozen=True, slots=True)
class _RetryConfig:
    attempts: int = 6
    base_delay: float = 2.0  # seconds
    max_delay: float = 30.0  # seconds


_TRANSIENT_MARKERS = (
    "temporarily unavailable",
    "wrong file_id",
    "need to retry",
)


async def _sleep_for_attempt(attempt: int, cfg: _RetryConfig) -> None:
    if attempt >= cfg.attempts:
        return
    delay = min(cfg.base_delay * (2 ** (attempt - 1)), cfg.max_delay)
    await asyncio.sleep(delay)


def _is_transient(description: str | None) -> bool:
    if not description:
        return False
    lowered = description.lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def _build_api_url(bot_token: str, method: str) -> str:
    if USE_LOCAL_BOT_API:
        base = LOCAL_BOT_API_URL.rstrip("/")
        return f"{base}/bot{bot_token}/{method}"
    return f"{API_BASE}/bot{bot_token}/{method}"


def _build_file_url(bot_token: str, file_path: str) -> str:
    if USE_LOCAL_BOT_API:
        base = LOCAL_BOT_API_URL.rstrip("/")
        return f"{base}/file/bot{bot_token}/{file_path}"
    return f"{API_BASE}/file/bot{bot_token}/{file_path}"


async def get_file_info(
    bot_token: str,
    file_id: str,
    *,
    timeout: float = 30.0,
    retry_cfg: _RetryConfig | None = None,
) -> Optional[dict[str, Any]]:
    """Fetch Telegram file metadata, retrying on transient failures."""
    retry_cfg = retry_cfg or _RetryConfig()
    url = _build_api_url(bot_token, "getFile")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retry_cfg.attempts + 1):
            try:
                response = await client.post(url, data={"file_id": file_id})
            except httpx.HTTPError as exc:
                logger.warning(
                    "getFile request failed (attempt %s): %s",
                    attempt,
                    exc,
                )
                await _sleep_for_attempt(attempt, retry_cfg)
                continue

            try:
                payload = response.json()
            except ValueError:
                payload = None

            if response.status_code != 200:
                description = (
                    payload.get("description")
                    if isinstance(payload, dict)
                    else response.text
                )
                logger.warning(
                    "getFile HTTP error (attempt %s, status %s): %s",
                    attempt,
                    response.status_code,
                    description,
                )
                if _is_transient(description):
                    await _sleep_for_attempt(attempt, retry_cfg)
                    continue
                return None

            if payload and payload.get("ok"):
                return payload.get("result")

            description = payload.get("description") if payload else None
            logger.error(
                "getFile returned error (attempt %s, code %s): %s",
                attempt,
                payload.get("error_code") if payload else "unknown",
                description,
            )
            if _is_transient(description):
                await _sleep_for_attempt(attempt, retry_cfg)
                continue
            return None

    return None


async def download_large_file(
    *,
    bot_token: str,
    file_id: str,
    destination: Path,
    chunk_size: int = 65536,
    timeout: float = 300.0,
    retry_cfg: _RetryConfig | None = None,
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
) -> bool:
    """Download a Telegram file with retry/backoff support.
    
    Args:
        progress_callback: Optional async function(downloaded_bytes, total_bytes) called periodically
    """
    retry_cfg = retry_cfg or _RetryConfig()
    destination.parent.mkdir(parents=True, exist_ok=True)

    file_info = await get_file_info(bot_token, file_id, retry_cfg=retry_cfg)
    if not file_info or "file_path" not in file_info:
        logger.error(
            "Failed to obtain file info for download",
            extra={"file_id": file_id},
        )
        return False

    raw_file_path = file_info["file_path"]
    logger.info(
        f"🔍 getFile returned path: {raw_file_path}",
        extra={"file_id": file_id, "raw_path": raw_file_path}
    )
    file_path = raw_file_path
    
    # Если Local Bot API вернул абсолютный путь вида /var/lib/telegram-bot-api/<token>/...
    # надо извлечь относительную часть после <token>/
    if raw_file_path.startswith("/var/lib/telegram-bot-api/"):
        logger.info(f"🔍 Detected local Bot API path, attempting direct copy")
        # Попытка прямого копирования из volume (если он смонтирован)
        local_root = Path(
            os.getenv("TELEGRAM_BOT_API_LOCAL_DIR", "/app/telegram-bot-api-data")
        )
        logger.info(f"🔍 Local root: {local_root}")
        try:
            relative_path = Path(raw_file_path).relative_to("/var/lib/telegram-bot-api")
            local_source = local_root / relative_path
            logger.info(f"🔍 Checking if file exists: {local_source}")
            if local_source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(local_source, destination)
                logger.info(
                    "Copied media file from local Bot API storage",
                    extra={
                        "source": str(local_source),
                        "destination": str(destination),
                    },
                )
                return True
            else:
                logger.warning(f"🔍 File does not exist at {local_source}, falling back to HTTP")
        except ValueError as e:
            logger.warning(f"🔍 Failed to parse relative path: {e}")
        
        # Volume не смонтирован - извлекаем путь для HTTP-скачивания
        # Путь вида: /var/lib/telegram-bot-api/<token>/music/file_6.mp3
        # Local Bot API ожидает путь от /var/lib/telegram-bot-api/: <token>/music/file_6.mp3
        parts = Path(raw_file_path).parts
        if len(parts) >= 5:  # ['/', 'var', 'lib', 'telegram-bot-api', '<token>', 'music', 'file.mp3']
            # Берём всё начиная с <token> (индекс 4)
            file_path = str(Path(*parts[4:]))
        else:
            logger.warning(f"Unexpected Local Bot API path format: {raw_file_path}")
            file_path = raw_file_path.lstrip("/")
    elif file_path.startswith("/"):
        # Обычный случай - просто убираем начальный /
        file_path = file_path.lstrip("/")
    file_url = _build_file_url(bot_token, file_path)

    tmp_path = destination.with_suffix(destination.suffix + ".part")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retry_cfg.attempts + 1):
            try:
                async with client.stream("GET", file_url) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning(
                            "File download HTTP error (attempt %s, status %s): %s",
                            attempt,
                            response.status_code,
                            body.decode("utf-8", errors="ignore"),
                        )
                        await _sleep_for_attempt(attempt, retry_cfg)
                        continue

                    # Get total size from headers
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    with tmp_path.open("wb") as handle:
                        async for chunk in response.aiter_bytes(chunk_size):
                            handle.write(chunk)
                            downloaded += len(chunk)
                            
                            # Call progress callback if provided
                            if progress_callback and total_size > 0:
                                try:
                                    await progress_callback(downloaded, total_size)
                                except Exception as e:
                                    logger.warning(f"Progress callback error: {e}")

                    tmp_path.replace(destination)
                    return True
            except httpx.HTTPError as exc:
                logger.warning(
                    "File download failed (attempt %s): %s",
                    attempt,
                    exc,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Unexpected error during file download (attempt %s)",
                    attempt,
                )

            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

            await _sleep_for_attempt(attempt, retry_cfg)

    logger.error("Exhausted download attempts for file %s", file_id)
    return False


__all__ = ["download_large_file", "get_file_info"]
