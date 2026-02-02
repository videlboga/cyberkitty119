"""Reranking helpers for improving search results quality."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from transkribator_modules.config import logger, OPENROUTER_API_KEY

# Reranking settings
# Default to enabled (can be disabled via env) because LLM-based reranking
# significantly improves short-list quality in most cases.
ENABLE_RERANKING = os.getenv('ENABLE_RERANKING', 'true').lower() in {'1', 'true', 'yes'}
RERANK_MODEL = os.getenv('RERANK_MODEL', 'google/gemini-2.0-flash-exp:free')
# Reduce default top-k fetched for reranker to a modest number to save cost/latency
RERANK_TOP_K = int(os.getenv('RERANK_TOP_K', '8'))  # Fetch this many, then rerank
RERANK_TIMEOUT = float(os.getenv('RERANK_TIMEOUT', '10'))


async def rerank_results(query: str, results: list[dict[str, Any]], top_k: int = 5) -> list[dict[str, Any]]:
    """
    Rerank search results using LLM to improve relevance.
    
    Args:
        query: User's search query
        results: List of search results with 'chunk', 'note_id', 'score', 'note' keys
        top_k: How many top results to return after reranking
        
    Returns:
        Reranked list of results (top_k items)
    """
    if not ENABLE_RERANKING or not OPENROUTER_API_KEY:
        logger.debug('Reranking disabled or no API key')
        return results[:top_k]
    
    if len(results) <= 1:
        return results[:top_k]
    
    # Prepare candidates for reranking
    candidates = []
    for idx, result in enumerate(results[:RERANK_TOP_K]):
        note = result.get('note', {})
        chunk_text = result.get('chunk', '')
        summary = note.get('summary', '')
        
        # Combine summary + chunk for better context
        combined = f"{summary}\n\n{chunk_text}".strip() if summary else chunk_text
        
        candidates.append({
            'id': idx,
            'note_id': result.get('note_id'),
            'text': combined[:500],  # Limit text length for prompt
        })
    
    if not candidates:
        return results[:top_k]
    
    # Build prompt for LLM
    candidates_text = '\n'.join([
        f"[{c['id']}] Note #{c['note_id']}: {c['text']}"
        for c in candidates
    ])
    
    system_prompt = (
        "You are a search relevance expert. Given a user query and a list of text snippets, "
        "rank them by relevance to the query. Return ONLY a JSON array of IDs in order from most to least relevant. "
        "Format: [0, 3, 1, 2, ...]. No explanations, just the JSON array."
    )
    
    user_prompt = f"""Query: {query}

Snippets:
{candidates_text}

Return ranked IDs (JSON array):"""
    
    try:
        async with httpx.AsyncClient(timeout=RERANK_TIMEOUT) as client:
            headers = {
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'HTTP-Referer': os.getenv('OPENROUTER_REFERER', 'https://transkribator.local'),
                'X-Title': os.getenv('OPENROUTER_APP_NAME', 'CyberKitty'),
                'Content-Type': 'application/json',
            }
            
            payload = {
                'model': RERANK_MODEL,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'temperature': 0.1,
                'max_tokens': 200,
            }
            
            response = await client.post(
                'https://openrouter.ai/api/v1/chat/completions',
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
            
            # Parse JSON array from response
            # Clean potential markdown artifacts
            if content.startswith('```'):
                content = content.split('```')[1].strip()
                if content.startswith('json'):
                    content = content[4:].strip()
            
            ranked_ids = json.loads(content)
            
            if not isinstance(ranked_ids, list):
                logger.warning('Rerank returned non-list, falling back to original order')
                return results[:top_k]
            
            # Reorder results based on ranked IDs
            reranked = []
            used_indices = set()
            
            for rank_id in ranked_ids:
                if not isinstance(rank_id, int) or rank_id < 0 or rank_id >= len(results):
                    continue
                if rank_id in used_indices:
                    continue
                used_indices.add(rank_id)
                reranked.append(results[rank_id])
            
            # Add any missing results at the end
            for idx in range(len(results)):
                if idx not in used_indices and idx < RERANK_TOP_K:
                    reranked.append(results[idx])
            
            logger.info(
                'Reranked search results',
                extra={
                    'query': query[:50],
                    'original_top3': [r.get('note_id') for r in results[:3]],
                    'reranked_top3': [r.get('note_id') for r in reranked[:3]],
                }
            )
            
            return reranked[:top_k]
            
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            'Reranking failed, falling back to original order',
            extra={'error': str(exc), 'query': query[:50]}
        )
        return results[:top_k]
