"""Tests for natural-dialog routing: casual replies must NOT trigger RAG/search_notes.

Covers the three sources of over-eager RAG described in the task:
  1. system prompt pushes answer_question for any question without active note,
  2. runtime fallback forces search_notes whenever question_like,
  3. is_question analyzer treats any question as a notes query.

Mocks the LLM and the question analyzer; no PostgreSQL or real LLM needed.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite://")
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core_api.domains.agent.core import tools
from core_api.domains.agent.core.agent_runtime import AgentSession, AgentUser
from core_api.domains.agent.persistence import AgentPersistenceGateway
from transkribator_modules.db.database import Base
from transkribator_modules.db.models import User


@pytest.fixture
def _inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_dialog_tests.sqlite")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    assert inspect(engine).has_table("users")
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr("transkribator_modules.db.database.SessionLocal", Session)
    monkeypatch.setattr("core_api.domains.agent.core.tools.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.search.index.SessionLocal", Session, raising=False)
    yield Session
    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _make_session(Session) -> AgentSession:
    with Session() as s:
        user = User(telegram_id=11, username="dialog", timezone="Europe/Moscow")
        s.add(user)
        s.commit()
        db_id = user.id
    gateway = AgentPersistenceGateway(session_factory=Session)
    return AgentSession(
        AgentUser(telegram_id=11, db_id=db_id, username="dialog",
                 first_name="D", last_name="T"),
        persistence_gateway=gateway,
    )


def _llm_say(response_text: str, actions=None):
    """Build a fake LLM returning a plain conversational response, no tools."""
    return json.dumps({
        "response": response_text,
        "actions": actions or [],
        "suggestions": [],
    }, ensure_ascii=False)


def test_casual_greeting_does_not_trigger_search(_inmemory_db, monkeypatch):
    """LLM answers 'привет' in response; runtime must not force a search."""
    Session = _inmemory_db
    agent_session = _make_session(Session)

    monkeypatch.setattr(tools, "_looks_like_question", AsyncMock(return_value=False))
    import core_api.domains.agent.core.agent_runtime as runtime_mod
    monkeypatch.setattr(runtime_mod, "_looks_like_question", AsyncMock(return_value=False))

    async def _fake_llm(messages, timeout=20, retries=1):
        return _llm_say("Привет! Я Киберкотёнок, помогаю с заметками.")

    monkeypatch.setattr(runtime_mod, "call_agent_llm_with_retry", _fake_llm)

    invoked_tools: list[str] = []
    orig_invoke = agent_session._invoke_tool

    async def _spy_invoke(tool_name, args, comment=None):
        invoked_tools.append(tool_name)
        return await orig_invoke(tool_name, args, comment)

    monkeypatch.setattr(agent_session, "_invoke_tool", _spy_invoke)

    result = asyncio.run(agent_session.handle_user_message("привет"))

    assert "Привет" in result.text
    assert not any(t in {"search_notes", "answer_question"} for t in invoked_tools), (
        f"casual greeting must not trigger notes tools, got: {invoked_tools}"
    )


def test_casual_greeting_still_safe_when_analyzer_misfires(_inmemory_db, monkeypatch):
    """Even if is_question wrongly returns True, fallback must respect LLM response."""
    Session = _inmemory_db
    agent_session = _make_session(Session)

    import core_api.domains.agent.core.agent_runtime as runtime_mod
    monkeypatch.setattr(runtime_mod, "_looks_like_question", AsyncMock(return_value=True))
    monkeypatch.setattr(tools, "_looks_like_question", AsyncMock(return_value=True))

    async def _fake_llm(messages, timeout=20, retries=1):
        return _llm_say("Привет! Чем могу помочь с заметками?")

    monkeypatch.setattr(runtime_mod, "call_agent_llm_with_retry", _fake_llm)

    invoked_tools: list[str] = []
    orig_invoke = agent_session._invoke_tool

    async def _spy_invoke(tool_name, args, comment=None):
        invoked_tools.append(tool_name)
        return await orig_invoke(tool_name, args, comment)

    monkeypatch.setattr(agent_session, "_invoke_tool", _spy_invoke)

    result = asyncio.run(agent_session.handle_user_message("привет"))

    assert "Привет" in result.text
    assert not any(t in {"search_notes", "answer_question"} for t in invoked_tools), (
        f"fallback must trust non-empty LLM response, got: {invoked_tools}"
    )


def test_notes_query_triggers_search_when_llm_requests_it(_inmemory_db, monkeypatch):
    """Sanity: an explicit notes query with a search action still works."""
    Session = _inmemory_db
    agent_session = _make_session(Session)

    import core_api.domains.agent.core.agent_runtime as runtime_mod
    monkeypatch.setattr(runtime_mod, "_looks_like_question", AsyncMock(return_value=True))
    monkeypatch.setattr(tools, "_looks_like_question", AsyncMock(return_value=True))

    async def _fake_llm(messages, timeout=20, retries=1):
        return _llm_say(
            "Ищу заметки про бюджет.",
            actions=[{"tool": "search_notes", "args": {"query": "бюджет", "k": 3}, "comment": "поиск"}],
        )

    monkeypatch.setattr(runtime_mod, "call_agent_llm_with_retry", _fake_llm)

    async def _fake_search(self, user_id, query, k=3):
        return [
            {
                "note_id": 201,
                "chunk_index": 0,
                "chunk": "Бюджет",
                "score": 0.9,
                "note": {
                    "id": 201, "ts": None, "type_hint": "note",
                    "summary": "Бюджет", "text": "Бюджет 100", "tags": [], "links": {},
                },
            },
        ]

    monkeypatch.setattr(tools.IndexService, "search", _fake_search)

    invoked_tools: list[str] = []
    orig_invoke = agent_session._invoke_tool

    async def _spy_invoke(tool_name, args, comment=None):
        invoked_tools.append(tool_name)
        return await orig_invoke(tool_name, args, comment)

    monkeypatch.setattr(agent_session, "_invoke_tool", _spy_invoke)

    result = asyncio.run(agent_session.handle_user_message("что я писал про бюджет"))
    assert "Бюджет" in result.text or "бюджет" in result.text.lower()
    assert "search_notes" in invoked_tools