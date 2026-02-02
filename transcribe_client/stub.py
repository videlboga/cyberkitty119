"""Stub adapter for transcribe_client used in tests and local development."""
from __future__ import annotations

import time
from typing import Optional


class StubAdapter:
    def __init__(self, text: str | None = None):
        self.text = text or "This is a stub transcription."

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        # Return a deterministic result quickly for tests.
        now = time.time()
        return {
            "status": "ok",
            "text": self.text,
            "segments": [
                {"start": 0.0, "end": 1.0, "text": self.text, "confidence": 0.99}
            ],
            "model": "stub",
            "meta": {"file_uri": file_uri, "mode": mode, "ts": now},
        }
