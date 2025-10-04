"""Tests for the refactored beta agent runtime."""

import json
import os
import asyncio
from types import SimpleNamespace
from typing import Any
from datetime import datetime

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite://')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from transkribator_modules.beta.agent_runtime import AgentSession, AgentUser, _parse_agent_json, _build_fallback_message
from transkribator_modules.beta.handlers.entrypoint import _merge_artifact_hint, _NoteSnapshot
from transkribator_modules.beta.command_processor import execute_command
from transkribator_modules.beta.tools import IndexService
from transkribator_modules.beta.presets import Preset
from transkribator_modules.beta.timezone import TIMEZONE_REMINDER
from transkribator_modules.db.database import Base, SessionLocal, NoteService
from transkribator_modules.db.models import NoteStatus, User


@pytest.fixture(autouse=True)
def _inmemory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    monkeypatch.setattr("transkribator_modules.db.database.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.agent_runtime.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.tools.SessionLocal", Session)
    monkeypatch.setattr("transkribator_modules.beta.command_processor.SessionLocal", Session)
    from transkribator_modules.db import database as db_module
    globals()['SessionLocal'] = db_module.SessionLocal

    yield


@pytest.fixture
def user_session(monkeypatch):
    with SessionLocal() as session:
        user = User(telegram_id=123, username="tester", timezone='Europe/Moscow')
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

    # Prevent IndexService from performing real embedding work
    monkeypatch.setattr(IndexService, "add", lambda *args, **kwargs: None)
    monkeypatch.setattr(IndexService, "search", lambda *args, **kwargs: [])

    return agent_session


def test_agent_session_executes_tools(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = 'Europe/Moscow'
        session.commit()
        note = NoteService(session).create_note(user=user, text="Запланировать встречу завтра", status=NoteStatus.INGESTED.value)

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
    async def _fake_call(*args, **kwargs):
        return json.dumps(response_payload)

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_ingest(
        {
            "note_id": note.id,
            "text": "Запланировать встречу завтра",
            "summary": None,
            "source": "message",
            "created_at": "2024-10-02T10:00:00",
            "created": True,
        }
    ))

    assert "Заметку оформила." in result.text
    assert "Предлагаю добавить встречу" in result.text
    assert result.tool_results
    assert any(r.suggestion for r in result.tool_results)

    with SessionLocal() as session:
        stored_note = NoteService(session).get_note(note.id)
        assert stored_note.status == NoteStatus.APPROVED.value


def test_agent_session_user_message_no_actions(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_call(*args, **kwargs):
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
    async def _fake_call(*args, **kwargs):
        return "not a json"

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_call,
    )

    result = asyncio.run(user_session.handle_user_message("Просто сохрани"))
    assert result.text.startswith("Команда выполнена для заметки #")
    assert "готово" not in result.text.lower()


