"""OpenRouter adapter for transcribe_client."""
from __future__ import annotations

import os
import time
import base64
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("transcribe_client.openrouter")

try:
    import requests
except Exception:
    requests = None


class OpenRouterAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        request_timeout: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_WHISPER_MODEL") or "openai/whisper-large-v3"
        
        # Determine timeout: (connect_timeout, read_timeout)
        timeout_env = os.getenv("OPENROUTER_REQUEST_TIMEOUT_SEC", "1800")
        try:
            timeout_val = int(timeout_env)
        except ValueError:
            timeout_val = 1800
        self.request_timeout = request_timeout or (60, timeout_val)
        
        self.referer = os.getenv("OPENROUTER_REFERER", "https://transkribator.local")
        self.app_name = os.getenv("OPENROUTER_APP_NAME", "CyberKitty")

    def _build_url(self) -> str:
        return "https://openrouter.ai/api/v1/audio/transcriptions"

    def _build_headers(self) -> dict:
        auth_header = f"Bearer {self.api_key}" if self.api_key else ""
        return {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "HTTP-Referer": self.referer,
            "X-Title": self.app_name,
        }

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe audio file from URI using OpenRouter."""
        if requests is None:
            raise RuntimeError("requests library is required for OpenRouterAdapter")
            
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")

        path = Path(file_uri)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        with open(path, "rb") as f:
            raw_data = f.read()
            base64_audio = base64.b64encode(raw_data).decode("utf-8")

        # Audio format inference
        extension = path.suffix.lower().lstrip(".")
        format_mapping = {"ogg": "ogg", "mp3": "mp3", "wav": "wav", "m4a": "m4a", "flac": "flac"}
        audio_format = format_mapping.get(extension, "wav") # Default to wav
        
        logger.info(f"OpenRouter sending file: {path.name}, size: {len(raw_data)} bytes, extension: {extension}, payload_format: {audio_format}")

        url = self._build_url()
        headers = self._build_headers()
        
        payload = {
            "model": self.model,
            "input_audio": {
                "data": base64_audio,
                "format": audio_format
            }
        }
        
        start_time = time.monotonic()
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=json.dumps(payload),
                timeout=self.request_timeout
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("text", "")
            
            elapsed = time.monotonic() - start_time
            return {
                "status": "ok",
                "text": text,
                "segments": data.get("segments", []),
                "model": self.model,
                "meta": {
                    "provider": "openrouter",
                    "latency": elapsed,
                    "model": self.model,
                },
            }
        except requests.exceptions.RequestException as e:
            err_msg = str(e)
            if hasattr(e, "response") and e.response is not None:
                err_msg = f"{err_msg} - {e.response.text}"
            
            return {
                "status": "error",
                "text": "",
                "segments": [],
                "model": self.model,
                "meta": {
                    "error": err_msg,
                    "provider": "openrouter"
                }
            }

