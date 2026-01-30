#!/usr/bin/env python3
"""Long‑lived transcription service using faster‑whisper.

- Loads a specified model (default: medium) once on startup (so container can stay alive).
- Exposes HTTP endpoints:
  - GET /health
  - POST /transcribe (multipart file upload or JSON with existing server path)

Usage (dev):
  pip install fastapi uvicorn faster-whisper
  UVICORN_CMD: uvicorn tools.whisper_service:app --host 0.0.0.0 --port 8080 --workers 1

Environment variables:
  MODEL_ID (default: "medium")
  DEVICE (default: "cuda" if available else "cpu")
  MAX_CONCURRENCY (default: 2) — limits concurrent transcriptions
  OUT_DIR (optional) — directory to write per-request outputs

Design notes:
- We use a ThreadPoolExecutor to run blocking faster_whisper calls so the async server stays responsive.
- The model is stored in the module global `MODEL` and reused for all requests.
"""

import os
import time
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

MODEL = None
MODEL_NAME = os.environ.get('MODEL_ID', 'medium')
DEVICE = os.environ.get('DEVICE', 'cuda')
MAX_CONCURRENCY = int(os.environ.get('MAX_CONCURRENCY', '2'))
OUT_DIR = os.environ.get('OUT_DIR', '/tmp/whisper_service_out')

# executor for blocking model calls
EXEC = ThreadPoolExecutor(max_workers=MAX_CONCURRENCY)
SEM = asyncio.Semaphore(MAX_CONCURRENCY)

@app.on_event('startup')
def load_model():
    global MODEL, MODEL_NAME, DEVICE
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        raise RuntimeError(f'Failed to import faster_whisper: {e}')
    t0 = time.time()
    MODEL = WhisperModel(MODEL_NAME, device=DEVICE)
    load_time = time.time() - t0
    app.state.model_load_time = load_time
    # ensure out dir exists
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"Loaded model {MODEL_NAME} on {DEVICE} in {load_time:.2f}s")

@app.get('/health')
def health():
    return {'status': 'ok', 'model': MODEL_NAME, 'device': DEVICE, 'load_time_s': getattr(app.state, 'model_load_time', None)}

async def transcribe_file_blob(data: bytes, filename: str = 'upload.wav', language: Optional[str] = 'ru'):
    # write to a temp file
    tmp = Path(OUT_DIR) / f'tmp_{int(time.time()*1000)}_{filename}'
    tmp.write_bytes(data)
    try:
        # run blocking transcription in threadpool
        loop = asyncio.get_running_loop()
        t0 = time.time()
        segments, info = await loop.run_in_executor(EXEC, lambda: MODEL.transcribe(str(tmp), language=language))
        wall = time.time() - t0
        text = ''.join([s.text for s in segments]).strip()
        return {'text': text, 'audio_duration': getattr(info, 'duration', None), 'wall_time_s': wall}
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass

@app.post('/transcribe')
async def transcribe(file: Optional[UploadFile] = File(None), path: Optional[str] = Form(None), language: Optional[str] = Form('ru')):
    """Accepts either an uploaded file (multipart/form-data) or a server-side path (form field `path`).
    Returns JSON: { text, audio_duration, wall_time_s }
    """
    async with SEM:
        if file is None and not path:
            raise HTTPException(status_code=400, detail='Either file upload or path must be provided')

        if file is not None:
            data = await file.read()
            result = await transcribe_file_blob(data, filename=file.filename or 'upload.wav', language=language)
        else:
            # path provided — ensure it's a safe absolute path
            p = Path(path)
            if not p.exists():
                raise HTTPException(status_code=404, detail='Provided path not found')
            loop = asyncio.get_running_loop()
            t0 = time.time()
            segments, info = await loop.run_in_executor(EXEC, lambda: MODEL.transcribe(str(p), language=language))
            wall = time.time() - t0
            text = ''.join([s.text for s in segments]).strip()
            result = {'text': text, 'audio_duration': getattr(info, 'duration', None), 'wall_time_s': wall}

        # optionally write per-request output
        safe_name = f"req_{int(time.time()*1000)}.json"
        outp = Path(OUT_DIR) / safe_name
        with outp.open('w', encoding='utf-8') as fh:
            json.dump({'model': MODEL_NAME, 'device': DEVICE, **result}, fh, ensure_ascii=False)
        result['saved_json'] = str(outp)
        return JSONResponse(result)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('tools.whisper_service:app', host='0.0.0.0', port=8080, workers=1)
