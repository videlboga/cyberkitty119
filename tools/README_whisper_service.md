Whisper long-lived service (tools/whisper_service.py)

Purpose
- Keep a GPU/CPU process alive with a loaded faster-whisper model (default: `medium`).
- Accept transcription requests over HTTP and avoid paying the model-load penalty each time.

Quick start (local)

1) Create a virtualenv and install deps (or use your existing `.venv_whisper_min`):

```bash
python -m venv .venv_whisper_service
. .venv_whisper_service/bin/activate
pip install fastapi uvicorn faster-whisper
```

2) Start the service (example using CUDA):

```bash
export MODEL_ID=medium
export DEVICE=cuda
export MAX_CONCURRENCY=2
export OUT_DIR=/tmp/whisper_service_out
uvicorn tools.whisper_service:app --host 0.0.0.0 --port 8080 --workers 1
```

3) Test with curl (upload file):

```bash
curl -F "file=@/tmp/run_N14_chunks_big/chunk_000.wav" http://127.0.0.1:8080/transcribe
```

Or request server-side path (if service can access the file):

```bash
curl -X POST -F "path=/tmp/run_N14_chunks_big/chunk_000.wav" http://127.0.0.1:8080/transcribe
```

Docker (suggested)
- Build a runtime image with `faster-whisper` and CUDA/onnxruntime GPU support.
- Start container with GPU access and keep it running; the service will load the model once on container start.

Notes
- The service limits concurrent transcriptions via `MAX_CONCURRENCY` to avoid OOM on GPU.
- The service writes per-request JSON outputs to `OUT_DIR` (default `/tmp/whisper_service_out`).
- For production, run under a process manager, attach logging, and secure endpoints (auth/ACL).
