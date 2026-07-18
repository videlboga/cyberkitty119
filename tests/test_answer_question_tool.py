"""Tests for the `answer_question` agent tool (cyberkitty119 core_api).

Mocks IndexService.search and call_agent_llm_with_retry so no PostgreSQL or
LLM API is required. Verifies the structured ToolResult (summary + highlights +
note_links) described in RESEARCH.md acceptance criteria for Task 2.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite://")
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core_api.domains.agent.core import tools
from core_api.domains.agent.core.agent_runtime import AgentSession, AgentUser
from transkribator_modules.db.database import Base, NoteService, SessionLocal
from transkribator_modules.db.models import User


@pytest.fixture
def _inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_answer_question.sqlite")
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
        user = User(telegram_id=7, username="tester", timezone="Europe/Moscow")
        s.add(user)
        s.commit()
        db_id = user.id
    return AgentSession(AgentUser(telegram_id=7, db_id=db_id, username="tester",
                                  first_name="T", last_name="U"))


def _fake_search_results():
    """Two notes returned by IndexService.search."""
    return [
        {
            "note_id": 101,
            "chunk_index": 0,
            "chunk": "Заметка про бюджет",
            "score": 0.9,
            "note": {
                "id": 101,
                "ts": None,
                "type_hint": "note",
                "summary": "Бюджет на квартал",
                "text": "Бюджет на квартал составил 100 тысяч.",
                "tags": [],
                "links": {},
            },
        },
        {
            "note_id": 102,
            "chunk_index": 0,
            "chunk": "Заметка про расходы",
            "score": 0.7,
            "note": {
                "id": 102,
                "ts": None,
                "type_hint": "note",
                "summary": "Расходы",
                "text": "Расходы превысили доходы в этом месяце.",
                "tags": [],
                "links": {},
            },
        },
    ]


def _fake_llm_payload():
    return json.dumps({
        "summary": "Бюджет и расходы связаны: расходы превысили доходы.",
        "highlights": [
            {"note_id": 101, "insight": "Бюджет на квартал — 100 тысяч"},
            {"note_id": 102, "insight": "Расходы превысили доходы"},
        ],
    })


def test_answer_question_returns_structured_result(_inmemory_db, monkeypatch):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    async def _fake_search(self, user_id, query, k=3):
        return _fake_search_results()

    async def _fake_llm(messages, timeout=20, retries=1):
        return _fake_llm_payload()

    monkeypatch.setattr(tools.IndexService, "search", _fake_search)
    monkeypatch.setattr(tools, "call_agent_llm_with_retry", _fake_llm)

    result = asyncio.run(tools._tool_answer_question(agent_session, {"query": "бюджет"}))

    assert result.status is None or result.status != "error"
    assert result.details is not None
    assert result.details["summary"] == "Бюджет и расходы связаны: расходы превысили доходы."
    highlights = result.details["highlights"]
    assert isinstance(highlights, list)
    assert {h["note_id"] for h in highlights} == {101, 102}
    assert all("insight" in h for h in highlights)
    note_links = result.details["note_links"]
    assert isinstance(note_links, list)
    assert {entry["note_id"] for entry in note_links} == {101, 102}
    # Message should contain the summary and note references
    assert "Бюджет и расходы" in result.message
    assert "#101" in result.message
    assert "#102" in result.message


def test_answer_question_no_results_returns_message(_inmemory_db, monkeypatch):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    async def _fake_search(self, user_id, query, k=3):
        return []

    monkeypatch.setattr(tools.IndexService, "search", _fake_search)
    monkeypatch.setattr(tools, "call_agent_llm_with_retry", AsyncMock())

    result = asyncio.run(tools._tool_answer_question(agent_session, {"query": "ничего"}))
    assert "не нашлось" in result.message.lower()


def test_answer_question_empty_query_blocked(_inmemory_db):
    Session = _inmemory_db
    agent_session = _make_session(Session)
    result = asyncio.run(tools._tool_answer_question(agent_session, {"query": "   "}))
    assert result.status == "blocked"


def test_answer_question_registered_in_tools():
    names = {t.name for t in tools.TOOLS}
    assert "answer_question" in names
    assert "fetch_url" in names
    # Schema must match the spec
    aq = next(t for t in tools.TOOLS if t.name == "answer_question")
    assert aq.args_schema == {"query": "str", "k": "int|optional"}
    fu = next(t for t in tools.TOOLS if t.name == "fetch_url")
    assert fu.args_schema == {"url": "str", "save_as_note": "bool|optional"}