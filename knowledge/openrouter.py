"""Light wrapper for OpenRouter (OpenAI-compatible) with safe mock fallback.

This module provides two helpers: embed_texts and chat_completion. If
OPENROUTER_API_KEY is not set, functions run in mock mode (deterministic
behaviour) so the skeleton services are runnable without secrets.
"""
from __future__ import annotations

import os
import time
import logging
from typing import List, Dict, Any

import requests

LOG = logging.getLogger("knowledge.openrouter")

OPENROUTER_URL = os.environ.get("OPENROUTER_API_URL", "https://api.openrouter.ai")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
EMBED_MODEL = os.environ.get("OPENROUTER_EMBED_MODEL", "text-embedding-3-small")
LLM_MODEL = os.environ.get("OPENROUTER_LLM_MODEL", "gpt-4o-mini")

USE_MOCK = not bool(OPENROUTER_KEY)

_SESSION = requests.Session()
if OPENROUTER_KEY:
    _SESSION.headers.update({"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json"})


def _post_json(path: str, payload: dict, timeout: int = 60) -> dict:
    if USE_MOCK:
        LOG.info("openrouter: mock _post_json called path=%s", path)
        # Very small deterministic mock response
        if path.endswith("/embeddings"):
            return {"data": [{"embedding": [0.001 * (i + 1) for _ in range(8)], "index": i} for i in range(len(payload.get("input", [])))]}
        if path.endswith("/chat/completions"):
            return {"choices": [{"message": {"role": "assistant", "content": "MOCK: generated text"}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return {}

    url = OPENROUTER_URL.rstrip("/") + path
    backoff = 1.0
    for attempt in range(6):
        try:
            r = _SESSION.post(url, json=payload, timeout=timeout)
            if r.status_code == 429:
                LOG.warning("rate limited, sleeping %.1fs", backoff)
                time.sleep(backoff)
                backoff *= 2
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            LOG.warning("openrouter request failed attempt %d: %s", attempt + 1, e)
            if attempt == 5:
                raise
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("unreachable")


def embed_texts(texts: List[str], model: str | None = None, batch_size: int = 64) -> List[List[float]]:
    """Return embeddings for a list of texts.

    In mock mode returns small deterministic vectors. Otherwise calls
    OpenRouter /v1/embeddings (OpenAI compatible).
    """
    model = model or EMBED_MODEL
    embeddings: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        payload = {"model": model, "input": batch}
        res = _post_json("/v1/embeddings", payload, timeout=120)
        data = res.get("data", [])
        for item in data:
            embeddings.append(item.get("embedding", []))
    return embeddings


def chat_completion(messages: List[Dict[str, str]], model: str | None = None, max_tokens: int = 512, temperature: float = 0.0) -> Dict[str, Any]:
    """Call chat/completions and return raw response dict.

    In mock mode returns a simple canned reply.
    """
    model = model or LLM_MODEL
    if USE_MOCK:
        LOG.info("openrouter: mock chat_completion called model=%s", model)
        return {"choices": [{"message": {"role": "assistant", "content": "MOCK: This is a generated document based on provided context."}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    return _post_json("/v1/chat/completions", payload, timeout=120)
