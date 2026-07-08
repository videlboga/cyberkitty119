"""OpenRouter adapter for transcribe_client."""
from __future__ import annotations

import os
import time
import base64
import json
import logging
import random
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

    def _get_audio_duration_seconds(self, file_path: Path) -> float:
        """Return audio duration in seconds via ffprobe, or 0 on failure."""
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
        """Split audio into equal-duration MP3 chunks using ffmpeg segment muxer."""
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

    def _compute_backoff(self, attempt: int, response=None) -> float:
        """Exponential backoff with jitter, capped at 30s.

        If a 429 response includes a Retry-After header, honour it
        (capped at 60s) instead of the computed backoff.
        """
        retry_after = None
        if response is not None:
            try:
                raw_ra = response.headers.get("Retry-After")
                if raw_ra:
                    retry_after = min(float(raw_ra), 60.0)
            except (TypeError, ValueError):
                retry_after = None
        if retry_after is not None:
            return retry_after
        base = min(2 ** attempt, 30)
        jitter = random.uniform(0, base * 0.1)
        return base + jitter

    def _transcribe_bytes(self, raw_data: bytes, audio_format: str, start_time: float) -> dict:
        """Send a single raw audio payload to OpenRouter as base64 JSON."""
        if requests is None:
            return {
                "status": "error",
                "text": "",
                "segments": [],
                "model": self.model,
                "meta": {"error": "requests library not available", "provider": "openrouter"},
            }

        base64_audio = base64.b64encode(raw_data).decode("utf-8")
        url = self._build_url()
        headers = self._build_headers()
        payload = {
            "model": self.model,
            "input_audio": {
                "data": base64_audio,
                "format": audio_format,
            }
        }

        try:
            max_retries = int(os.getenv("OPENROUTER_MAX_RETRIES", "6"))
        except ValueError:
            max_retries = 6

        retry_statuses = {429, 502, 503, 504}
        last_err = None
        last_status = None
        rate_limited = False

        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    data=json.dumps(payload),
                    timeout=self.request_timeout,
                )
                last_status = resp.status_code

                if resp.status_code in retry_statuses:
                    rate_limited = rate_limited or resp.status_code == 429
                    # Build error detail from response body for logging/meta
                    try:
                        err_body = resp.json()
                        last_err = f"HTTP {resp.status_code}: {err_body}"
                    except Exception:
                        last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"

                    if attempt < max_retries:
                        backoff = self._compute_backoff(attempt, resp)
                        logger.warning(
                            "OpenRouter %s attempt %d/%d, retrying in %.1fs",
                            resp.status_code,
                            attempt,
                            max_retries,
                            backoff,
                            extra={
                                "attempt": attempt,
                                "status": resp.status_code,
                                "backoff_sec": round(backoff, 1),
                            },
                        )
                        time.sleep(backoff)
                        continue
                    # Retries exhausted — fall through to error return
                    break

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
                    last_status = e.response.status_code
                    rate_limited = rate_limited or e.response.status_code == 429
                    try:
                        err_body = e.response.json()
                        err_msg = f"{err_msg} - {err_body}"
                    except Exception:
                        err_msg = f"{err_msg} - {e.response.text[:300]}"
                last_err = err_msg
                if attempt < max_retries:
                    backoff = self._compute_backoff(attempt, e.response if hasattr(e, "response") else None)
                    logger.warning(
                        "OpenRouter attempt %d/%d failed: %s, retrying in %.1fs",
                        attempt,
                        max_retries,
                        err_msg[:300],
                        backoff,
                        extra={
                            "attempt": attempt,
                            "status": last_status or 0,
                            "backoff_sec": round(backoff, 1),
                        },
                    )
                    time.sleep(backoff)
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
                "rate_limited": rate_limited,
            },
        }

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe audio file from URI using OpenRouter.

        If the compressed file exceeds OPENROUTER_MAX_FILE_MB (default 20 MB),
        the file is automatically split into chunks and the results are joined.
        """
        if requests is None:
            raise RuntimeError("requests library is required for OpenRouterAdapter")

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set.")

        path = Path(file_uri)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        # Audio format inference
        extension = path.suffix.lower().lstrip(".")
        format_mapping = {"ogg": "ogg", "mp3": "mp3", "wav": "wav", "m4a": "m4a", "flac": "flac"}
        audio_format = format_mapping.get(extension, "wav")

        file_size = path.stat().st_size
        logger.info(f"OpenRouter sending file: {path.name}, size: {file_size} bytes, format: {audio_format}")

        # base64 encoding inflates size by ~33%, so Cloudflare/OpenRouter limit on JSON body
        # is effectively ~7.5 MB binary → ~10 MB base64. Use 5 MB binary to be safe.
        max_bytes = int(os.getenv("OPENROUTER_MAX_FILE_MB", "5")) * 1024 * 1024
        # target chunk size: also 5 MB binary
        target_chunk_bytes = int(os.getenv("OPENROUTER_CHUNK_FILE_MB", "5")) * 1024 * 1024

        start_time = time.monotonic()

        if file_size <= max_bytes:
            # Small enough — send directly
            with open(path, "rb") as f:
                raw_data = f.read()
            return self._transcribe_bytes(raw_data, audio_format, start_time)

        # File is too large — split into chunks
        # Aim for chunks ~15 MB. Estimate duration from bitrate or ffprobe.
        duration = self._get_audio_duration_seconds(path)
        if duration <= 0:
            logger.warning("Could not determine audio duration; attempting direct upload despite large size")
            with open(path, "rb") as f:
                raw_data = f.read()
            return self._transcribe_bytes(raw_data, audio_format, start_time)

        # Each target chunk ≤ target_chunk_bytes → calc max seconds per chunk
        bytes_per_sec = file_size / duration
        chunk_duration_sec = max(30, int(target_chunk_bytes / bytes_per_sec))
        logger.info(f"File {file_size/1024/1024:.1f} MB > limit {max_bytes/1024/1024:.0f} MB; "
                    f"splitting {duration:.0f}s audio into {chunk_duration_sec}s chunks (~{target_chunk_bytes//1024//1024} MB each)")

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
                    err_str = str(result["meta"].get("error", ""))
                    chunk_rate_limited = result["meta"].get("rate_limited", False)
                    if "429" in err_str and i + 1 < len(chunks):
                        throttle_sec = int(os.getenv("OPENROUTER_429_THROTTLE_SEC", "30"))
                        logger.warning(
                            f"Chunk {i+1}/{len(chunks)} hit 429 rate limit; "
                            f"sleeping {throttle_sec}s before next chunk"
                        )
                        time.sleep(throttle_sec)
                        time_offset += chunk_duration_sec
                        continue
                    logger.error(f"Chunk {i+1} transcription failed: {result['meta'].get('error')}")
                    # Return error dict with rate_limited flag instead of raising,
                    # so callers can initiate fallback.
                    return {
                        "status": "error",
                        "text": "",
                        "segments": [],
                        "model": self.model,
                        "meta": {
                            "error": f"Chunk {i+1}/{len(chunks)} transcription failed: {result['meta'].get('error')}",
                            "provider": "openrouter",
                            "rate_limited": chunk_rate_limited,
                        },
                    }
                all_texts.append(result["text"])
                # Offset segment timestamps
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
