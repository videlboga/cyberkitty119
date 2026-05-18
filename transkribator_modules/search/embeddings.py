"""Embedding helpers with fallback hashing for semantic search."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Iterable, List, Dict, Tuple

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

# Embedding cache: key = sha256(text), value = (embedding, timestamp)
_EMBEDDING_CACHE: Dict[str, Tuple[List[float], float]] = {}
_CACHE_MAX_SIZE = int(os.getenv('EMBEDDING_CACHE_SIZE', '1000'))
_CACHE_TTL_SECONDS = int(os.getenv('EMBEDDING_CACHE_TTL', '3600'))  # 1 hour
_CACHE_HITS = 0
_CACHE_MISSES = 0


def get_cache_stats() -> dict:
    """Return cache statistics."""
    total_requests = _CACHE_HITS + _CACHE_MISSES
    hit_rate = (_CACHE_HITS / total_requests * 100) if total_requests > 0 else 0
    return {
        'size': len(_EMBEDDING_CACHE),
        'max_size': _CACHE_MAX_SIZE,
        'hits': _CACHE_HITS,
        'misses': _CACHE_MISSES,
        'hit_rate': f'{hit_rate:.1f}%',
    }


def _get_cache_key(text: str) -> str:
    """Generate cache key from text."""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _get_from_cache(text: str) -> List[float] | None:
    """Get embedding from cache if exists and not expired."""
    global _CACHE_HITS, _CACHE_MISSES
    
    key = _get_cache_key(text)
    if key not in _EMBEDDING_CACHE:
        _CACHE_MISSES += 1
        return None
    
    embedding, timestamp = _EMBEDDING_CACHE[key]
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        # Expired, remove from cache
        del _EMBEDDING_CACHE[key]
        _CACHE_MISSES += 1
        return None
    
    _CACHE_HITS += 1
    return embedding


def _put_to_cache(text: str, embedding: List[float]) -> None:
    """Put embedding to cache with current timestamp."""
    # Simple eviction: remove oldest entries if cache is full
    if len(_EMBEDDING_CACHE) >= _CACHE_MAX_SIZE:
        oldest_key = min(_EMBEDDING_CACHE.items(), key=lambda x: x[1][1])[0]
        del _EMBEDDING_CACHE[oldest_key]
    
    key = _get_cache_key(text)
    _EMBEDDING_CACHE[key] = (embedding, time.time())


def _clean_expired_cache() -> None:
    """Remove expired entries from cache."""
    now = time.time()
    expired_keys = [
        key for key, (_, timestamp) in _EMBEDDING_CACHE.items()
        if now - timestamp > _CACHE_TTL_SECONDS
    ]
    for key in expired_keys:
        del _EMBEDDING_CACHE[key]



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


async def _call_openrouter_embeddings(texts: List[str]) -> List[List[float]]:
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
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT) as client:
            response = await client.post('https://openrouter.ai/api/v1/embeddings', json=payload, headers=headers)
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


async def _call_deepinfra_embeddings(texts: List[str]) -> List[List[float]]:
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
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT) as client:
            response = await client.post(DEEPINFRA_EMBEDDING_URL, json=payload, headers=headers)
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


async def embed_texts_async(texts: List[str]) -> List[List[float]]:
    """Асинхронная версия embed_texts для использования в async контексте с кешированием."""
    if not texts:
        return []

    if DISABLE_REMOTE_EMBEDDINGS:
        return _hash_embeddings(texts)

    # Периодически чистим устаревшие записи
    if len(_EMBEDDING_CACHE) > 0 and len(_EMBEDDING_CACHE) % 100 == 0:
        _clean_expired_cache()

    # Проверяем кеш для каждого текста
    cached_results: List[List[float] | None] = []
    texts_to_fetch: List[str] = []
    fetch_indices: List[int] = []
    
    for idx, text in enumerate(texts):
        cached = _get_from_cache(text)
        if cached is not None:
            cached_results.append(cached)
            logger.debug('Cache hit for text %s', idx)
        else:
            cached_results.append(None)
            texts_to_fetch.append(text)
            fetch_indices.append(idx)

    # Если все в кеше, возвращаем сразу
    if not texts_to_fetch:
        logger.debug('All %s embeddings from cache', len(texts))
        return cached_results  # type: ignore

    # Запрашиваем только некешированные тексты
    logger.debug('Fetching %s/%s embeddings from API', len(texts_to_fetch), len(texts))

    vectors: List[List[float]] = []
    errors: List[str] = []

    async def _fetch_with_provider(provider: str, payload: List[str]) -> List[List[float]]:
        if provider == 'openrouter':
            return await _call_openrouter_embeddings(payload)
        if provider == 'deepinfra':
            return await _call_deepinfra_embeddings(payload)
        logger.warning('Unknown embedding provider, using hash fallback', extra={'provider': provider})
        return _hash_embeddings(payload)

    async def _attempt(primary: str, fallback: str, payload: List[str]) -> List[List[float]]:
        first = await _fetch_with_provider(primary, payload)
        if len(first) == len(payload):
            return first
        errors.append(primary)
        logger.warning(
            'Primary embedding provider returned %s/%s vectors, trying fallback',
            len(first),
            len(payload),
            extra={'primary': primary, 'fallback': fallback},
        )
        second = await _fetch_with_provider(fallback, payload)
        if len(second) == len(payload):
            return second
        errors.append(fallback)
        return first  # partial result; rest hashed later

    primary = EMBEDDING_PROVIDER
    secondary = 'openrouter' if primary == 'deepinfra' else 'deepinfra'
    vectors = await _attempt(primary, secondary, texts_to_fetch)

    # Кешируем полученные эмбеддинги
    for text, vector in zip(texts_to_fetch, vectors):
        _put_to_cache(text, vector)

    # Fallback для недостающих векторов
    if len(vectors) != len(texts_to_fetch):
        logger.debug(
            'Falling back to hash embeddings for %s items',
            len(texts_to_fetch) - len(vectors),
        )
        vectors.extend(_hash_embeddings(texts_to_fetch[len(vectors):]))

    # Собираем финальный результат: кеш + новые векторы
    result: List[List[float]] = []
    fetch_idx = 0
    for cached in cached_results:
        if cached is not None:
            result.append(cached)
        else:
            result.append(vectors[fetch_idx])
            fetch_idx += 1
    
    return result


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Синхронная обёртка для обратной совместимости. Лучше использовать embed_texts_async()."""
    if not texts:
        return []

    if DISABLE_REMOTE_EMBEDDINGS:
        return _hash_embeddings(texts)

    # Для синхронных вызовов используем fallback на хэш-эмбеддинги
    logger.warning('Using sync embed_texts() - consider migrating to embed_texts_async()')
    return _hash_embeddings(texts)


async def embed_text_async(text: str) -> List[float]:
    """Асинхронная версия для одного текста."""
    result = await embed_texts_async([text]) if text is not None else [_hash_embedding('')]
    return result[0]
