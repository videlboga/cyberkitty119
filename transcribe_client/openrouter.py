"""OpenRouter adapter for transcribe_client."""
from __future__ import annotations

import os
import time
import base64
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger("transcribe_client.openrouter")

try:
    import requests
except Exception:
    requests = None

MIME_MAP = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "m4a": "audio/mp4",
    "flac": "audio/flac",
    "webm": "audio/webm",
    "aac": "audio/aac",
}


class OpenRouterAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        request_timeout: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("OPENROUTER_WHISPER_MODEL") or "openai/whisper-large-v3-turbo"
        
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
            "HTTP-Referer": self.referer,
            "X-OpenRouter-Title": self.app_name,
        }

    def _get_mime(self, audio_format: str) -> str:
        return MIME_MAP.get(audio_format, "audio/wav")

    def _get_audio_duration_seconds(self, file_path: Path) -> float:
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(file_path)],
                capture_output=True, text=True, timeout=30,
            )
            info = json.loads(result.stdout)
            return float(info.get("format", {}).get("duration", 0))
        except Exception as e:
            logger.warning(f"ffprobe failed: {e}")
            return 0.0

    def _split_audio_into_chunks(self, file_path: Path, chunk_duration_sec: int, tmp_dir: str) -> List[Path]:
        chunk_pattern = os.path.join(tmp_dir, "chunk_%04d.mp3")
        cmd = [
            "ffmpeg", "-y", "-i", str(file_path),
            "-f", "segment",
            "-segment_time", str(chunk_duration_sec),
            "-c", "copy",
            "-reset_timestamps", "1",
            chunk_pattern,
        ]
        logger.info(f"Splitting {file_path.name} into {chunk_duration_sec}s chunks…")
        subprocess.run(cmd, capture_output=True, check=True, timeout=600)
        chunks = sorted(Path(tmp_dir).glob("chunk_*.mp3"))
        logger.info(f"Split produced {len(chunks)} chunks")
        return chunks

    def _transcribe_bytes(self, raw_data: bytes, audio_format: str, start_time: float) -> dict:
        """Send a single audio payload to OpenRouter as multipart/form-data."""
        url = self._build_url()
        headers = self._build_headers()
        mime = self._get_mime(audio_format)

        files = {
            "file": (f"audio.{audio_format}", raw_data, mime),
            "model": (None, self.model),
        }

        max_retries = 3
        last_err = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    timeout=self.request_timeout,
                )
                if resp.status_code in (502, 503, 504) and attempt < max_retries:
                    logger.warning(f"OpenRouter {resp.status_code} attempt {attempt}/{max_retries}, retrying in {2**attempt}s…")
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                result = resp.json()
                elapsed = time.monotonic() - start_time
                return {
                    "status": "ok",
                    "text": result.get("text", ""),
                    "segments": result.get("segments", []),
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
                    try:
                        err_body = e.response.json()
                        err_msg = f"{err_msg} - {err_body}"
                    except Exception:
                        err_msg = f"{err_msg} - {e.response.text[:300]}"
                last_err = err_msg
                if attempt < max_retries:
                    logger.warning(f"OpenRouter attempt {attempt}/{max_retries} failed: {err_msg[:300]}, retrying in {2**attempt}s…")
                    time.sleep(2 ** attempt)
                    continue
                break

        return {
            "status": "error",
            "text": "",
            "segments": [],
            "model": self.model,
            "meta": {
                "error": last_err or "Unknown error",
                "provider": "openrouter",
            },
        }

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe audio file from URI using OpenRouter.

        If the file exceeds OPENROUTER_MAX_FILE_MB (default 20 MB),
        it is automatically split into chunks and the results are joined.
        """
        if requests is None:
            raise RuntimeError("requests library is required for OpenRouterAdapter")

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")

        path = Path(file_uri)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        extension = path.suffix.lower().lstrip(".")
        format_mapping = {"ogg": "ogg", "mp3": "mp3", "wav": "wav", "m4a": "m4a", "flac": "flac"}
        audio_format = format_mapping.get(extension, "wav")

        file_size = path.stat().st_size
        logger.info(f"OpenRouter sending file: {path.name}, size: {file_size} bytes, format: {audio_format}")

        max_bytes = int(os.getenv("OPENROUTER_MAX_FILE_MB", "20")) * 1024 * 1024
        target_chunk_bytes = int(os.getenv("OPENROUTER_CHUNK_FILE_MB", "15")) * 1024 * 1024

        start_time = time.monotonic()

        if file_size <= max_bytes:
            with open(path, "rb") as f:
                raw_data = f.read()
            return self._transcribe_bytes(raw_data, audio_format, start_time)

        # File too large — split into chunks
        duration = self._get_audio_duration_seconds(path)
        if duration <= 0:
            logger.warning("Could not determine audio duration; attempting direct upload despite large size")
            with open(path, "rb") as f:
                raw_data = f.read()
            return self._transcribe_bytes(raw_data, audio_format, start_time)

        bytes_per_sec = file_size / duration
        chunk_duration_sec = max(30, int(target_chunk_bytes / bytes_per_sec))
        logger.info(f"File {file_size/1024/1024:.1f} MB > limit {max_bytes/1024/1024:.0f} MB; "
                    f"splitting {duration:.0f}s audio into {chunk_duration_sec}s chunks")

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                chunks = self._split_audio_into_chunks(path, chunk_duration_sec, tmp_dir)
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"ffmpeg chunking failed: {e.stderr.decode()[:500]}") from e

            all_texts: List[str] = []
            all_segments: List[dict] = []
            time_offset = 0.0

            for i, chunk_path in enumerate(chunks):
                chunk_size = chunk_path.stat().st_size
                logger.info(f"Transcribing chunk {i+1}/{len(chunks)}: {chunk_path.name} ({chunk_size/1024:.0f} KB)")
                with open(chunk_path, "rb") as f:
                    raw_data = f.read()
                result = self._transcribe_bytes(raw_data, "mp3", start_time)
                if result["status"] == "error":
                    logger.error(f"Chunk {i+1} transcription failed: {result['meta'].get('error')}")
                    raise RuntimeError(f"Chunk {i+1}/{len(chunks)} transcription failed: {result['meta'].get('error')}")
                all_texts.append(result["text"])
                for seg in result.get("segments", []):
                    seg = dict(seg)
                    seg["start"] = seg.get("start", 0) + time_offset
                    seg["end"] = seg.get("end", 0) + time_offset
                    all_segments.append(seg)
                time_offset += chunk_duration_sec

        elapsed = time.monotonic() - start_time
        full_text = " ".join(t.strip() for t in all_texts if t.strip())
        return {
            "status": "ok",
            "text": full_text,
            "segments": all_segments,
            "model": self.model,
            "meta": {
                "provider": "openrouter",
                "latency": elapsed,
                "model": self.model,
                "chunks": len(chunks),
            },
        }
