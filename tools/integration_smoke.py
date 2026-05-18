#!/usr/bin/env python3
"""Integration smoke flow:
- create temp sqlite DB and patch SessionLocal across modules
- transcribe using StubAdapter
- create a note and run AgentSession.handle_ingest (stubbed LLM to save summary)
- run IndexService.search and print results
"""
from __future__ import annotations

import json
import asyncio
import tempfile
import os
import importlib
from pathlib import Path

# Move to repo root
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from transkribator_modules.db.database import Base

# Create temp sqlite DB
fd, tmp_path = tempfile.mkstemp(suffix='_live_smoke.sqlite')
os.close(fd)
engine = create_engine(f"sqlite:///{tmp_path}")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Patch SessionLocal in modules that use it
modules_to_patch = [
    'transkribator_modules.db.database',
    'transkribator_modules.beta.agent_runtime',
    'transkribator_modules.beta.tools',
    'transkribator_modules.beta.handlers.entrypoint',
    'transkribator_modules.search.index',
]
for mod_name in modules_to_patch:
    mod = importlib.import_module(mod_name)
    if hasattr(mod, 'SessionLocal'):
        setattr(mod, 'SessionLocal', Session)

# Create test user
from transkribator_modules.db.models import User, NoteStatus
from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.database import NoteService

with Session() as s:
    user = User(telegram_id=777, username='live_smoke', timezone='Europe/Moscow')
    s.add(user)
    s.commit()
    s.refresh(user)
    user_id = user.id

# Transcribe using stub
from transcribe_client import TranscribeClient
from transcribe_client.stub import StubAdapter
stub = StubAdapter(text='Это тестовая транскрипция: договорились созвониться завтра в 12:00')
client = TranscribeClient(adapter=stub)
res = client.transcribe('/tmp/sample.wav', mode='stub')
print('\n--- Transcription result ---')
print(json.dumps(res, ensure_ascii=False, indent=2))

# Create note
with Session() as s:
    user = s.query(User).filter_by(telegram_id=777).one()
    note = NoteService(s).create_note(user=user, text=res['text'], status=NoteStatus.INGESTED.value)
    note_id = note.id
    print('\nCreated note id=', note_id)

# Stub LLM and run agent handler
from transkribator_modules.beta.agent_runtime import call_agent_llm_with_retry as real_call

async def _fake_call(*_args, **_kwargs):
    payload = {
        'response': 'Сохраняю заметку.',
        'actions': [
            {'tool': 'save_note', 'args': {'summary': 'Договорились созвониться завтра в 12:00'}, 'comment': 'Сохраняю заметку'},
        ],
        'suggestions': [],
    }
    return json.dumps(payload)

import transkribator_modules.beta.agent_runtime as art
art.call_agent_llm_with_retry = _fake_call
from transkribator_modules.beta.agent_runtime import AgentUser, AgentSession
agent_user = AgentUser(telegram_id=777, db_id=user_id, username='live_smoke', first_name='Live', last_name='Smoke')
agent_session = AgentSession(agent_user)
agent_session.set_active_note(note)

payload = {
    'note_id': note_id,
    'text': res['text'],
    'summary': None,
    'source': 'message',
    'created_at': '2026-02-05T10:00:00',
    'created': True,
}

print('\n--- Running handle_ingest ---')
result = asyncio.run(agent_session.handle_ingest(payload))
print('\nAgent result:')
print(result)

# Verify stored note
with Session() as s:
    stored = NoteService(s).get_note(note_id)
    print('\nStored note: id=', stored.id, 'status=', stored.status, 'summary=', stored.summary)

# Search the index
from transkribator_modules.search.index import IndexService
idx = IndexService()

async def do_search():
    return await idx.search(user_id, 'созвониться', k=5)

search_res = asyncio.run(do_search())
print('\nSearch results:')
print(json.dumps(search_res, ensure_ascii=False, indent=2))

print('\nSmoke flow finished; temp DB at', tmp_path)
