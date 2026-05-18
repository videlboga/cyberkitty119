from __future__ import annotations

import os
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import whisper
from typing import Optional

app = FastAPI(title="Real Whisper HTTP")


class TranscribeRequest(BaseModel):
    file_uri: str
    options: Optional[dict] = None


MODEL_NAME = os.environ.get("WHISPER_MODEL", "medium")
DEVICE = os.environ.get("WHISPER_DEVICE", "cuda")
COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE", "float16")
MAX_CONCURRENCY = max(1, int(os.environ.get("WHISPER_MAX_CONCURRENCY", "1")))


@app.on_event("startup")
def load_model():
    global model, _executor, _semaphore
    # OpenAI's whisper uses torch under the hood and will utilize CUDA if device='cuda'
    model = whisper.load_model(MODEL_NAME, device=DEVICE)
    _executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
    _semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    print(f"Loaded model {MODEL_NAME} on {DEVICE} (max concurrency: {MAX_CONCURRENCY})")


@app.get('/health')
def health():
    return {"status": "ok", "model": MODEL_NAME, "device": DEVICE}


def _run_transcription(file_path: str, language: Optional[str], beam_size: int):
    segments = []
    result = model.transcribe(file_path, beam_size=beam_size, language=language)
    for seg in result.get("segments", []):
        segments.append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": seg.get("text", ""),
            "confidence": float(seg.get("avg_logprob", 0.0)) if seg.get("avg_logprob") is not None else 0.0,
        })
    text = result.get("text", "")
    return text, segments


@app.post("/transcribe")
async def transcribe(req: TranscribeRequest):
    file_path = req.file_uri
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="file not found")

    opts = req.options or {}
    language = opts.get("language")
    beam_size = int(opts.get("beam_size", 5))

    await _semaphore.acquire()
    try:
        loop = asyncio.get_running_loop()
        try:
            text, segments = await loop.run_in_executor(
                _executor,
                _run_transcription,
                file_path,
                language,
                beam_size,
            )
        except Exception as exc:  # whisper failure
            raise HTTPException(status_code=500, detail=str(exc))
    finally:
        _semaphore.release()

    return {
        "status": "ok",
        "text": text,
        "segments": segments,
        "model": MODEL_NAME,
        "meta": {"file_uri": file_path, "device": DEVICE},
    }
