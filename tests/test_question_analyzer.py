"""Tests for the is_question analyzer narrowing.

Verifies the system prompt now scopes 'question' to notes-content queries, and
that the analyzer plumbing correctly maps LLM JSON answers to True/False for the
representative cases from the task: 'привет'->False, 'что ты умеешь'->False,
'что я писал про X'->True, 'найди заметки про Y'->True.

The LLM itself is mocked (no real model call). The prompt-text assertions guard
the behavioural change; the plumbing assertions guard the parsing logic.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite://")
from core_api.domains.agent.core import tools


def test_question_analyzer_prompt_is_narrowed():
    """The system prompt must scope 'question' to notes-content queries, not any question."""
    prompt = tools._QUESTION_ANALYZER_SYSTEM_PROMPT
    # Must NOT retain the old over-broad instruction.
    assert "даже если нет вопросительного знака" not in prompt
    # Must explicitly mention notes-content phrasing examples.
    assert "заметк" in prompt.lower()
    # Must explicitly exclude casual dialogue.
    assert "привет" in prompt.lower()
    assert "что ты умеешь" in prompt.lower() or "умеешь" in prompt.lower()


@pytest.mark.parametrize(
    "user_text,llm_answer,expected",
    [
        ("привет", '{"is_question": false}', False),
        ("что ты умеешь", '{"is_question": false}', False),
        ("как дела", '{"is_question": false}', False),
        ("расскажи о себе", '{"is_question": false}', False),
        ("что я писал про X", '{"is_question": true}', True),
        ("найди заметки про Y", '{"is_question": true}', True),
        ("о чём у меня заметки про бюджет", '{"is_question": true}', True),
    ],
)
def test_analyzer_parses_llm_decisions(monkeypatch, user_text, llm_answer, expected):
    # Use a fresh analyzer instance so cached decisions from other tests don't leak.
    analyzer = tools._LLMQuestionAnalyzer()

    async def _fake_llm(messages, timeout=8, retries=1):
        return llm_answer

    monkeypatch.setattr(tools, "call_agent_llm_with_retry", _fake_llm)
    decision = asyncio.run(analyzer.is_question(user_text))
    assert decision is expected, f"{user_text!r}: expected {expected}, got {decision}"


def test_analyzer_returns_false_on_empty(monkeypatch):
    analyzer = tools._LLMQuestionAnalyzer()
    monkeypatch.setattr(tools, "call_agent_llm_with_retry", AsyncMock())
    assert asyncio.run(analyzer.is_question("")) is False
    assert asyncio.run(analyzer.is_question("   ")) is False


def test_analyzer_returns_false_on_llm_failure(monkeypatch):
    from core_api.domains.agent.core.llm import AgentLLMError
    analyzer = tools._LLMQuestionAnalyzer()

    async def _failing_llm(messages, timeout=8, retries=1):
        raise AgentLLMError("boom")

    monkeypatch.setattr(tools, "call_agent_llm_with_retry", _failing_llm)
    assert asyncio.run(analyzer.is_question("найди заметки")) is False