def test_agent_session_ingest_fallback(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Черновик", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_call(*args, **kwargs):
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


def test_agent_session_free_prompt_tool(monkeypatch, user_session, caplog):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(
            user=user,
            text="Черновик",
            status=NoteStatus.INGESTED.value,
        )

    user_session.set_active_note(note)

    dummy_preset = Preset(
        id="custom.free_prompt",
        title="Free prompt",
        description="",
        content_types=("other",),
        kind="custom",
        detail="normal",
        tone="neutral",
        output_format="md",
        priority=100,
        match_hints=(),
        min_characters=None,
        max_characters=None,
        requires_timecodes=False,
        system_prompt="",
        user_prompt_template="{text}",
        post_actions={},
    )

    monkeypatch.setattr("transkribator_modules.beta.tools.get_free_prompt", lambda: dummy_preset)

    async def _fake_process(*args, **kwargs):
        return {
            "note_id": note.id,
            "rendered_output": "Итоговый текст заметки",
            "drive": {},
        }

    monkeypatch.setattr(
        "transkribator_modules.beta.tools._content_processor.process",
        _fake_process,
    )

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "",
                "actions": [
                    {
                        "tool": "free_prompt",
                        "args": {"prompt": "сделай саммари"},
                        "comment": "Обрабатываю заметку",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    caplog.set_level("ERROR")

    result = asyncio.run(user_session.handle_user_message("сделай саммари"))
    if result.text.startswith("Инструмент free_prompt завершился с ошибкой"):
        # For easier debugging when the tool fails, include logged error in assertion message
        errors = [record.__dict__.get('error') for record in caplog.records if record.levelname == 'ERROR']
        raise AssertionError(f"free_prompt tool failed: {errors}")

    assert "Действие `free_prompt` выполнено." in result.text
    assert "Итоговый текст заметки" in result.text


def test_agent_session_calendar_requires_timezone(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = None
        session.commit()
        note = NoteService(session).create_note(
            user=user,
            text="Созвон завтра",
            status=NoteStatus.INGESTED.value,
        )

    user_session.set_active_note(note)

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "",
                "actions": [
                    {
                        "tool": "create_calendar_event",
                        "args": {"start": "2025-10-04T12:00"},
                        "comment": "Создаю встречу",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    result = asyncio.run(user_session.handle_user_message("Создай встречу"))
    assert TIMEZONE_REMINDER in result.text


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


def test_agent_session_create_calendar_event(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        note = NoteService(session).create_note(user=user, text="Созвон завтра в 12", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    monkeypatch.setattr("transkribator_modules.beta.tools.FEATURE_GOOGLE_CALENDAR", True)

    class _DummyCred:
        pass

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.GoogleCredentialService.get_credentials",
        lambda self, user_id: _DummyCred(),
    )

    captured: dict[str, Any] = {}

    def _fake_create(credentials, title, start, end, description, **kwargs):
        captured.update({
            'credentials': credentials,
            'title': title,
            'start': start,
            'end': end,
            'description': description,
        })
        return {
            'htmlLink': 'https://calendar.google.com/event',
            'id': 'evt-123',
            'start': {'dateTime': '2024-10-02T12:00:00+03:00', 'timeZone': 'Europe/Moscow'},
        }

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.calendar_create_timebox",
        _fake_create,
    )

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "Встречу создала.",
                "actions": [
                    {
                        "tool": "create_calendar_event",
                        "args": {"start": "2024-10-02 12:00", "duration_minutes": 45},
                        "comment": "Записываю событие",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    result = asyncio.run(user_session.handle_user_message("Добавь встречу"))

    assert 'Встречу создала.' in result.text
    assert captured.get('title')
    start_iso = captured.get('start')
    assert start_iso
    start_dt = datetime.fromisoformat(start_iso)
    assert (start_dt.hour, start_dt.minute) == (12, 0)

    with SessionLocal() as session:
        stored = NoteService(session).get_note(note.id)
        links = stored.links
        if isinstance(links, str):
            links = json.loads(links)
        assert links.get('calendar_url') == 'https://calendar.google.com/event'
        meta = stored.meta
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta.get('calendar_event_id') == 'evt-123'
        assert meta.get('calendar_timezone') == 'Europe/Moscow'


def test_agent_session_create_requires_timezone(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = None
        session.commit()
        note = NoteService(session).create_note(user=user, text="Создай встречу", status=NoteStatus.INGESTED.value)

    user_session.set_active_note(note)

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "Создаю.",
                "actions": [
                    {
                        "tool": "create_calendar_event",
                        "args": {"start": "2024-10-02 12:00"},
                        "comment": "Создаю встречу",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    result = asyncio.run(user_session.handle_user_message("Создай встречу"))

    assert 'часовой пояс' in result.text.lower()

    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = 'Europe/Moscow'
        session.commit()


def test_agent_session_update_requires_timezone(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = None
        session.commit()
        service = NoteService(session)
        note = service.create_note(user=user, text="Встреча", status=NoteStatus.INGESTED.value)
        service.update_note_metadata(
            note,
            links={'calendar_url': 'https://calendar.google.com/event'},
            meta={'calendar_event_id': 'evt-999', 'calendar_timezone': 'Europe/Moscow'},
        )

    user_session.set_active_note(note)

    monkeypatch.setattr("transkribator_modules.beta.tools.FEATURE_GOOGLE_CALENDAR", True)

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "Переношу.",
                "actions": [
                    {
                        "tool": "update_calendar_event",
                        "args": {"start": "2024-10-03 18:30"},
                        "comment": "Сдвигаю встречу",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    result = asyncio.run(user_session.handle_user_message("Перенеси встречу"))

    assert 'часовой пояс' in result.text.lower()

    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = 'Europe/Moscow'
        session.commit()


def test_calendar_command_requires_timezone(monkeypatch):
    monkeypatch.setattr("transkribator_modules.beta.command_processor.FEATURE_GOOGLE_CALENDAR", True)

    tg_user = SimpleNamespace(id=456, username="tzuser", first_name="TZ", last_name="User")
    payload = {
        "command": {
            "intent": "calendar",
            "args": {"mode": "changes"},
        }
    }

    result = asyncio.run(execute_command(tg_user, payload))

    assert 'часовой пояс' in result.lower()


def test_agent_session_update_calendar_event(monkeypatch, user_session):
    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = 'Europe/Moscow'
        session.commit()
        service = NoteService(session)
        note = service.create_note(user=user, text="Встреча", status=NoteStatus.INGESTED.value)
        service.update_note_metadata(
            note,
            links={'calendar_url': 'https://calendar.google.com/event'},
            meta={'calendar_event_id': 'evt-123', 'calendar_timezone': 'Europe/Moscow'},
        )

    user_session.set_active_note(note)

    monkeypatch.setattr("transkribator_modules.beta.tools.FEATURE_GOOGLE_CALENDAR", True)

    class _DummyCred:
        pass

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.GoogleCredentialService.get_credentials",
        lambda self, user_id: _DummyCred(),
    )

    captured: dict[str, Any] = {}

    def _fake_update(credentials, event_id, start, end, description, **kwargs):
        captured.update({
            'credentials': credentials,
            'event_id': event_id,
            'start': start,
            'end': end,
            'description': description,
        })
        return {
            'id': event_id,
            'htmlLink': 'https://calendar.google.com/event?updated=1',
            'start': {'dateTime': '2024-10-03T18:30:00+03:00', 'timeZone': 'Europe/Moscow'},
        }

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.calendar_update_timebox",
        _fake_update,
    )

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "Перенесла встречу.",
                "actions": [
                    {
                        "tool": "update_calendar_event",
                        "args": {"start": "2024-10-03 18:30", "duration_minutes": 30},
                        "comment": "Обновляю время",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    result = asyncio.run(user_session.handle_user_message("Перенеси встречу"))

    assert 'Перенесла встречу' in result.text
    assert captured.get('event_id') == 'evt-123'
    start_iso = captured.get('start')
    assert start_iso
    start_dt = datetime.fromisoformat(start_iso)
    assert (start_dt.hour, start_dt.minute) == (18, 30)

    with SessionLocal() as session:
        stored = NoteService(session).get_note(note.id)
        meta = stored.meta
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta.get('calendar_event_id') == 'evt-123'
        assert meta.get('calendar_timezone') == 'Europe/Moscow'
        links = stored.links
        if isinstance(links, str):
            links = json.loads(links)
        assert links.get('calendar_url').endswith('updated=1')


def test_agent_session_update_calendar_event_with_link_fallback(monkeypatch, user_session):
    encoded = 'ZXZ0LWxpbms='  # base64 urlsafe of 'evt-link'
    calendar_url = f"https://www.google.com/calendar/event?eid={encoded}"

    with SessionLocal() as session:
        user = session.query(User).filter_by(telegram_id=123).one()
        user.timezone = 'Europe/Moscow'
        session.commit()
        service = NoteService(session)
        note = service.create_note(user=user, text="Встреча", status=NoteStatus.INGESTED.value)
        service.update_note_metadata(
            note,
            links={'calendar_url': calendar_url},
        )

    user_session.set_active_note(note)

    monkeypatch.setattr("transkribator_modules.beta.tools.FEATURE_GOOGLE_CALENDAR", True)

    class _DummyCred:
        pass

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.GoogleCredentialService.get_credentials",
        lambda self, user_id: _DummyCred(),
    )

    captured: dict[str, Any] = {}

    def _fake_update(credentials, event_id, start, end, description, **kwargs):
        captured['event_id'] = event_id
        return {
            'id': event_id,
            'htmlLink': 'https://calendar.google.com/event?updated=2',
            'start': {'dateTime': '2024-10-04T10:00:00+03:00'},
        }

    monkeypatch.setattr(
        "transkribator_modules.beta.tools.calendar_update_timebox",
        _fake_update,
    )

    async def _fake_llm(*args, **kwargs):
        return json.dumps(
            {
                "response": "Перенесла встречу.",
                "actions": [
                    {
                        "tool": "update_calendar_event",
                        "args": {"start": "2024-10-04 10:00"},
                        "comment": "Обновляю время",
                    }
                ],
                "suggestions": [],
            }
        )

    monkeypatch.setattr(
        "transkribator_modules.beta.agent_runtime.call_agent_llm_with_retry",
        _fake_llm,
    )

    asyncio.run(user_session.handle_user_message("Перенеси встречу ещё раз"))

    assert captured.get('event_id') == 'evt-link'

    with SessionLocal() as session:
        stored = NoteService(session).get_note(note.id)
        meta = stored.meta
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta.get('calendar_event_id') == 'evt-link'
