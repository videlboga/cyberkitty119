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
                status = response.status
                
                if status == 429:
                    # Rate limit - специальная обработка
                    error_data = await response.text()
                    logger.warning(
                        "OpenRouter rate limit exceeded (429)",
                        extra={"response": error_data[:500]}
                    )
                    raise AgentLLMError("Rate limit exceeded, retry later")
                
                if status != 200:
                    error_data = await response.text()
                    logger.error(
                        f"OpenRouter API returned HTTP {status}",
                        extra={"status": status, "response": error_data[:500]}
                    )
                    raise AgentLLMError(f"HTTP {status}: {error_data[:200]}")
                
                data = await response.json()
    except AgentLLMError:
        # Пробрасываем наши ошибки дальше
        raise
    except asyncio.TimeoutError:
        logger.error("Agent LLM call timeout", extra={"timeout": timeout})
        raise AgentLLMError(f"Request timeout after {timeout}s")
    except aiohttp.ClientError as exc:
        logger.error("Agent LLM network error", extra={"error": str(exc), "type": type(exc).__name__})
        raise AgentLLMError(f"Network error: {type(exc).__name__}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Agent LLM unexpected error", extra={"error": str(exc), "type": type(exc).__name__})
        raise AgentLLMError(f"Unexpected error: {type(exc).__name__}") from exc

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
    retries: int = 3,  # Увеличено с 1 до 3
    delay: float = 5.0,  # Увеличено с 2 до 5 секунд
) -> str:
    """Call the LLM with exponential backoff retry logic."""
    attempt = 0
    while True:
        try:
            return await call_agent_llm(messages, timeout=timeout)
        except AgentLLMError as exc:
            if attempt >= retries:
                logger.error(
                    "Agent LLM exhausted all retries",
                    extra={"attempts": attempt + 1, "error": str(exc)}
                )
                raise
            
            attempt += 1
            # Exponential backoff: 5s, 10s, 20s
            backoff_delay = delay * (2 ** (attempt - 1))
            
            logger.warning(
                "Agent LLM retry",
                extra={
                    "attempt": attempt,
                    "max_retries": retries,
                    "backoff_delay": backoff_delay,
                    "error": str(exc)
                }
            )
            
            await asyncio.sleep(backoff_delay)
