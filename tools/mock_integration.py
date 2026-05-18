#!/usr/bin/env python3
import os, json, tempfile
from pathlib import Path
# lightweight mocked integration flow
SRC = Path(__file__).resolve().parents[1]
print('Project mounted at', SRC)
# 1) 'Upload' video/audio (we'll use sample.wav presence)
wav = SRC / 'sample.wav'
print('sample.wav exists:', wav.exists())

# 2) Transcription (mocked): try to read precomputed transcript file, else use placeholder
transcript_file = SRC / 'json' / 'sample_transcript.txt'
if transcript_file.exists():
    transcript = transcript_file.read_text(encoding='utf-8')
    print('Loaded precomputed transcript from', transcript_file)
else:
    transcript = (
        'Сегодня обсудили релиз версии проекта. Решили подготовить тестовый план и распределить задачи. '
        'Ответственный — Алиса. Дата встречи: завтра 12:00.'
    )
    print('Using placeholder transcript')
print('\n--- Transcript ---')
print(transcript)

# 3) Create note (mock DB)
notes = []

def create_note(text, status='INGESTED'):
    nid = len(notes) + 1
    note = {'id': nid, 'text': text, 'summary': None, 'status': status}
    notes.append(note)
    return note

note = create_note(transcript)
print('\nCreated note:', note)

# 4) Save note via 'agent' (mock LLM returns action save_note)
# simple 'agent' applies a summary = first sentence

def simple_summary(text):
    # naive: split by sentence end
    for sep in ['. ', '! ', '? ', '\n']:
        if sep in text:
            return text.split(sep)[0].strip() + '.'
    return text[:120].strip()

agent_response = {
    'response': 'Сохраняю заметку.',
    'actions': [
        {'tool': 'save_note', 'args': {'summary': simple_summary(transcript)}, 'comment': 'Сохраняю заметку из мок-агента'}
    ],
    'suggestions': []
}
print('\nAgent response (mock):')
print(json.dumps(agent_response, ensure_ascii=False, indent=2))

# apply save
for act in agent_response['actions']:
    if act['tool'] == 'save_note':
        note['summary'] = act['args'].get('summary')
        note['status'] = 'APPROVED'
        print('\nApplied save_note -> summary set to:', note['summary'])

# 5) Indexing (mock): create simple inverted index
index = {}

def index_note(n):
    words = set(w.strip('.,!?').lower() for w in n['text'].split())
    for w in words:
        index.setdefault(w, set()).add(n['id'])

index_note(note)
print('\nIndex keys sample:', list(index.keys())[:10])

# 6) Search demo
queries = ['релиз', 'встреча', 'Алиса', 'несуществующее']
print('\nSearch results:')
for q in queries:
    qk = q.lower()
    found_ids = index.get(qk, set())
    print(f"- query '{q}' -> note ids: {sorted(found_ids)}")

# 7) Generate a short summary (mock second-stage LLM)
summary = f"Краткий итог: {note['summary']}"
print('\nFinal generated summary:')
print(summary)

print('\n--- Stored notes ---')
for n in notes:
    print(n)
