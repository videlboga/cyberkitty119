"""Lightweight transcribe_client abstraction.

Provides TranscribeClient which unifies calls to different ASR backends
(`local` HTTP service, `di_worker` container runner, or `stub` for tests).

API is intentionally tiny: TranscribeClient.transcribe(file_uri, mode)
returns a dict TranscriptionResult.
"""
from __future__ import annotations

import os
from typing import Optional

from .stub import StubAdapter
try:  # optional, only when OPENROUTER_API_KEY provided
    from .openrouter import OpenRouterAdapter
except Exception:
    OpenRouterAdapter = None  # type: ignore

try:  # optional, only when DEEPINFRA_API_KEY provided
    from .deepinfra import DeepInfraAdapter
except Exception:  # pragma: no cover - keep lazy import errors from breaking stub/local
    DeepInfraAdapter = None  # type: ignore

try:  # optional GPU adapter
    from .gpu import GPUAdapter
except Exception:  # pragma: no cover - keep lazy import errors from breaking other adapters
    GPUAdapter = None  # type: ignore


class TranscriptionError(RuntimeError):
    pass


def _resolve_default_adapter(default_mode: Optional[str]) -> object:
    """Pick adapter based on env or requested mode.

    Priority:
    1) Explicit env TRANSCRIBE_CLIENT_ADAPTER
    2) default_mode (from caller)
    3) auto -> prefer DeepInfra if key present, else GPU if available, else Local if WHISPER_SERVICE_URL, else di_worker, else stub
    """

    adapter_hint = (os.getenv("TRANSCRIBE_CLIENT_ADAPTER") or default_mode or "auto").strip().lower()

    # OpenRouter
    if adapter_hint in {"openrouter"}:
        if OpenRouterAdapter:
            return OpenRouterAdapter()

    # GPU Whisper adapter - uses local GPU pipeline
    if adapter_hint in {"gpu", "gpu_whisper", "cuda"}:
        if GPUAdapter:
            try:
                return GPUAdapter()
            except Exception:
                pass  # fallback below

    # DeepInfra (remote) - preferred when key is present
    if adapter_hint in {"deepinfra", "remote"}:
        if DeepInfraAdapter:
            return DeepInfraAdapter()

    # Local HTTP whisper
    if adapter_hint in {"local", "http", "whisper"}:
        try:
            from .local import LocalAdapter
            service_url = os.getenv("WHISPER_SERVICE_URL")
            return LocalAdapter(service_url=service_url)
        except Exception:
            pass  # fallback below

    # di_worker container adapter
    if adapter_hint in {"di_worker", "docker", "worker"}:
        try:
            from .di_worker import DiWorkerAdapter
            run_opts = os.getenv("DI_WORKER_RUN_OPTS")
            image = os.getenv("DI_WORKER_IMAGE")
            return DiWorkerAdapter(image=image, run_opts=run_opts)
        except Exception:
            pass  # fallback below

    # Auto mode: prefer DeepInfra if configured, else GPU, else Local, else di_worker, else stub
    if adapter_hint in {"auto", ""}:
        if OpenRouterAdapter and os.getenv("OPENROUTER_API_KEY"):
            try:
                return OpenRouterAdapter()
            except Exception:
                pass
        if DeepInfraAdapter and os.getenv("DEEPINFRA_API_KEY"):
            try:
                return DeepInfraAdapter()
            except Exception:
                pass
        # Try GPU adapter
        if GPUAdapter:
            try:
                return GPUAdapter()
            except Exception:
                pass
        service_url = os.getenv("WHISPER_SERVICE_URL")
        if service_url:
            try:
                from .local import LocalAdapter
                return LocalAdapter(service_url=service_url)
            except Exception:
                pass
        try:
            from .di_worker import DiWorkerAdapter
            run_opts = os.getenv("DI_WORKER_RUN_OPTS")
            image = os.getenv("DI_WORKER_IMAGE")
            return DiWorkerAdapter(image=image, run_opts=run_opts)
        except Exception:
            pass

    # Default stub adapter to keep behaviour deterministic if nothing else works.
    return StubAdapter()


class TranscribeClient:
    def __init__(self, default_mode: str = "auto", adapter: Optional[object] = None):
        self.default_mode = default_mode
        # adapter is used in tests to inject stub/local behavior
        self._adapter = adapter or _resolve_default_adapter(default_mode)

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe given file_uri using selected mode.

        mode: 'auto'|'local'|'di_worker'|'stub'|'deepinfra'
        Returns TranscriptionResult dict with keys: status, text, segments, meta
        """
        use_mode = mode or self.default_mode
        # Adapter must implement transcribe(file_uri, mode)
        try:
            result = self._adapter.transcribe(file_uri, mode=use_mode)
        except Exception as exc:  # pragma: no cover - surface errors
            raise TranscriptionError(str(exc))
        return result


__all__ = ["TranscribeClient", "TranscriptionError"]
