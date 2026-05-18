"""Local HTTP adapter for transcribe_client.

This adapter attempts to POST a JSON payload to a local whisper HTTP service
which is expected to read files from a shared filesystem path.
"""
from __future__ import annotations

from typing import Optional
import os
import json

try:
    import requests
except Exception:  # pragma: no cover - optional runtime dependency
    requests = None


class LocalAdapter:
    def __init__(self, service_url: Optional[str] = None):
        self.service_url = service_url or os.environ.get("WHISPER_SERVICE_URL", "http://localhost:8000")

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        if requests is None:
            raise RuntimeError("requests library is required for LocalAdapter")
        # Be tolerant if the configured service_url already contains the /transcribe path.
        base = self.service_url.rstrip('/')
        if base.endswith('/transcribe'):
            url = base
        else:
            url = f"{base}/transcribe"
        payload = {"file_uri": file_uri, "options": {"mode": mode}}
        # Transcription can be slow on CPU-bound models; use a generous timeout.
        resp = requests.post(url, json=payload, timeout=300)
        try:
            data = resp.json()
        except json.JSONDecodeError:
            resp.raise_for_status()
        return data
