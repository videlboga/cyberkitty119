"""DeepInfra adapter for transcribe_client."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

try:
    import requests
except Exception:
    requests = None
import uuid
import subprocess
import shlex


class DeepInfraAdapter:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        request_timeout: Optional[int] = None,
    ):
        self.api_key = api_key or os.getenv("DEEPINFRA_API_KEY")
        self.model = model or os.getenv("DEEPINFRA_MODEL") or "openai/whisper-large-v3-turbo"
        self.request_timeout = request_timeout or (60, int(os.getenv("DEEPINFRA_REQUEST_TIMEOUT_SEC", "1800")))

        # Optional: if set, use an SSH alias to forward requests from a remote worker.
        # When this is provided we will scp the file to the remote host and run curl there.
        self.remote_ssh_alias = os.getenv("REMOTE_DEEPINFRA_SSH_ALIAS") or None
        # Optional: if set, forward requests to a stable HTTP relay (e.g., running on proxy host)
        # Relay URL should accept POST /v1/transcribe and forward to DeepInfra.
        self.remote_relay_url = os.getenv("REMOTE_DEEPINFRA_RELAY_URL") or None
        # If set, skip attempting local whisper fallback (useful when local whisper is not available)
        self.disable_local_whisper = os.getenv("DISABLE_LOCAL_WHISPER", "0") in ("1", "true", "yes")

        if not self.api_key:
            raise RuntimeError("DEEPINFRA_API_KEY is required for DeepInfraAdapter")

    def _build_url(self) -> str:
        return f"https://api.deepinfra.com/v1/inference/{self.model}"

    def _build_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _build_payload(self) -> dict:
        payload = {
            "task": os.getenv("DEEPINFRA_TASK", "transcribe"),
            "temperature": os.getenv("DEEPINFRA_TEMPERATURE", "0"),
            "language": os.getenv("DEEPINFRA_LANGUAGE", "ru"),
        }
        return {k: v for k, v in payload.items() if v is not None}

    def _transcribe_file(self, file_path: Path, url: str, headers: dict, payload: dict) -> dict:
        """Transcribe audio file using DeepInfra API with retry logic."""
        # If remote relay URL configured, attempt HTTP relay first
        if self.remote_relay_url:
            try:
                return self._transcribe_via_http_relay(file_path, payload)
            except Exception as e:
                print(f"[WARNING] Remote HTTP relay transcribe failed ({type(e).__name__}), falling back: {e}")

        # If remote ssh alias configured, attempt to perform the request on the remote host via scp+ssh.
        if self.remote_ssh_alias:
            try:
                return self._transcribe_file_via_ssh(file_path, url, headers, payload)
            except Exception as e:  # fall through to local requests implementation on error
                print(f"[WARNING] Remote SSH transcribe failed ({type(e).__name__}), falling back to local requests: {e}")
        query_string = "&".join(f"{k}={v}" for k, v in payload.items())
        url_with_params = f"{url}?{query_string}" if query_string else url
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                with open(file_path, "rb") as fh:
                    files = {"audio": (file_path.name, fh, "application/octet-stream")}
                    if attempt > 0:
                        print(f"[*] Retry {attempt}/{max_retries-1}...")
                    resp = requests.post(url_with_params, headers=headers, files=files, timeout=self.request_timeout)
                
                try:
                    data = resp.json()
                except Exception:
                    resp.raise_for_status()
                    raise RuntimeError("DeepInfra returned non-JSON response")

                text = data.get("text") or data.get("output") or data.get("result") or data.get("transcript") or ""
                segments = data.get("segments") or data.get("chunks") or []
                
                if not text and not segments:
                    if "error" in data:
                        raise RuntimeError(f"DeepInfra API error: {data['error']}")
                    raise RuntimeError("DeepInfra returned 200 but no text present")
                    
                return {
                    "text": text,
                    "segments": segments,
                    "meta": {
                        "provider": "deepinfra",
                        "model": self.model,
                        "language": payload.get("language", "ru"),
                        "attempt": attempt + 1
                    },
                    "status": "ok"
                }
            
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"[*] DeepInfra timeout/connection error (attempt {attempt+1}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[WARNING] DeepInfra failed after {max_retries} attempts, falling back to local Whisper...")
                    return self._transcribe_file_local(file_path)

            except Exception as e:
                print(f"[WARNING] DeepInfra failed ({type(e).__name__})")
                if self.disable_local_whisper:
                    raise
                print("[WARNING] falling back to local Whisper...")
                return self._transcribe_file_local(file_path)
        return self._transcribe_file_local(file_path)

    def _transcribe_via_http_relay(self, file_path: Path, payload: dict) -> dict:
        """Send file to HTTP relay which forwards to DeepInfra."""
        import requests as _requests

        # POST file to configured relay endpoint and parse JSON response.
        with open(file_path, "rb") as fh:
            files = {"audio": (file_path.name, fh, "application/octet-stream")}
            resp = _requests.post(self.remote_relay_url.rstrip("/") + "/v1/transcribe", files=files, data=payload, timeout=self.request_timeout)
            try:
                data = resp.json()
            except Exception:
                resp.raise_for_status()
                raise RuntimeError("DeepInfra relay returned non-JSON response")

        # Accept multiple possible keys returned by various relay implementations
        text = data.get("text") or data.get("output") or data.get("result") or data.get("transcript") or ""
        segments = data.get("segments") or data.get("chunks") or []

        if not text and not segments:
            if "error" in data:
                raise RuntimeError(f"DeepInfra API error (relay): {data['error']}")
            raise RuntimeError("DeepInfra returned 200 but no text present (relay)")

        return {
            "text": text,
            "segments": segments,
            "meta": {"provider": "deepinfra_relay", "model": self.model, "language": payload.get("language", "ru")},
            "status": "ok",
        }

    def _transcribe_file_via_ssh(self, file_path: Path, url: str, headers: dict, payload: dict) -> dict:
        """Copy file to remote host via scp and run curl on the remote side to call DeepInfra.

        Returns parsed dict similar to the normal requests path.
        """
        remote_alias = self.remote_ssh_alias
        remote_tmp = f"/tmp/deepinfra_upload_{uuid.uuid4().hex}{file_path.suffix}"

        # 1) scp file to remote
        scp_cmd = f"scp -q {shlex.quote(str(file_path))} {shlex.quote(remote_alias + ':' + remote_tmp)}"
        subprocess.run(scp_cmd, shell=True, check=True)

        try:
            # 2) build curl command on remote
            # DeepInfra expects form fields (-F), not query parameters
            form_fields = " ".join(f"-F {shlex.quote(k)}={shlex.quote(str(v))}" for k, v in payload.items())
            
            # Use -sS to surface errors and limit max time via --max-time
            curl_cmd = (
                "curl -sS --fail --show-error --max-time 300 "
                f"-H 'Authorization: Bearer {self.api_key}' "
                f"-F 'file=@{remote_tmp}' {form_fields} {shlex.quote(url)}"
            )
            ssh_cmd = f"ssh -o BatchMode=yes {shlex.quote(remote_alias)} {shlex.quote(curl_cmd)}"
            # Run ssh and capture output
            proc = subprocess.run(ssh_cmd, shell=True, check=True, capture_output=True, text=True)
            out = proc.stdout
            # try parse json
            try:
                import json as _json

                data = _json.loads(out)
            except Exception:
                raise RuntimeError("Remote DeepInfra returned non-JSON response")

            # Accept 'transcript' as an alternative key used by some relays
            text = data.get("text") or data.get("output") or data.get("result") or data.get("transcript") or ""
            segments = data.get("segments") or data.get("chunks") or []

            if not text and not segments:
                if "error" in data:
                    raise RuntimeError(f"DeepInfra API error: {data['error']}")
                raise RuntimeError("DeepInfra returned 200 but no text present (remote)")

            return {
                "text": text,
                "segments": segments,
                "meta": {
                    "provider": "deepinfra_remote_ssh",
                    "model": self.model,
                    "language": payload.get("language", "ru"),
                    "remote_tmp": remote_tmp,
                },
                "status": "ok",
            }

        finally:
            # cleanup remote tmp (best-effort)
            try:
                subprocess.run(f"ssh -o BatchMode=yes {shlex.quote(remote_alias)} rm -f {shlex.quote(remote_tmp)}", shell=True)
            except Exception:
                pass

    def _transcribe_file_local(self, file_path: Path) -> dict:
        """Fallback to local Whisper transcription."""
        try:
            import whisper
        except ImportError:
            raise RuntimeError("whisper library not installed. Install with: pip install openai-whisper")
        
        model_size = "base"
        print(f"[*] Loading local Whisper model (size={model_size})...")
        model = whisper.load_model(model_size)
        
        print(f"[*] Transcribing {file_path.name} with local Whisper...")
        result = model.transcribe(str(file_path), language="ru", verbose=False)
        
        text = result.get("text", "").strip()
        segments = result.get("segments", [])
        
        return {
            "text": text,
            "segments": segments,
            "meta": {
                "provider": "local_whisper",
                "model": f"whisper-{model_size}",
                "language": "ru"
            },
            "status": "ok"
        }

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        """Transcribe audio file from URI."""
        if requests is None:
            raise RuntimeError("requests library is required for DeepInfraAdapter")

        path = Path(file_uri)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_uri}")

        url = self._build_url()
        headers = self._build_headers()
        payload = self._build_payload()

        result = self._transcribe_file(path, url, headers, payload)
        provider = result.get("meta", {}).get("provider", "deepinfra_or_local")
        
        return {
            "status": "ok",
            "text": result["text"],
            "segments": result.get("segments", []),
            "model": self.model,
            "meta": {
                "file_uri": file_uri,
                "mode": mode,
                "ts": time.time(),
                "provider": provider,
            },
        }


__all__ = ["DeepInfraAdapter"]
