"""Query service: accept question, retrieve top-k contexts and optionally call LLM."""
from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
except Exception:  # pragma: no cover - allow tests without fastapi
    class HTTPException(Exception):
        def __init__(self, status_code: int = 500, detail: str | None = None):
            super().__init__(detail or "HTTPException")
    class FastAPI:
        def __init__(self, *a, **k):
            pass
        def post(self, path: str):
            def _decorator(fn):
                return fn
            return _decorator

try:
    from pydantic import BaseModel
except Exception:
    class BaseModel:  # simple fallback for tests
        pass

from pathlib import Path
from typing import List

from .openrouter_client import embed, generate
from .store import SimpleVectorStore


app = FastAPI(title="knowledge-query")


class QueryRequest(BaseModel):
    question: str
    top_k: int = 3
    use_llm: bool = True


STORE_PATH = Path("knowledge/data/index.json")
store = SimpleVectorStore(STORE_PATH)


@app.post("/query")
async def query(req: QueryRequest):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="empty question")
    q_emb = embed([q])[0]
    results = store.query(q_emb, top_k=req.top_k)
    contexts = [r[1]["text"] for r in results]
    answer = None
    if req.use_llm:
        prompt = "Use the following context to answer the question:\n\n" + "\n---\n".join(contexts) + "\n\nQuestion: " + q
        answer = generate(prompt)
    return {"answer": answer, "contexts": contexts, "scores": [r[0] for r in results]}
    return {"answer": answer, "contexts": contexts, "scores": [r[0] for r in results]}
