"""Adapter that runs the di_worker container/CLI to produce transcription.

This is a minimal implementation that shells out to a configured docker
command. It expects the di_worker image to write a JSON result to a known
output path which this adapter then reads.
"""
from __future__ import annotations

import os
import json
import subprocess
from typing import Optional


class DiWorkerAdapter:
    def __init__(self, image: Optional[str] = None, run_opts: Optional[str] = None):
        self.image = image or os.environ.get("DI_WORKER_IMAGE", "cyberkitty119-di_worker:latest")
        self.run_opts = run_opts or os.environ.get("DI_WORKER_RUN_OPTS", "")

    def transcribe(self, file_uri: str, mode: Optional[str] = None) -> dict:
        # If caller requests local mode, delegate to LocalAdapter (call local whisper HTTP)
        # This allows di_worker to offer 'local' operation mode that uses an HTTP
        # whisper service instead of launching the container.
        # Allow several common truthy values so enabling local-only behavior is easy
        force_local = os.environ.get("DI_WORKER_FORCE_LOCAL", "")
        if (mode or "").lower() == "local" or force_local.lower() in ("1", "true", "yes"):
            # import locally to avoid adding a hard dependency at module import time
            try:
                from .local import LocalAdapter
            except Exception:  # pragma: no cover - defensive
                raise RuntimeError("LocalAdapter is required for local mode")

            local_url = os.environ.get("WHISPER_SERVICE_URL")
            adapter = LocalAdapter(service_url=local_url)
            return adapter.transcribe(file_uri, mode="local")

        # For simplicity, mount the parent dir of file_uri into /data and write output to /data/out.json
        host_path = os.path.abspath(file_uri)
        host_dir = os.path.dirname(host_path)
        out_path = os.path.join(host_dir, "di_worker_out.json")
        # Ensure there is a prepared mono/compressed file for downstream tools that
        # may not handle multi-channel audio. Create a prepared WAV (mono, 16k, PCM)
        # next to the source file to avoid surprising tensor shape errors.
        stem = os.path.splitext(os.path.basename(host_path))[0]
        prepared_name = f"{stem}_prep.wav"
        prepared_path = os.path.join(host_dir, prepared_name)
        # Only (re)create prepared file if it does not exist or if explicitly forced
        force_prepare = os.environ.get("DI_WORKER_FORCE_PREPARE", "0").lower() in ("1", "true", "yes")
        if (not os.path.exists(prepared_path)) or force_prepare:
            ffmpeg_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                host_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                prepared_path,
            ]
            # Run ffmpeg; if it fails, let the exception propagate so caller sees error
            subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Use the di_worker image's supported command 'run_chunk_scan' instead of 'process'.
        # Build argv list to avoid shell quoting problems with spaces/non-ascii paths.
        base_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{host_dir}:/data",
        ]
        # If run_opts provided, split into args (allow additional docker flags)
        if self.run_opts:
            base_cmd += self.run_opts.split()

        # Use the prepared file path inside the container if created
        container_input = os.path.basename(prepared_path) if os.path.exists(prepared_path) else os.path.basename(host_path)
        base_cmd += [self.image, "run_chunk_scan", f"/data/{container_input}", f"/data/{os.path.basename(out_path)}"]

        # Run the di_worker container
        subprocess.run(base_cmd, check=True)

        # The di_worker may write a directory named like the out_path containing multiple
        # per-run JSONs (result_1.json, result_2.json...). Handle both cases.
        if os.path.isdir(out_path):
            results = []
            for name in sorted(os.listdir(out_path)):
                if name.endswith('.json'):
                    p = os.path.join(out_path, name)
                    try:
                        with open(p, 'r', encoding='utf-8') as fh:
                            results.append(json.load(fh))
                    except Exception:
                        # skip unreadable files
                        continue
            return {"results": results}
        else:
            with open(out_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data
