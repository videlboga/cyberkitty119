"""Simple HTTP relay that accepts multipart audio and forwards to DeepInfra.

Run on a stable proxy host and point workers to this relay via
`REMOTE_DEEPINFRA_RELAY_URL` to avoid relying on direct DeepInfra calls from worker hosts.

Usage (on proxy):
  pip install fastapi uvicorn requests
  REMOTE_DEEPINFRA_API_KEY="<key>" uvicorn deepinfra_relay:app --host 0.0.0.0 --port 5000

The relay expects form field `audio` and forwards additional form fields.
"""
from __future__ import annotations

import os
import requests
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI(title="DeepInfra Relay")

DEEPINFRA_API_KEY = os.getenv("REMOTE_DEEPINFRA_API_KEY") or os.getenv("DEEPINFRA_API_KEY")
DEEPINFRA_MODEL = os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo")


@app.post("/v1/transcribe")
async def transcribe(audio: UploadFile = File(...), task: str = Form("transcribe"), language: str = Form("ru")):
    if not DEEPINFRA_API_KEY:
        raise HTTPException(status_code=500, detail="DeepInfra API key not configured on relay")

    url = f"https://api.deepinfra.com/v1/inference/{DEEPINFRA_MODEL}"
    headers = {"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}

    files = {"audio": (audio.filename or "upload", await audio.read(), "application/octet-stream")}
    data = {"task": task, "language": language}

    try:
        resp = requests.post(url, headers=headers, files=files, data=data, timeout=300)
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}")

    try:
        payload = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Upstream returned non-JSON response")

    return JSONResponse(status_code=resp.status_code, content=payload)
