"""Simple OpenRouter chat client for beta agent."""

from __future__ import annotations

import asyncio
from typing import Any, List

import aiohttp

from transkribator_modules.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    logger,
)

_OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class AgentLLMError(RuntimeError):
    """Raised when the agent LLM call fails."""


async def call_agent_llm(messages: List[dict[str, Any]], *, timeout: float = 25.0) -> str:
    """Call the configured OpenRouter chat model and return assistant content."""

    if not OPENROUTER_API_KEY:
        raise AgentLLMError("OPENROUTER_API_KEY is not configured")

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "top_p": 0.9,
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://transkribator.local",
        "X-Title": "CyberKitty Agent",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                _OPENROUTER_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response.raise_for_status()
                data = await response.json()
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent LLM call failed", extra={"error": str(exc)})
        raise AgentLLMError("Agent LLM call failed") from exc

    choices = data.get("choices") or []
    if not choices:
        raise AgentLLMError("Agent LLM returned no choices")

    content = choices[0].get("message", {}).get("content")
    if not content:
        raise AgentLLMError("Agent LLM returned empty content")
    return str(content)


async def call_agent_llm_with_retry(
    messages: List[dict[str, Any]],
    *,
    timeout: float = 25.0,
    retries: int = 1,
    delay: float = 2.0,
) -> str:
    """Call the LLM with a simple retry loop."""

    attempt = 0
    while True:
        try:
            return await call_agent_llm(messages, timeout=timeout)
        except AgentLLMError:
            if attempt >= retries:
                raise
            attempt += 1
            await asyncio.sleep(delay)

