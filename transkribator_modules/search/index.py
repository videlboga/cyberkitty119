"""PostgreSQL vector index backed by pgvector."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable, List

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import NoteChunk, Note

CHUNK_SIZE = 800
CHUNK_OVERLAP = 200
EMBEDDING_DIM = 256

try:  # Detect pgvector availability
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pragma: no cover - pgvector optional
    PgVector = None

_EMBEDDING_TYPE = NoteChunk.__table__.c.embedding.type
USE_PGVECTOR = bool(PgVector) and isinstance(_EMBEDDING_TYPE, PgVector)


def _hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    digest = hashlib.sha256(text.encode('utf-8')).digest()
    repeats = (dim * 4) // len(digest) + 1
    data = (digest * repeats)[: dim * 4]
    arr = np.frombuffer(data, dtype=np.uint8).astype(np.float32)
    arr = arr[:dim]
    norm = np.linalg.norm(arr)
    if norm:
        arr = arr / norm
    return arr.tolist()


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterable[str]:
    cleaned = (text or '').strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = cleaned[start:end]
        chunks.append(chunk.strip())
        if end == length:
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def _serialize_note(note: Note) -> dict:
    try:
        tags = json.loads(note.tags or '[]')
        if not isinstance(tags, list):
            tags = []
    except Exception:
        tags = []
    try:
        links = json.loads(note.links or '{}')
        if not isinstance(links, dict):
            links = {}
    except Exception:
        links = {}
    return {
        'id': note.id,
        'ts': note.ts.isoformat() if note.ts else None,
        'type_hint': note.type_hint or 'other',
        'summary': note.summary or '',
        'text': note.text or '',
        'tags': tags,
        'links': links,
    }


class IndexService:
    """Stores note chunks and embeddings inside PostgreSQL."""

    def __init__(self):
        self.session_factory = SessionLocal

    def add(
        self,
        note_id: int,
        user_id: int,
        text: str,
        *,
        summary: str | None = None,
        type_hint: str | None = None,
        tags: list[str] | None = None,
        links: dict | None = None,
    ) -> None:
        combined_text = "\n\n".join(filter(None, [summary, text]))
        chunks = list(_chunk_text(combined_text))
        if not chunks:
            return

        with self.session_factory() as session:
            session.execute(
                delete(NoteChunk).where(
                    NoteChunk.note_id == note_id,
                    NoteChunk.user_id == user_id,
                )
            )
            for idx, chunk_text in enumerate(chunks):
                embedding = _hash_embedding(chunk_text)
                stored_embedding = embedding if USE_PGVECTOR else json.dumps(embedding)
                session.add(
                    NoteChunk(
                        note_id=note_id,
                        user_id=user_id,
                        chunk_index=idx,
                        text=chunk_text,
                        embedding=stored_embedding,
                    )
                )
            session.commit()

    def rebuild(self, notes: list[dict]) -> int:
        updated = 0
        for item in notes:
            text = (item.get('text') or '').strip()
            summary = item.get('summary')
            if not text and not summary:
                continue
            self.add(
                item['note_id'],
                item['user_id'],
                text,
                summary=summary,
            )
            updated += 1
        return updated

    def search(self, user_id: int, query: str, k: int = 5) -> list[dict]:
        embedding = _hash_embedding(query)
        with self.session_factory() as session:
            if USE_PGVECTOR:
                distance = NoteChunk.embedding.l2_distance(embedding)
                stmt = (
                    select(
                        NoteChunk,
                        Note,
                        distance.label('distance'),
                    )
                    .join(Note, Note.id == NoteChunk.note_id)
                    .where(NoteChunk.user_id == user_id)
                    .order_by(distance)
                    .limit(k)
                )
                rows = session.execute(stmt).all()

                matches: list[dict] = []
                for chunk, note, distance in rows:
                    matches.append(
                        {
                            'note_id': note.id,
                            'chunk_index': chunk.chunk_index,
                            'chunk': chunk.text,
                            'score': float(distance if distance is not None else 0.0),
                            'note': _serialize_note(note),
                        }
                    )
                return matches

            # Fallback: emulate vector search in Python for non-pgvector backends
            stmt = (
                select(NoteChunk, Note)
                .join(Note, Note.id == NoteChunk.note_id)
                .where(NoteChunk.user_id == user_id)
            )
            rows = session.execute(stmt).all()

        query_vec = np.array(embedding, dtype=np.float32)
        scored: list[dict] = []
        for chunk, note in rows:
            try:
                stored = json.loads(chunk.embedding) if isinstance(chunk.embedding, str) else chunk.embedding
            except Exception:  # noqa: BLE001
                stored = None
            if not stored:
                continue
            chunk_vec = np.array(stored, dtype=np.float32)
            if chunk_vec.size == 0:
                continue
            distance = float(np.linalg.norm(chunk_vec - query_vec))
            scored.append(
                {
                    'note_id': note.id,
                    'chunk_index': chunk.chunk_index,
                    'chunk': chunk.text,
                    'score': distance,
                    'note': _serialize_note(note),
                }
            )

        scored.sort(key=lambda item: item['score'])
        return scored[:k]
