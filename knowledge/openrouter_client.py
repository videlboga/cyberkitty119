"""Lightweight OpenRouter client with safe local fallback for embeddings/LLM.

If OPENROUTER_API_KEY is not set, the client returns deterministic mock
embeddings and canned generations so the services can be used offline.
"""
from __future__ import annotations

import os
import hashlib
import math
from typing import List

try:
    import httpx
except Exception:
    httpx = None

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = os.getenv("OPENROUTER_API_URL", "https://api.openrouter.ai")
OPENROUTER_EMBED_MODEL = os.getenv("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
OPENROUTER_LLM_MODEL = os.getenv("OPENROUTER_LLM_MODEL", "gpt-4o-mini")


def _deterministic_embedding(text: str, dim: int = 32) -> List[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vals = []
    for i in range(dim):
        byte = h[i % len(h)]
        vals.append((byte / 255.0) * 2.0 - 1.0)
    # normalize
    norm = math.sqrt(sum(x * x for x in vals)) or 1.0
    return [x / norm for x in vals]


def embed(texts: List[str]) -> List[List[float]]:
    """Return embeddings for a list of texts.

    If OPENROUTER_API_KEY is set, a real HTTP call is attempted (httpx required).
    Otherwise return deterministic mock embeddings.
    """
    if not OPENROUTER_API_KEY or not httpx:
        return [_deterministic_embedding(t) for t in texts]

    # Minimal call shape for OpenRouter-like embeddings endpoint; adapt if needed.
    url = f"{OPENROUTER_API_URL.rstrip('/')}/v1/embeddings"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {"model": OPENROUTER_EMBED_MODEL, "input": texts}
    resp = httpx.post(url, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    # expect data['data'] -> list of { 'embedding': [...] }
    out = []
    for item in data.get("data", []):
        out.append(item.get("embedding", []))
    return out


def generate(prompt: str, max_tokens: int = 256) -> str:
    """Generate a short response for a prompt.

    If key missing, return a canned but useful reply.
    """
    if not OPENROUTER_API_KEY or not httpx:
        # Very simple canned reply: echo with a hint.
        snippet = prompt.strip().replace("\n", " ")[:300]
        return f"[mock answer] based on: {snippet}"

    url = f"{OPENROUTER_API_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": OPENROUTER_LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=60.0)
    resp.raise_for_status()
    data = resp.json()
    # Try to extract a reasonable reply from common OpenRouter/OpenAI shapes
    choices = data.get("choices") or []
    if choices:
        msg = choices[0].get("message") or choices[0].get("text") or {}
        if isinstance(msg, dict):
            return msg.get("content", "")
        return str(msg)
    return ""


__all__ = ["embed", "generate"]
