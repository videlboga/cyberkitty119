"""Factory helpers for media job pipeline services."""

from __future__ import annotations

import importlib
from typing import Any, Callable, Mapping, Optional

from transkribator_modules.config import logger

from .services import (
    MediaPipelineServices,
    default_media_services,
)


def _load_callable(path: str) -> Callable[..., Any]:
    module_name, _, attr = path.rpartition(":")
    if not module_name:
        raise ValueError(f"Invalid callable path '{path}'. Expected 'module:attr'.")
    module = importlib.import_module(module_name)
    target = getattr(module, attr, None)
    if target is None:
        raise AttributeError(f"{module_name!r} has no attribute {attr!r}")
    if not callable(target):
        raise TypeError(f"{path!r} is not callable.")
    return target


def build_services(
    config: Optional[Mapping[str, Any]] = None,
) -> MediaPipelineServices:
    """Build service collection for media pipeline."""

    base_replacements: dict[str, Callable[..., Any]] = {}
    normalized_config = dict(config or {})

    # Автоматически подменяем download-функцию на vk_ytdlp_download_mp3, если указана авто-настройка.
    from .services import vk_ytdlp_download_mp3
    if normalized_config.get("download") == "auto_vk_ytdlp":
        base_replacements["download"] = vk_ytdlp_download_mp3
        normalized_config.pop("download", None)

    if not normalized_config:
        return default_media_services()

    prepare_fn = normalized_config.get("prepare")
    download_fn = normalized_config.get("download")
    transcribe_fn = normalized_config.get("transcribe")
    finalize_fn = normalized_config.get("finalize")
    deliver_fn = normalized_config.get("deliver")
    cleanup_fn = normalized_config.get("cleanup")

    replacements: dict[str, Callable[..., Any]] = dict(base_replacements)

    for key, candidate in (
        ("prepare", prepare_fn),
        ("download", download_fn),
        ("transcribe", transcribe_fn),
        ("finalize", finalize_fn),
        ("deliver", deliver_fn),
        ("cleanup", cleanup_fn),
    ):
        if not candidate:
            continue
        if isinstance(candidate, str):
            candidate = _load_callable(candidate)
        if not callable(candidate):
            raise TypeError(f"Service override for '{key}' must be callable.")
        replacements[key] = candidate

    base = default_media_services()
    prepared_services = MediaPipelineServices(
        prepare=replacements.get("prepare", base.prepare),
        download=replacements.get("download", base.download),
        transcribe=replacements.get("transcribe", base.transcribe),
        finalize=replacements.get("finalize", base.finalize),
        deliver=replacements.get("deliver", base.deliver),
        cleanup=replacements.get("cleanup", base.cleanup),
    )

    logger.debug(
        "Media services constructed",
        extra={
            "overrides": sorted(replacements.keys()),
        },
    )
    return prepared_services


__all__ = ["build_services"]
