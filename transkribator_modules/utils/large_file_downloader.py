"""Helpers for downloading large Telegram files with retry logic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
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
LOCAL_BOT_API_DATA_DIR_HOST = os.getenv("LOCAL_BOT_API_DATA_DIR_HOST", "/var/lib/telegram-bot-api").rstrip("/")


def _storage_roots() -> list[Path]:
    """Return candidate directories that may contain cached Bot API files."""
    def _iter_candidates() -> list[str]:
        env_names = (
            "TELEGRAM_BOT_API_LOCAL_DIR",
            "LOCAL_BOT_API_DATA_DIR",
            "LOCAL_BOT_API_DATA_DIR_HOST",
        )
        for name in env_names:
            value = os.getenv(name, "").strip()
            if value:
                yield value
        if LOCAL_BOT_API_DATA_DIR_HOST:
            yield LOCAL_BOT_API_DATA_DIR_HOST
        # Common mount points (containers mount /vpn-api-data; local dev keeps /app/telegram-bot-api-data).
        yield "/vpn-api-data"
        yield "/app/telegram-bot-api-data"
        yield "/var/lib/telegram-bot-api-vpn"
        yield "/var/lib/telegram-bot-api"

    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in _iter_candidates():
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        key = str(path)
        if key and key not in seen:
            seen.add(key)
            roots.append(path)
    return roots


@dataclass(frozen=True, slots=True)
class _RetryConfig:
    # Retry policy: when using local Bot API, we keep it short to allow
    # quick fallback to global API; otherwise keep a bit longer.
    attempts: int = 8
    base_delay: float = 2.0  # seconds
    max_delay: float = 30.0  # seconds


_TRANSIENT_MARKERS = (
    "temporarily unavailable",
    "wrong file_id",
    "need to retry",
)


def _strip_host_prefix(raw_path: str) -> str:
    """Remove /var/lib/telegram-bot-api* prefix if present."""
    normalized = raw_path.lstrip("/")
    if not LOCAL_BOT_API_DATA_DIR_HOST:
        return normalized
    host = LOCAL_BOT_API_DATA_DIR_HOST.lstrip("/")
    if host and normalized.startswith(host):
        normalized = normalized[len(host):].lstrip("/")
    return normalized


def normalize_bot_api_file_path(raw_path: str, bot_token: str) -> str:
    """Normalize file_path returned by Bot API for use in HTTP downloads."""
    without_host = _strip_host_prefix(raw_path)
    token_prefix = f"{bot_token}/"
    if without_host.startswith(token_prefix):
        return without_host[len(token_prefix):]
    return without_host


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
    # Сначала используем локальный Bot API, чтобы получить корректный file_path
    # для данного датацентра/экземпляра. При нехватке — позже сделаем
    # одноразовый fallback на глобальный API.
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
    # Increase default timeout: local bot API may need extra time to fetch
    # large files from Telegram and return file_path.
    # Для локального Bot API даём больше времени на подготовку file_path,
    # особенно для больших файлов. Увеличено до 600 сек (10 минут).
    timeout: float = 180.0 if not USE_LOCAL_BOT_API else 600.0,
    retry_cfg: _RetryConfig | None = None,
) -> Optional[dict[str, Any]]:
    """Fetch Telegram file metadata, retrying on transient failures."""
    logger.info(
        "🔍 get_file_info STARTING",
        extra={"file_id": file_id, "timeout": timeout, "use_local_api": USE_LOCAL_BOT_API}
    )
    if retry_cfg is None:
        retry_cfg = _RetryConfig()
        # Для локального API даём больше времени подготовить file_path
        if USE_LOCAL_BOT_API:
            # Увеличено до 10 попыток с таймаутом 600 сек на каждую.
            # Это позволяет локальному Bot API получить большие файлы от Telegram.
            # Total max time: ~600 сек + retry backoff (до 10 минут).
            object.__setattr__(retry_cfg, 'attempts', 10)
            object.__setattr__(retry_cfg, 'base_delay', 2.0)
            object.__setattr__(retry_cfg, 'max_delay', 20.0)
    url = _build_api_url(bot_token, "getFile")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retry_cfg.attempts + 1):
            start_ts = time.monotonic()
            try:
                logger.debug(
                    "🔍 getFile attempt %s: POST to %s with timeout=%.1f",
                    attempt,
                    url,
                    timeout,
                )
                response = await client.post(url, data={"file_id": file_id})
            except httpx.HTTPError as exc:
                elapsed = time.monotonic() - start_ts
                logger.warning(
                "getFile request FAILED (attempt %s after %.2fs) for file_id=%s: %s",
                attempt,
                elapsed,
                file_id,
                exc,
                )
                await _sleep_for_attempt(attempt, retry_cfg)
                continue

            elapsed = time.monotonic() - start_ts
            logger.info(
                "✅ getFile attempt %s finished in %.2fs (status=%s, content_len=%s)",
                attempt,
                elapsed,
                response.status_code,
                response.headers.get("content-length"),
            )

            try:
                payload = response.json()
            except ValueError:
                # Can't parse JSON - capture raw body for debugging
                text = response.text
                logger.debug(
                    "getFile: failed to parse JSON response (attempt %s). Raw body: %s",
                    attempt,
                    text[:1000],
                )
                payload = None

            if response.status_code != 200:
                description = (
                    payload.get("description")
                    if isinstance(payload, dict)
                    else response.text
                )
                # Log status and a snippet of the body to help debugging local Bot API issues
                body_snippet = (response.text or "")[:1000]
                logger.warning(
                    "getFile HTTP error (attempt %s, status %s) for file_id=%s: %s; body_snippet=%s",
                    attempt,
                    response.status_code,
                    file_id,
                    description,
                    body_snippet,
                )
                if _is_transient(description):
                    await _sleep_for_attempt(attempt, retry_cfg)
                    continue
                return None

            if payload and payload.get("ok"):
                result = payload.get("result") or {}
                # Local Bot API may respond 200/ok while still preparing a file
                # and omit file_path until it's ready. Treat this as transient
                # and keep polling within retry budget.
                if isinstance(result, dict) and "file_path" not in result:
                    logger.info(
                        "getFile ok but NO file_path yet (attempt %s) - payload keys: %s — retrying",
                        attempt,
                        list(result.keys()) if isinstance(result, dict) else "not_dict",
                    )
                    await _sleep_for_attempt(attempt, retry_cfg)
                    continue
                logger.info(
                    "✅ getFile SUCCESS with file_path (attempt %s): %s",
                    attempt,
                    result.get("file_path", "N/A"),
                )
                return result

            description = payload.get("description") if payload else None
            err_code = payload.get("error_code") if isinstance(payload, dict) else "unknown"
            # Include payload snippet for greater visibility when debugging
            payload_snippet = str(payload)[:1000] if payload else None
            logger.error(
                "getFile returned error (attempt %s, code %s) for file_id=%s: %s; payload=%s",
                attempt,
                err_code,
                file_id,
                description,
                payload_snippet,
            )
            if _is_transient(description):
                await _sleep_for_attempt(attempt, retry_cfg)
                continue
            return None

    # Если локальный API не выдал file_path, пробуем один раз глобальный API
    # НО: для больших файлов глобальный API может отказать с "file is too big"
    # Поэтому для локального Bot API мы НЕ пробуем глобальный API, а вместо этого
    # рассчитываем на механизм скачивания через локальное хранилище в download_large_file
    if USE_LOCAL_BOT_API:
        # Для локального Bot API не рекомендуется fallback на глобальный API,
        # так как он может отказать для больших файлов.
        # Вместо этого download_large_file() будет искать файл в локальном кеше.
        logger.warning(
            "❌ getFile EXHAUSTED attempts for local Bot API (timeout or no-file-yet), "
            "skipping global API fallback for local Bot API. "
            "Will attempt to locate file in local storage cache.",
            extra={"file_id": file_id, "attempts": retry_cfg.attempts if retry_cfg else 12}
        )
        return None
    
    # Для глобального API пробуем getFile напрямую
    try:
        fallback_url = f"{API_BASE}/bot{bot_token}/getFile"
        logger.info("Trying global API getFile: %s", fallback_url)
        async with httpx.AsyncClient(timeout=180.0) as fb:
            resp = await fb.post(fallback_url, data={"file_id": file_id})
            status = resp.status_code
            body = None
            try:
                payload = resp.json()
            except ValueError:
                payload = None
                body = (resp.text or "")[:500]

            if status == 200 and payload and payload.get("ok"):
                return payload.get("result") or None
            else:
                logger.warning(
                    "Global getFile HTTP %s; ok=%s; payload_snippet=%s body_snippet=%s",
                    status,
                    payload.get("ok") if isinstance(payload, dict) else None,
                    str(payload)[:500] if payload else None,
                    body,
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Global getFile fallback failed: %s", exc)
    return None


async def download_large_file(
    *,
    bot_token: str,
    file_id: str,
    destination: Path,
    chunk_size: int = 65536,
    # Streaming large downloads can take a long time on slow networks —
    # increase default client timeout to allow completion.
    timeout: float = 900.0,
    retry_cfg: _RetryConfig | None = None,
    progress_callback: Optional[Callable[[int, int], Awaitable[None]]] = None,
    # Опционально: ожидаемый размер файла (в байтах). Позволяет осуществить
    # раннее копирование из кеша локального Bot API до появления file_path,
    # если найдено уникальное совпадение по размеру в недавних файлах.
    expected_size_bytes: Optional[int] = None,
    # Временное окно (сек) для поиска "свежих" файлов в кешe.
    cache_mtime_window_sec: int = 1800,
) -> bool:
    """Download a Telegram file with retry/backoff support.
    
    Args:
        progress_callback: Optional async function(downloaded_bytes, total_bytes) called periodically
    """
    logger.info(
        "🔄 download_large_file START",
        extra={"file_id": file_id, "expected_size_bytes": expected_size_bytes, "timeout": timeout, "destination": str(destination)}
    )
    retry_cfg = retry_cfg or _RetryConfig()
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Попытка раннего копирования из кеша по эвристике размера
    # Делается очень аккуратно: только если есть ровно одно совпадение
    # по размеру в каталоге за недавний период времени.
    try:
        if expected_size_bytes and expected_size_bytes > 0:
            local_roots = _storage_roots()
            for local_root in local_roots:
                if not local_root.exists():
                    continue
                token_dir = local_root / bot_token
                if token_dir.exists():
                    now = time.time()
                    candidates: list[Path] = []
                    try:
                        for p in token_dir.rglob('*'):
                            try:
                                if not p.is_file():
                                    continue
                                st = p.stat()
                                if st.st_size == expected_size_bytes and (now - st.st_mtime) <= cache_mtime_window_sec:
                                    candidates.append(p)
                            except OSError:
                                continue
                    except Exception:
                        # rglob can raise on permission errors; fall back to a conservative scan
                        candidates = []

                    if len(candidates) == 1:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(candidates[0], destination)
                        logger.info(
                            "Early-copied media from cache by size (recursive token scan)",
                            extra={"source": str(candidates[0]), "destination": str(destination), "size": expected_size_bytes, "root": str(local_root)},
                        )
                        return True
    except Exception as e:
        logger.warning("Early cache probe failed: %s", e)

    # Во время ожидания getFile дополнительно проверяем появление файла в локальном кеше
    # (ступенчатый поллинг кеша). Если найден уникальный кандидат по размеру — копируем сразу.
    async def _probe_cache_copy() -> bool:
        """Probe local Bot API storage for a recent file and copy if uniquely matched.

        Two modes:
        - If expected_size_bytes is provided (>0) -> match by exact size and recent mtime.
        - If expected_size_bytes is None/0 -> match by recent mtime only, but require a single candidate.
        """
        try:
            local_roots = _storage_roots()
            for local_root in local_roots:
                if not local_root.exists():
                    continue
                token_dir = local_root / bot_token
                if not token_dir.exists():
                    continue
                now = time.time()
                candidates: list[Path] = []
                try:
                    for p in token_dir.rglob("*"):
                        try:
                            if not p.is_file():
                                continue
                            st = p.stat()
                            # Skip empty files
                            if st.st_size == 0:
                                continue
                            age = now - st.st_mtime
                            if age <= cache_mtime_window_sec:
                                if expected_size_bytes and expected_size_bytes > 0:
                                    if st.st_size == expected_size_bytes:
                                        candidates.append(p)
                                else:
                                    candidates.append(p)
                        except OSError:
                            continue
                except Exception:
                    # rglob can fail on some filesystems/permissions; treat as no candidates
                    candidates = []

                # If exactly one candidate found, copy and return True
                if len(candidates) == 1:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(candidates[0], destination)
                    logger.info(
                        "Early-copied media from cache during polling (recursive token scan)",
                        extra={"source": str(candidates[0]), "destination": str(destination), "root": str(local_root)},
                    )
                    return True

                # Multiple candidates -> try a best-effort selection instead of skipping.
                # Often multiple files can have the same size (e.g. duplicates or reuploads).
                # In that case choose the most recently modified candidate as a heuristic.
                if len(candidates) > 1:
                    try:
                        candidates_sorted = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
                        chosen = candidates_sorted[0]
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy(chosen, destination)
                        logger.info(
                            "Early-copied media from cache by choosing most-recent candidate",
                            extra={
                                "chosen": str(chosen),
                                "candidates_count": len(candidates),
                                "sample": [str(c) for c in candidates[:5]],
                                "root": str(local_root),
                            },
                        )
                        return True
                    except Exception as e:
                        logger.warning("Best-effort cache copy failed: %s", e)
        except Exception as e:
            logger.warning("Cache probe failed: %s", e)
        return False

    file_info = await get_file_info(bot_token, file_id, retry_cfg=retry_cfg)
    logger.info(
        "🔄 get_file_info COMPLETED",
        extra={"file_id": file_id, "has_file_info": bool(file_info), "file_path": file_info.get('file_path', 'N/A') if file_info else 'N/A'}
    )
    if not file_info:
        # Последняя попытка: возможно файл уже появился в кеше tgapi, копируем по эвристике
        logger.info(
            "get_file_info returned no file_path, attempting cache probe",
            extra={"file_id": file_id, "expected_size": expected_size_bytes}
        )
        if await _probe_cache_copy():
            logger.info(
                "✅ Cache probe SUCCESS",
                extra={"file_id": file_id}
            )
            return True
        logger.warning(
            "❌ Cache probe FAILED",
            extra={"file_id": file_id}
        )
    if not file_info or "file_path" not in file_info:
        logger.error(
            "Failed to obtain file info for download (getFile returned no result or missing file_path)",
            extra={
                "file_id": file_id,
                "has_file_info": bool(file_info),
                "expected_size_bytes": expected_size_bytes,
                "use_local_api": USE_LOCAL_BOT_API,
            },
        )
        return False

    raw_file_path = file_info["file_path"]
    logger.info(
        "🔍 getFile returned path: %s",
        raw_file_path,
        extra={"file_id": file_id, "raw_path": raw_file_path},
    )
    # file_path от локального Bot API может быть:
    # 1) относительным, типа "videos/file_123.mp4" (обычно от глобального API)
    # 2) абсолютным путём внутри контейнера Bot API, например
    #    "/var/lib/telegram-bot-api/<bot_token>/videos/file_2"
    # Приведём к относительному виду "videos/<...>" и корректно обработаем
    # локальное копирование из общего тома.
    file_path = normalize_bot_api_file_path(raw_file_path, bot_token)

    # Попытка прямого копирования из каталога локального Bot API
    # Ожидаем путь вида /var/lib/telegram-bot-api/<bot_token>/<file_path>
    try:
        host_relative = _strip_host_prefix(raw_file_path)
        for local_root in _storage_roots():
            if not local_root.exists():
                continue
            # В локальном томе структура: <root>/<bot_token>/<relative_path>
            local_source = local_root / bot_token / file_path
            logger.info(
                "🔍 Checking local Bot API storage",
                extra={"candidate": str(local_source), "root": str(local_root)},
            )
            if local_source.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(local_source, destination)
                logger.info(
                    "Copied media file from local Bot API storage",
                    extra={"source": str(local_source), "destination": str(destination)},
                )
                return True
            if host_relative:
                abs_candidate = local_root / host_relative
                if abs_candidate.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(abs_candidate, destination)
                    logger.info(
                        "Copied media file from local Bot API storage (abs path)",
                        extra={"source": str(abs_candidate), "destination": str(destination)},
                    )
                    return True
    except Exception as e:
        logger.warning("Local storage probe failed: %s", e)
    # Сначала пробуем локальный URL (если включён локальный API), затем глобальный
    file_url = _build_file_url(bot_token, file_path)
    global_file_url = f"{API_BASE}/file/bot{bot_token}/{file_path}"

    tmp_path = destination.with_suffix(destination.suffix + ".part")

    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, retry_cfg.attempts + 1):
            try:
                logger.info(
                    "🌐 Starting HTTP download attempt %s for file_id=%s from %s",
                    attempt,
                    file_id,
                    file_url,
                )
                # 1) Попытка локального URL (если используется локальный API)
                primary_url = file_url if USE_LOCAL_BOT_API else global_file_url
                async with client.stream("GET", primary_url) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning(
                            "File download HTTP error (attempt %s, status %s) from %s: %s",
                            attempt,
                            response.status_code,
                            primary_url,
                            body.decode("utf-8", errors="ignore"),
                        )
                        # One-shot fallback via global API if local URL failed
                        if USE_LOCAL_BOT_API and primary_url != global_file_url:
                            try:
                                logger.info("Trying global file URL fallback: %s", global_file_url)
                                async with client.stream("GET", global_file_url) as gresp:
                                    if gresp.status_code == 200:
                                        total_size = int(gresp.headers.get("content-length", 0))
                                        downloaded = 0
                                        with tmp_path.open("wb") as handle:
                                            async for chunk in gresp.aiter_bytes(chunk_size):
                                                handle.write(chunk)
                                                downloaded += len(chunk)
                                                if progress_callback and total_size > 0:
                                                    try:
                                                        await progress_callback(downloaded, total_size)
                                                    except Exception as e:
                                                        logger.warning(f"Progress callback error: {e}")
                                        tmp_path.replace(destination)
                                        return True
                                    else:
                                        gbody = await gresp.aread()
                                        logger.warning("Global file URL HTTP error (status %s): %s", gresp.status_code, gbody.decode("utf-8", errors="ignore"))
                            except Exception as exc:
                                logger.warning("Global file URL fallback failed: %s", exc)
                        await _sleep_for_attempt(attempt, retry_cfg)
                        continue

                    # Get total size from headers
                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    logger.info(
                        "⬇️ HTTP download response 200 for file_id=%s (attempt %s, total_size=%s)",
                        file_id,
                        attempt,
                        total_size,
                    )

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
                    logger.info(
                        "✅ File download COMPLETED successfully",
                        extra={"file_id": file_id, "attempt": attempt, "destination": str(destination), "total_size": total_size}
                    )
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

    logger.error(
        "❌ Exhausted download attempts for file (after %s attempts)",
        retry_cfg.attempts if retry_cfg else 8,
        extra={"file_id": file_id, "timeout": timeout, "attempts": retry_cfg.attempts if retry_cfg else 8}
    )
    return False


__all__ = ["download_large_file", "get_file_info", "normalize_bot_api_file_path"]
