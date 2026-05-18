"""Ingest service: accept text documents, compute embeddings and store them."""
from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
except Exception:  # pragma: no cover - allow tests to run without fastapi installed
    class HTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str | None = None):
            super().__init__(detail or "HTTPException")

    class FastAPI:  # minimal placeholder so module imports in tests
        def __init__(self, *args, **kwargs):
            pass
        def post(self, path: str):
            def _decorator(fn):
                return fn
            return _decorator
        def get(self, path: str):
            def _decorator(fn):
                return fn
            return _decorator
try:
    from pydantic import BaseModel
except Exception:  # pragma: no cover - fallback for test environment without pydantic
    class BaseModel:  # type: ignore
        pass
from pathlib import Path
import uuid

from .openrouter_client import embed
from .store import SimpleVectorStore


app = FastAPI(title="knowledge-ingest")


class IngestRequest(BaseModel):
    text: str
    id: str | None = None


STORE_PATH = Path("knowledge/data/index.json")
store = SimpleVectorStore(STORE_PATH)


@app.post("/ingest")
async def ingest(req: IngestRequest):
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    id = req.id or str(uuid.uuid4())
    emb = embed([text])[0]
    store.add(id, text, emb)
    store.save()
    return {"id": id, "status": "stored"}


if __name__ == "__main__":
    # simple CLI mode for manual runs
    import asyncio

    async def cli():
        print("Run as FastAPI app with: uvicorn knowledge.ingest_service:app --reload")

    asyncio.run(cli())
    asyncio.run(cli())
