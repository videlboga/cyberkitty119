"""Lightweight transcribe_client abstraction.

Provides TranscribeClient which unifies calls to different ASR backends
(`local` HTTP service, `di_worker` container runner, or `stub` for tests).

API is intentionally tiny: TranscribeClient.transcribe(file_uri, mode)
returns a dict TranscriptionResult.
"""
from __future__ import annotations

from typing import Optional

from .stub import StubAdapter


class TranscriptionError(RuntimeError):
    pass


class TranscribeClient:
    def __init__(self, default_mode: str = "auto", adapter: Optional[object] = None):
        self.default_mode = default_mode
        # adapter is used in tests to inject stub/local behavior
        self._adapter = adapter or StubAdapter()

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe given file_uri using selected mode.

        mode: 'auto'|'local'|'di_worker'|'stub'
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
