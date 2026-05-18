# Knowledge PoC: ingest + query (local skeleton)

This document describes how to run the minimal two-service skeleton for the
knowledge / semantic search PoC. The services are intentionally small and
use `knowledge/data/index.json` as the simple shared index store.

Prerequisites
 - Python 3.10+, pip install -r requirements.txt (or just `fastapi`, `uvicorn`, `requests`)
 - Optional: set `OPENROUTER_API_KEY` in `.env` if you want real embeds / LLM calls.

Quick start (local, without Docker)

1. Create a `.env` file (see `env.sample`) and optionally set:

```
OPENROUTER_API_KEY=...
OPENROUTER_API_URL=https://api.openrouter.ai
OPENROUTER_EMBED_MODEL=text-embedding-3-small
OPENROUTER_LLM_MODEL=gpt-4o-mini
```

2. Run ingest service:

```
uvicorn knowledge.ingest_service:app --host 0.0.0.0 --port 8100
```

3. Run query service (new terminal):

```
uvicorn knowledge.query_service:app --host 0.0.0.0 --port 8200
```

4. Demo flow (assumes you have a `result_whisper.json` file):

```
curl -X POST "http://127.0.0.1:8100/ingest/transcript" -H "Content-Type: application/json" -d '{"user_id":"u1","source_id":"demo1","result_path":"/path/to/result_whisper.json"}'

# after a short while (background task finishes), call search:
curl 'http://127.0.0.1:8200/search?q=summary&k=5'

# generate a document
curl -X POST 'http://127.0.0.1:8200/generate' -H 'Content-Type: application/json' -d '{"query":"Prepare a short summary","max_tokens":200}'
```

Notes
- The skeleton writes a very small JSON index to `knowledge/data/index.json`.
- If `OPENROUTER_API_KEY` is not set, the wrapper runs in mock mode and returns
  deterministic mock embeddings and replies. This allows local demos without
  secrets.

Next steps
- Replace the local JSON index with a vector DB (Faiss/Chroma/Milvus) and
  store embeddings separately for efficient retrieval.
- Harden ingestion: dedupe, PII redaction, background worker with retry.
