from __future__ import annotations

import os
import json
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


@app.on_event("startup")
def load_model():
    global model
    # OpenAI's whisper uses torch under the hood and will utilize CUDA if device='cuda'
    model = whisper.load_model(MODEL_NAME, device=DEVICE)
    print(f"Loaded model {MODEL_NAME} on {DEVICE}")


@app.post("/transcribe")
def transcribe(req: TranscribeRequest):
    file_path = req.file_uri
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="file not found")

    # options could contain language, beam_size etc.
    opts = req.options or {}
    language = opts.get("language")
    beam_size = int(opts.get("beam_size", 5))

    segments = []
    text_parts = []

    # Use OpenAI whisper model to transcribe — it returns a dict with 'text' and 'segments'
    try:
        result = model.transcribe(file_path, beam_size=beam_size, language=language)
        for seg in result.get("segments", []):
            segments.append({
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "text": seg.get("text", ""),
                "confidence": float(seg.get("avg_logprob", 0.0)) if seg.get("avg_logprob") is not None else 0.0,
            })
        text = result.get("text", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "ok",
        "text": text,
        "segments": segments,
        "model": MODEL_NAME,
        "meta": {"file_uri": file_path, "device": DEVICE},
    }
