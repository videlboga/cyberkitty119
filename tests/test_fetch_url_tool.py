"""Tests for the `fetch_url` agent tool (cyberkitty119 core_api).

These tests exercise the tool function directly with mocked httpx + DB services,
so no network or PostgreSQL is required. They mirror the DB fixture pattern used
in ``tests/test_beta_mode.py`` (in-memory SQLite with all tables created).
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
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
from transkribator_modules.db import database as db_module
from transkribator_modules.db.database import Base, NoteService, SessionLocal, UserService
from transkribator_modules.db.models import User


@pytest.fixture
def _inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_fetch_url.sqlite")
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
        user = User(telegram_id=42, username="tester", timezone="Europe/Moscow")
        s.add(user)
        s.commit()
        db_id = user.id
    agent_user = AgentUser(telegram_id=42, db_id=db_id, username="tester",
                           first_name="T", last_name="U")
    return AgentSession(agent_user)


def _fake_httpx_response(status_code: int, text: str):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


def _make_async_client(resp):
    """Return a fake httpx.AsyncClient-like context manager."""

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return resp

    return _Client


_HTML_FIXTURE = """
<html><head><title>Тестовая статья</title></head>
<body><article><p>Это основной текст статьи про заметки и агентов.</p>
<p>Второй абзац с дополнительной информацией.</p></article></body></html>
"""


def test_fetch_url_creates_note_and_returns_summary(_inmemory_db):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    # Avoid real index writes
    with patch.object(tools.IndexService, "add", new=MagicMock(return_value=None)):
        resp = _fake_httpx_response(200, _HTML_FIXTURE)
        client_cls = _make_async_client(resp)
        with patch("httpx.AsyncClient", client_cls):
            result = asyncio.run(tools._tool_fetch_url(agent_session, {"url": "https://example.com/a"}))

    assert result.status is None or result.status != "error"
    assert result.details is not None
    assert result.details["url"] == "https://example.com/a"
    note_id = result.details["note_id"]
    assert note_id is not None
    assert "Тестовая статья" in (result.details.get("title") or "")
    assert f"#{note_id}" in result.message

    # Note persisted with the expected fields
    with Session() as s:
        note = NoteService(s).get_note(note_id)
        assert note is not None
        assert note.source == "link"
        assert note.raw_link == "https://example.com/a"
        tags = tools._coerce_tags(note.tags)
        assert "url" in tags
        links = tools._coerce_links(note.links)
        assert links.get("source_url") == "https://example.com/a"


def test_fetch_url_http_error_returns_error_and_no_note(_inmemory_db):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    resp = _fake_httpx_response(404, "<html>not found</html>")
    client_cls = _make_async_client(resp)
    created = MagicMock()
    with patch("httpx.AsyncClient", client_cls), \
         patch.object(tools.NoteService, "create_note", created):
        result = asyncio.run(tools._tool_fetch_url(agent_session, {"url": "https://example.com/missing"}))

    assert result.status == "error"
    assert "404" in result.message
    created.assert_not_called()
    assert result.details is None


def test_fetch_url_save_as_note_false_skips_note_creation(_inmemory_db):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    with patch.object(tools.IndexService, "add", new=MagicMock(return_value=None)):
        resp = _fake_httpx_response(200, _HTML_FIXTURE)
        client_cls = _make_async_client(resp)
        created = MagicMock()
        with patch("httpx.AsyncClient", client_cls), \
             patch.object(tools.NoteService, "create_note", created):
            result = asyncio.run(tools._tool_fetch_url(
                agent_session, {"url": "https://example.com/x", "save_as_note": False}))

    created.assert_not_called()
    assert result.details is not None
    assert result.details["note_id"] is None
    assert "Тестовая статья" in result.message


def test_fetch_url_missing_user_returns_error(monkeypatch, _inmemory_db):
    Session = _inmemory_db
    agent_session = _make_session(Session)

    # Force UserService.get_user_by_id to return None
    with patch.object(tools.UserService, "get_user_by_id", return_value=None):
        result = asyncio.run(tools._tool_fetch_url(agent_session, {"url": "https://example.com/x"}))
    assert result.status == "error"
    assert "Пользователь" in result.message