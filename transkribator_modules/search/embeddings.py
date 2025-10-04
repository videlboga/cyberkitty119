"""Embedding helpers with fallback hashing for semantic search."""

from __future__ import annotations

import hashlib
import os
from typing import Iterable, List

import httpx
import numpy as np

from transkribator_modules.config import (
    logger,
    OPENROUTER_API_KEY,
    DEEPINFRA_API_KEY,
)

EMBEDDING_DIM = 1536
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'openai/text-embedding-3-small')
EMBEDDING_PROVIDER = os.getenv('EMBEDDING_PROVIDER', 'openrouter').lower()
DEEPINFRA_EMBEDDING_URL = os.getenv(
    'DEEPINFRA_EMBEDDING_URL',
    'https://api.deepinfra.com/v1/openai/embeddings',
)
EMBEDDING_TIMEOUT = float(os.getenv('EMBEDDING_TIMEOUT', '15'))
DISABLE_REMOTE_EMBEDDINGS = os.getenv('DISABLE_REMOTE_EMBEDDINGS', 'false').lower() in {'1', 'true', 'yes'}


def _hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    digest = hashlib.sha256((text or '').encode('utf-8')).digest()
    repeats = ((dim * 4) // len(digest)) + 1
    data = (digest * repeats)[: dim * 4]
    arr = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
    arr = arr[:dim]
    norm = np.linalg.norm(arr)
    if norm:
        arr /= norm
    return arr.tolist()


def _hash_embeddings(texts: Iterable[str], dim: int = EMBEDDING_DIM) -> List[List[float]]:
    return [_hash_embedding(text, dim=dim) for text in texts]


def _normalize_embedding(values: Iterable[float], dim: int = EMBEDDING_DIM) -> List[float]:
    arr = np.asarray(list(values), dtype=np.float32)
    if arr.size == 0:
        arr = np.zeros(dim, dtype=np.float32)
    if arr.size > dim:
        arr = arr[:dim]
    elif arr.size < dim:
        pad = np.zeros(dim - arr.size, dtype=np.float32)
        arr = np.concatenate([arr, pad])
    norm = np.linalg.norm(arr)
    if norm:
        arr /= norm
    return arr.tolist()


def _call_openrouter_embeddings(texts: List[str]) -> List[List[float]]:
    if not OPENROUTER_API_KEY or not texts:
        return []

    headers = {
        'Authorization': f'Bearer {OPENROUTER_API_KEY}',
        'HTTP-Referer': os.getenv('OPENROUTER_REFERER', 'https://transkribator.local'),
        'X-Title': os.getenv('OPENROUTER_APP_NAME', 'CyberKitty'),
    }
    payload = {
        'model': EMBEDDING_MODEL,
        'input': texts,
    }
    try:
        with httpx.Client(timeout=EMBEDDING_TIMEOUT) as client:
            response = client.post('https://openrouter.ai/api/v1/embeddings', json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning('Embedding request failed', extra={'error': str(exc), 'provider': 'openrouter'})
        return []

    embeddings: List[List[float]] = []
    for idx, item in enumerate(data.get('data', [])):
        vector = item.get('embedding')
        if not isinstance(vector, list):
            logger.debug('Missing embedding vector for item %s', idx)
            embeddings.append(_hash_embedding(texts[idx]))
            continue
        embeddings.append(_normalize_embedding(vector, dim=EMBEDDING_DIM))
    return embeddings


def _call_deepinfra_embeddings(texts: List[str]) -> List[List[float]]:
    if not DEEPINFRA_API_KEY or not texts:
        return []

    headers = {
        'Authorization': f'Bearer {DEEPINFRA_API_KEY}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': EMBEDDING_MODEL,
        'input': texts,
        'encoding_format': 'float',
    }
    try:
        with httpx.Client(timeout=EMBEDDING_TIMEOUT) as client:
            response = client.post(DEEPINFRA_EMBEDDING_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning('Embedding request failed', extra={'error': str(exc), 'provider': 'deepinfra'})
        return []

    embeddings: List[List[float]] = []
    for idx, item in enumerate(data.get('data', [])):
        vector = item.get('embedding')
        if not isinstance(vector, list):
            logger.debug('Missing embedding vector for item %s', idx)
            embeddings.append(_hash_embedding(texts[idx]))
            continue
        embeddings.append(_normalize_embedding(vector, dim=EMBEDDING_DIM))
    return embeddings


def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    if DISABLE_REMOTE_EMBEDDINGS:
        return _hash_embeddings(texts)

    if EMBEDDING_PROVIDER == 'openrouter':
        vectors = _call_openrouter_embeddings(texts)
    elif EMBEDDING_PROVIDER == 'deepinfra':
        vectors = _call_deepinfra_embeddings(texts)
    else:
        logger.warning('Unknown embedding provider, falling back to hashes', extra={'provider': EMBEDDING_PROVIDER})
        return _hash_embeddings(texts)

    if len(vectors) != len(texts):
        logger.debug(
            'Falling back to hash embeddings for %s items',
            len(texts) - len(vectors),
        )
        vectors.extend(_hash_embeddings(texts[len(vectors):]))
    return vectors


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0] if text is not None else _hash_embedding('')
