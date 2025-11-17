"""Tests for the simplified beta agent runtime."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["DATABASE_URL"] = "sqlite://"
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from transkribator_modules.beta.agent_runtime import (
    AGENT_MANAGER,
    AgentSession,
    AgentUser,
    _build_fallback_message,
    _parse_agent_json,
)
from transkribator_modules.beta.handlers.entrypoint import (
    _NoteSnapshot,
    _merge_artifact_hint,
    process_text,
)
from transkribator_modules.beta.tools import IndexService
from transkribator_modules.db.database import Base, NoteService, SessionLocal
from transkribator_modules.db.models import NoteStatus, User


@pytest.fixture(autouse=True)
def _inmemory_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix="_beta_tests.sqlite")
    os.close(fd)

    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert inspector.has_table("users"), "users table must exist for tests"
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr("transkribator_modules.db.database.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.agent_runtime.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.tools.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.command_processor.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.handlers.entrypoint.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.search.index.SessionLocal", Session)

    from transkribator_modules.db import database as db_module

    globals()["SessionLocal"] = db_module.SessionLocal
    yield

    Base.metadata.drop_all(engine)
    engine.dispose()
    try:
        os.unlink(path)
    except FileNotFoundError:  # pragma: no cover - cleanup guard
        pass


@pytest.fixture
def user_session(monkeypatch):
    with SessionLocal() as session:
        user = User(telegram_id=123, username="tester", timezone="Europe/Moscow")
        session.add(user)
        session.commit()
        user_id = user.id

    agent_user = AgentUser(
        telegram_id=123,
        db_id=user_id,
        username="tester",
        first_name="Test",
        last_name="User",
    )
    agent_session = AgentSession(agent_user)

    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)
    monkeypatch.setattr(IndexService, "search", lambda *args, **kwargs: [])

    return agent_session


def test_agent_session_executes_save_note_tool(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(
            user=user,
            text="Запланировать встречу завтра",
            status=NoteStatus.INGESTED.value,
        )

    user_session.set_active_note(note)

    response_payload = {
        "response": "Заметку оформила.",
        "actions": [
            {
                "tool": "save_note",
                "args": {"summary": "Договорились о встрече"},
                "comment": "Сохраняю заметку",
            },
            {
                "tool": "suggest_calendar_event",
                "args": {"when": "завтра 12:00", "title": "Созвон с командой"},
                "comment": "Предлагаю добавить встречу",
            },
        ],
        "suggestions": ["Поставить задачу подготовить материалы"],
    }

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(response_payload)

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(
        user_session.handle_ingest(
            {
                "note_id": note.id,
                "text": "Запланировать встречу завтра",
                "summary": None,
                "source": "message",
                "created_at": "2024-10-02T10:00:00",
                "created": True,
            }
        )
    )

    assert "Заметку сохранил" in result.text
    assert "Предлагаю добавить встречу" not in result.text
    assert result.tool_results
    assert result.suggestions == []

    with SessionLocal() as session:
        stored_note = NoteService(session).get_note(note.id)
        assert stored_note.status == NoteStatus.APPROVED.value
        assert stored_note.summary == "Договорились о встрече"


def test_agent_session_user_message_no_actions(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_call(*_args, **_kwargs):
        return json.dumps({"response": "Сделаем список дел", "actions": [], "suggestions": []})

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_user_message("Разбей на задачи"))
    assert result.text.startswith("Сделаем список дел")
    assert not result.tool_results


def test_agent_session_handles_invalid_json(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_call(*_args, **_kwargs):
        return "not a json"

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_user_message("Просто сохрани"))
    assert result.text.startswith("Не уверен, что ответить по заметке #")
    assert "готово" not in result.text.lower()


def test_agent_session_ingest_fallback(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_call(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    payload = {
        "note_id": note.id,
        "text": "Протокол встречи от 12:00",
        "summary": None,
        "source": "message",
        "created_at": "2024-10-02T10:00:00",
        "created": True,
    }

    result = asyncio.run(user_session.handle_ingest(payload))
    assert f"Создана новая заметка #{note.id}" in result.text
    assert "протокол встречи" in result.text.lower()
    assert "готово" not in result.text.lower()


def test_agent_session_search_notes_tool(monkeypatch, user_session, caplog):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    def _fake_search(_self, _user_id, _query, *, k=3):
        return [
            {"note": {"id": note.id, "summary": "Встреча", "text": "Договорились"}},
            {"note": {"id": note.id + 1, "summary": None, "text": "Вторая заметка"}},
        ][:k]

    monkeypatch.setattr(IndexService, "search", _fake_search)

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Вот что нашёл.",
                "actions": [
                    {
                        "tool": "search_notes",
                        "args": {"query": "встреча", "k": 2},
                        "comment": "Ищу по заметкам",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    caplog.set_level("ERROR")

    result = asyncio.run(user_session.handle_user_message("найди заметки про встречу"))
    if result.tool_results and result.tool_results[0].status == "error":
        debug = [(rec.__dict__.get("tool"), rec.__dict__.get("error")) for rec in caplog.records]
        raise AssertionError(f"search tool failed: {debug}")

    assert "Нашёл заметки" in result.text
    assert "#" in result.text
    assert any("Встреча" in line for line in result.text.splitlines())


def test_agent_session_search_notes_answers_question(monkeypatch, user_session, caplog):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(
            user=user,
            text="Юзербот завершён и готов к запуску.",
            summary="Юзербот готов",
            status=NoteStatus.PROCESSED.value,
        )

    def _fake_search(_self, _user_id, _query, *, k=3):
        return [
            {"note": {"id": note.id, "summary": note.summary, "text": note.text}},
        ][:k]

    async def _fake_agent_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Смотрю по заметкам.",
                "actions": [
                    {
                        "tool": "search_notes",
                        "args": {"query": "Юзербот готов?", "k": 3},
                        "comment": "Ищу ответ в заметках",
                    }
                ],
                "suggestions": [],
            }
        )

    async def _fake_answer(messages, **_kwargs):  # pragma: no cover - deterministic stub
        return "Юзербот уже готов, можно использовать."

    monkeypatch.setattr(IndexService, "search", _fake_search)
    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_agent_call,
    )
    monkeypatch.setattr(
        "transkribator_modules.beta.tools.call_agent_llm_with_retry",
        _fake_answer,
    )

    caplog.set_level("ERROR")

    result = asyncio.run(user_session.handle_user_message("Юзербот готов?"))

    if result.tool_results and result.tool_results[0].status == "error":
        debug = [(rec.__dict__.get("tool"), rec.__dict__.get("error")) for rec in caplog.records]
        raise AssertionError(f"search tool failed: {debug}")

    assert "Юзербот уже готов" in result.text
    assert f"#{note.id}" in result.text


def test_agent_session_ignores_unknown_tool(monkeypatch, user_session):
    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Ответ без действий.",
                "actions": [
                    {
                        "tool": "unknown_tool",
                        "args": {"value": 1},
                        "comment": "Что-то делаю",
                    }
                ],
                "suggestions": ["Попробуй уточнить запрос"],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_user_message("что-нибудь сделай"))
    assert result.text.startswith("Ответ без действий.")
    assert not result.tool_results
    assert result.suggestions == []


def test_parse_agent_json_variants():
    data = {
        "response": "ok",
        "actions": [],
    }
    wrapped = "```json\n" + json.dumps(data) + "```"
    assert _parse_agent_json(wrapped) == data

    broken = "Response: {\"response\": \"ok\"}"
    assert _parse_agent_json(broken) == {"response": "ok"}


def test_merge_artifact_hint_adds_drive_and_file():
    snapshot = _NoteSnapshot(
        note=SimpleNamespace(id=42),
        created=True,
        drive_link="https://drive.google.com/file",
        local_file="/tmp/fake.md",
    )
    text = _merge_artifact_hint("", snapshot)
    assert "https://drive.google.com/file" in text
    assert "📎" in text


def test_fallback_mentions_local_artifact():
    context = {
        "mode": "ingest",
        "note_id": 77,
        "created": True,
        "summary": "Конспект",
        "text": "Конспект",
        "links": {},
        "local_artifact": True,
    }
    text = _build_fallback_message(context)
    assert "Файл заметки" in text


class _DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies: list[tuple[str, dict]] = []
        self.documents: list[tuple[str, str]] = []
        self.edits: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append((text, kwargs))
        return _DummyEditableMessage(self.edits)

    async def reply_document(self, document, filename: str, caption: str, **kwargs):  # pragma: no cover - helper
        self.documents.append((filename, caption))


class _DummyEditableMessage:
    def __init__(self, edits_store: list[tuple[str, dict]]):
        self._store = edits_store

    async def edit_text(self, text: str, **kwargs):
        self._store.append((text, kwargs))


class _DummyBot:
    def __init__(self):
        self.sent_messages = []
        self.sent_docs = []
        self.message_edits = []

    async def send_message(self, chat_id: int, text: str, **kwargs):  # pragma: no cover - helper
        self.sent_messages.append((chat_id, text, kwargs))
        return _DummyEditableMessage(self.message_edits)

    async def send_document(self, chat_id: int, document, filename: str, caption: str, **kwargs):  # pragma: no cover - helper
        self.sent_docs.append((chat_id, filename, caption))


class _DummyUpdate:
    def __init__(self, message: _DummyMessage, user):
        self.message = message
        self.effective_user = user
        self.callback_query = None


class _DummyContext(SimpleNamespace):
    pass


def test_process_text_creates_note_and_saves_summary(monkeypatch):
    AGENT_MANAGER._sessions.clear()

    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "transkribator_modules.beta.handlers.entrypoint._ensure_note_artifact",
        lambda *args, **kwargs: (None, None),
    )

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Заметку оформила.",
                "actions": [
                    {
                        "tool": "save_note",
                        "args": {"summary": "Краткий итог"},
                        "comment": "Сохраняю заметку",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    message = _DummyMessage("Запиши кратко: созвон с клиентом завтра.")
    telegram_user = SimpleNamespace(id=555, username="tester", first_name="Test", last_name="User")
    update = _DummyUpdate(message, telegram_user)
    context = _DummyContext(bot=_DummyBot(), user_data={})

    with SessionLocal() as session:
        if not session.query(User).filter_by(telegram_id=telegram_user.id).one_or_none():
            user = User(telegram_id=telegram_user.id, username="tester", timezone="Europe/Moscow")
            session.add(user)
            session.commit()

    asyncio.run(process_text(update, context, message.text, source="message"))

    assert message.replies, "Ожидается ответ бота"
    final_texts = [text for text, _ in message.edits]
    assert any("Заметку оформила" in text for text in final_texts)

    beta_state = context.user_data.get("beta", {})
    note_id = beta_state.get("active_note_id")
    assert note_id, "Должен быть выбран активный идентификатор заметки"

    with SessionLocal() as session:
        stored_note = NoteService(session).get_note(note_id)
        assert stored_note is not None
        assert stored_note.summary == "Краткий итог"
        assert stored_note.text == message.text


def test_process_text_updates_note_text(monkeypatch):
    AGENT_MANAGER._sessions.clear()

    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)

    with SessionLocal() as session:
        user = User(telegram_id=888, username="writer", timezone="Europe/Moscow")
        session.add(user)
        session.commit()
        note = NoteService(session).create_note(
            user=user,
            text="Изначальный текст заметки.",
            status=NoteStatus.INGESTED.value,
        )

    telegram_user = SimpleNamespace(id=888, username="writer", first_name="Writer", last_name="User")
    session_obj = AGENT_MANAGER.get_session(telegram_user)
    session_obj.set_active_note(note)

    context = _DummyContext(bot=_DummyBot(), user_data={"beta": {"active_note_id": note.id}})

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Обновляю заметку.",
                "actions": [
                    {
                        "tool": "update_note_text",
                        "args": {"append": "Финальный вывод: договорились."},
                        "comment": "Обновляю текст",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    message = _DummyMessage("Добавь финальный вывод." )
    update = _DummyUpdate(message, telegram_user)

    asyncio.run(process_text(update, context, message.text, source="message"))

    assert message.replies
    final_texts = [text for text, _ in message.edits]
    assert any("Обновил заметку" in text for text in final_texts)

    with SessionLocal() as session:
        stored_note = NoteService(session).get_note(note.id)
        assert stored_note is not None
        assert "Финальный вывод" in stored_note.text


def test_process_text_triggers_search(monkeypatch):
    AGENT_MANAGER._sessions.clear()

    def _fake_search(_self, user_id, query, *, k=3):
        return [
            {"note": {"id": 1, "summary": "Отчёт по встрече", "text": "Договорились..."}},
            {"note": {"id": 2, "summary": "Идеи", "text": "Новые предложения"}},
        ][:k]

    monkeypatch.setattr(IndexService, "search", _fake_search)
    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)

    with SessionLocal() as session:
        user = User(telegram_id=999, username="searcher", timezone="Europe/Moscow")
        session.add(user)
        session.commit()
        note = NoteService(session).create_note(
            user=user,
            text="Черновик",
            status=NoteStatus.INGESTED.value,
        )

    telegram_user = SimpleNamespace(id=999, username="searcher", first_name="Search", last_name="User")
    session_obj = AGENT_MANAGER.get_session(telegram_user)
    session_obj.set_active_note(note)

    context = _DummyContext(bot=_DummyBot(), user_data={"beta": {"active_note_id": note.id}})

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Ищу заметки по запросу.",
                "actions": [
                    {
                        "tool": "search_notes",
                        "args": {"query": "встреча", "k": 2},
                        "comment": "Ищу по заметкам",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    message = _DummyMessage("Покажи заметки про встречу")
    update = _DummyUpdate(message, telegram_user)

    asyncio.run(process_text(update, context, message.text, source="message"))

    assert message.replies
    final_texts = [text for text, _ in message.edits]
    assert any("Нашёл заметки" in text for text in final_texts)


def test_agent_session_open_note_tool(monkeypatch, user_session, caplog):
    caplog.set_level("ERROR")
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(
            user=user,
            text="Подробности о проекте UserBot. Нужен отчёт." ,
            summary="UserBot: отчёт",
            tags=["userbot", "отчёт"],
            status=NoteStatus.PROCESSED.value,
        )

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Показываю заметку.",
                "actions": [
                    {
                        "tool": "open_note",
                        "args": {"note_id": note.id},
                        "comment": "Открываю заметку",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_user_message("что в заметке"))

    if "Инструмент" in result.text:
        errors = [record.__dict__.get("error") for record in caplog.records if record.message == "Agent tool failed"]
        raise AssertionError(f"tool error: {errors}")

    assert "UserBot" in result.text
    assert user_session.active_note_id == note.id


def test_agent_session_add_tags_tool(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(
            user=user,
            text="Черновик заметки",
            summary="Черновик",
            tags=["draft"],
            status=NoteStatus.PROCESSED.value,
        )

    async def _fake_call(*_args, **_kwargs):
        return json.dumps(
            {
                "response": "Обновляю теги.",
                "actions": [
                    {
                        "tool": "add_tags",
                        "args": {"note_id": note.id, "tags": ["review", "important"]},
                        "comment": "Добавляю теги",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    asyncio.run(user_session.handle_user_message("добавь теги"))

    with SessionLocal() as session:
        stored_note = NoteService(session).get_note(note.id)
        assert sorted(stored_note.tags) == ["draft", "important", "review"]
