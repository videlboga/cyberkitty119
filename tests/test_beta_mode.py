"""Unit tests for beta-mode helpers and note service."""

import json
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from transkribator_modules.beta.handlers.content_flow import compose_header
from transkribator_modules.beta.handlers.command_flow import build_confirmation_text
from transkribator_modules.db.database import NoteService
from transkribator_modules.db.models import Base, User, NoteStatus, Reminder
from transkribator_modules.beta.command_processor import execute_command


def setup_inmemory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_compose_header_manual_type_priority():
    header = compose_header("idea", 0.9, manual_type="meeting")
    assert "Выбрали" in header
    assert "встреча" in header


def test_compose_header_confidence_levels():
    confident = compose_header("idea", 0.8, manual_type=None)
    assert "Похоже" in confident

    unsure = compose_header("idea", 0.1, manual_type=None)
    assert "Что делаем" in unsure


def test_note_service_create_and_backlog():
    session = setup_inmemory_session()

    user = User(telegram_id=123456)
    session.add(user)
    session.commit()

    service = NoteService(session)

    note = service.create_note(
        user=user,
        text="Тестовая заметка",
        type_hint="idea",
        type_confidence=0.9,
        status=NoteStatus.PROCESSED.value,
    )

    assert note.id is not None
    assert json.loads(note.tags) == []
    assert json.loads(note.links) == {}

    backlog = service.list_backlog(user)
    assert backlog == []

    service.update_status(note, NoteStatus.BACKLOG.value)
    backlog = service.list_backlog(user)
    assert len(backlog) == 1
    assert backlog[0].id == note.id

    reminder = service.schedule_backlog_reminder(user, note)
    assert reminder.note_id == note.id
    assert json.loads(reminder.payload)["kind"] == "backlog_reminder"


def test_build_confirmation_text_handles_query_and_action():
    payload = {
        "command": {
            "intent": "qa",
            "args": {"query": "как дела?", "action": "summary"},
        }
    }
    text = build_confirmation_text(payload)
    assert "qa" in text
    assert "как дела?" in text
    assert "summary" in text


class StubTelegramUser:
    def __init__(self, user_id: int, username: str = None):
        self.id = user_id
        self.username = username
        self.first_name = 'Test'
        self.last_name = 'User'


def test_execute_command_filter(monkeypatch):
    def fake_session_factory():
        s = setup_inmemory_session()
        user = User(telegram_id=555)
        s.add(user)
        s.commit()
        NoteService(s).create_note(user, 'text', type_hint='idea', status=NoteStatus.PROCESSED.value)
        return s

    monkeypatch.setattr('transkribator_modules.beta.command_processor.SessionLocal', fake_session_factory)

    response = asyncio.run(execute_command(StubTelegramUser(555), {'command': {'intent': 'filter', 'args': {}}})
    )
    assert 'Подходящие' in response or 'заметок не нашлось' in response
