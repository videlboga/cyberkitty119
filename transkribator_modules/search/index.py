"""PostgreSQL vector index backed by pgvector."""

from __future__ import annotations

import json
import os
import re
from typing import Iterable

import numpy as np
from sqlalchemy import delete, select, func, text
from sqlalchemy.orm import Session

from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import NoteChunk, Note, NoteEmbedding
from transkribator_modules.search.embeddings import embed_texts_async, _hash_embeddings, EMBEDDING_DIM
from transkribator_modules.search.reranker import rerank_results, ENABLE_RERANKING, RERANK_TOP_K

CHUNK_SIZE = 800
CHUNK_OVERLAP = 200

# Hybrid search settings
ENABLE_HYBRID_SEARCH = os.getenv('ENABLE_HYBRID_SEARCH', 'false').lower() in {'1', 'true', 'yes'}
HYBRID_VECTOR_WEIGHT = float(os.getenv('HYBRID_VECTOR_WEIGHT', '0.7'))  # 70% vector, 30% full-text
HYBRID_FULLTEXT_WEIGHT = 1.0 - HYBRID_VECTOR_WEIGHT

try:  # Detect pgvector availability
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pragma: no cover - pgvector optional
    PgVector = None

_EMBEDDING_TYPE = NoteChunk.__table__.c.embedding.type
USE_PGVECTOR = bool(PgVector) and isinstance(_EMBEDDING_TYPE, PgVector)


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterable[str]:
    """Умное разбиение текста на чанки с учётом границ параграфов и предложений."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    
    # Если текст короткий, возвращаем как есть
    if len(cleaned) <= chunk_size:
        return [cleaned]
    
    chunks: list[str] = []
    
    # Сначала разбиваем по параграфам (двойной перенос строки)
    paragraphs = re.split(r'\n\s*\n', cleaned)
    
    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # Если параграф сам по себе длинный, разбиваем по предложениям
        if len(para) > chunk_size:
            # Если есть незавершённый чанк, сохраняем его
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            
            # Разбиваем длинный параграф по предложениям
            sentences = re.split(r'([.!?]+[\s\n]+)', para)
            sentence_chunk = ""
            
            for i in range(0, len(sentences), 2):
                sentence = sentences[i]
                delimiter = sentences[i + 1] if i + 1 < len(sentences) else ""
                full_sentence = sentence + delimiter
                
                if len(sentence_chunk) + len(full_sentence) > chunk_size:
                    if sentence_chunk:
                        chunks.append(sentence_chunk.strip())
                    sentence_chunk = full_sentence
                else:
                    sentence_chunk += full_sentence
            
            if sentence_chunk:
                current_chunk = sentence_chunk
        else:
            # Параграф нормального размера
            if len(current_chunk) + len(para) + 2 > chunk_size:
                # Текущий чанк полон, сохраняем
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                # Добавляем параграф к текущему чанку
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
    
    # Добавляем последний чанк
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # Если получился только один большой чанк или слишком длинные чанки,
    # применяем старый алгоритм с перекрытием
    if len(chunks) == 1 and len(chunks[0]) > chunk_size * 1.5:
        return _chunk_text_simple(cleaned, chunk_size, overlap)
    
    # Проверяем что чанки не слишком большие
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 1.5:
            # Слишком большой чанк, разбиваем дальше
            final_chunks.extend(_chunk_text_simple(chunk, chunk_size, overlap))
        else:
            final_chunks.append(chunk)
    
    return [chunk for chunk in final_chunks if chunk.strip()]


def _chunk_text_simple(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> Iterable[str]:
    """Простое разбиение текста на чанки с фиксированным перекрытием (fallback)."""
    cleaned = (text or "").strip()
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


def _coerce_tags(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except Exception:
            return []
        if isinstance(data, list):
            return [str(tag).strip() for tag in data if str(tag).strip()]
    return []


def _coerce_links(raw: object) -> dict:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if isinstance(raw, str) and raw:
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items()}
    return {}


def _serialize_note(note: Note) -> dict:
    tags = _coerce_tags(getattr(note, "tags", []))
    links = _coerce_links(getattr(note, "links", {}))
    return {
        "id": note.id,
        "ts": note.ts.isoformat() if note.ts else None,
        "type_hint": note.type_hint or "other",
        "summary": note.summary or "",
        "text": note.text or "",
        "tags": tags,
        "links": links,
    }


class IndexService:
    """Stores note chunks and embeddings inside PostgreSQL."""

    def __init__(self):
        self.session_factory = SessionLocal

    async def add(
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
            embeddings = await embed_texts_async(chunks)
            if len(embeddings) != len(chunks):
                embeddings = [await embed_texts_async([chunk])[0] for chunk in chunks]
            for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
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

    async def rebuild(self, notes: list[dict]) -> int:
        updated = 0
        for item in notes:
            text = (item.get("text") or "").strip()
            summary = item.get("summary")
            if not text and not summary:
                continue
            await self.add(
                item["note_id"],
                item["user_id"],
                text,
                summary=summary,
            )
            updated += 1
        return updated

    def remove(self, note_id: int, user_id: int) -> None:
        with self.session_factory() as session:
            session.execute(
                delete(NoteChunk).where(
                    NoteChunk.note_id == note_id,
                    NoteChunk.user_id == user_id,
                )
            )
            session.execute(
                delete(NoteEmbedding).where(
                    NoteEmbedding.note_id == note_id,
                    NoteEmbedding.user_id == user_id,
                )
            )
            session.commit()

    def _fulltext_search(self, session: Session, user_id: int, query: str, k: int = 20) -> list[dict]:
        """PostgreSQL full-text search using ts_vector and ts_query."""
        # Prepare search query (remove special characters, use | for OR)
        search_terms = re.sub(r'[^\w\s]', '', query).split()
        if not search_terms:
            return []
        
        tsquery = ' | '.join(search_terms)  # OR search for all terms
        
        try:
            # Use PostgreSQL full-text search
            stmt = text("""
                SELECT nc.id, nc.note_id, nc.chunk_index, nc.text,
                       ts_rank(to_tsvector('russian', nc.text), to_tsquery('russian', :tsquery)) as rank
                FROM note_chunks nc
                JOIN notes n ON n.id = nc.note_id
                WHERE nc.user_id = :user_id
                  AND n.status != 'archived'
                  AND to_tsvector('russian', nc.text) @@ to_tsquery('russian', :tsquery)
                ORDER BY rank DESC
                LIMIT :k
            """)
            
            rows = session.execute(
                stmt,
                {'user_id': user_id, 'tsquery': tsquery, 'k': k}
            ).fetchall()
            
            results = []
            for row in rows:
                chunk_id, note_id, chunk_index, chunk_text, rank = row
                
                # Fetch note details
                note = session.query(Note).filter(Note.id == note_id).first()
                if note:
                    results.append({
                        'note_id': note_id,
                        'chunk_index': chunk_index,
                        'chunk': chunk_text,
                        'score': float(rank),
                        'note': _serialize_note(note),
                    })
            
            return results
        except Exception as exc:  # noqa: BLE001
            # Fallback if full-text search fails (e.g., not PostgreSQL)
            from transkribator_modules.config import logger
            logger.warning('Full-text search failed, using vector only', extra={'error': str(exc)})
            return []

    async def search(
        self,
        user_id: int,
        query: str,
        k: int = 5,
        *,
        tags: list[str] | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """
        Search for relevant note chunks with optional filters.
        
        Args:
            user_id: User ID
            query: Search query
            k: Number of results to return
            tags: Filter by tags (notes must have at least one of these tags)
            status: Filter by note status
            date_from: Filter notes created after this date (ISO format)
            date_to: Filter notes created before this date (ISO format)
        """
        # Fetch more candidates if reranking is enabled
        fetch_k = RERANK_TOP_K if ENABLE_RERANKING else k
        
        query_embedding_list = (await embed_texts_async([query or ""]))[0]
        with self.session_factory() as session:
            if USE_PGVECTOR:
                # Build filters
                filters = [
                    NoteChunk.user_id == user_id,
                    Note.status != "archived",
                ]
                
                # Add metadata filters
                if status:
                    filters.append(Note.status == status)
                
                if tags:
                    # Filter by tags (note must have at least one of the specified tags)
                    from sqlalchemy import or_, and_, cast, String
                    tag_conditions = [
                        cast(Note.tags, String).like(f'%{tag}%') 
                        for tag in tags
                    ]
                    filters.append(or_(*tag_conditions))
                
                if date_from:
                    from datetime import datetime
                    try:
                        dt_from = datetime.fromisoformat(date_from)
                        filters.append(Note.created_at >= dt_from)
                    except ValueError:
                        pass
                
                if date_to:
                    from datetime import datetime
                    try:
                        dt_to = datetime.fromisoformat(date_to)
                        filters.append(Note.created_at <= dt_to)
                    except ValueError:
                        pass
                
                # Vector search results
                distance = NoteChunk.embedding.cosine_distance(query_embedding_list)
                stmt = (
                    select(
                        NoteChunk,
                        Note,
                        distance.label("distance"),
                    )
                    .join(Note, Note.id == NoteChunk.note_id)
                    .where(*filters)
                    .order_by(distance)
                    .limit(fetch_k * 2 if ENABLE_HYBRID_SEARCH else fetch_k)  # Fetch more for hybrid
                )
                rows = session.execute(stmt).all()

                vector_matches: list[dict] = []
                for chunk, note, distance in rows:
                    vector_matches.append(
                        {
                            "note_id": note.id,
                            "chunk_index": chunk.chunk_index,
                            "chunk": chunk.text,
                            "score": float(distance if distance is not None else 0.0),
                            "note": _serialize_note(note),
                        }
                    )
                
                # Hybrid search: combine vector + full-text
                if ENABLE_HYBRID_SEARCH and vector_matches:
                    fulltext_matches = self._fulltext_search(session, user_id, query, k=fetch_k * 2)
                    
                    if fulltext_matches:
                        # Merge results with weighted scores
                        # Normalize scores to [0, 1] range
                        max_vector_score = max([m['score'] for m in vector_matches]) if vector_matches else 1.0
                        max_ft_score = max([m['score'] for m in fulltext_matches]) if fulltext_matches else 1.0
                        
                        # Create combined results dict by note_id + chunk_index
                        combined = {}
                        
                        for match in vector_matches:
                            key = (match['note_id'], match['chunk_index'])
                            normalized_score = 1.0 - (match['score'] / max_vector_score) if max_vector_score > 0 else 0.0
                            combined[key] = {
                                **match,
                                'vector_score': normalized_score,
                                'fulltext_score': 0.0,
                            }
                        
                        for match in fulltext_matches:
                            key = (match['note_id'], match['chunk_index'])
                            normalized_score = match['score'] / max_ft_score if max_ft_score > 0 else 0.0
                            if key in combined:
                                combined[key]['fulltext_score'] = normalized_score
                            else:
                                combined[key] = {
                                    **match,
                                    'vector_score': 0.0,
                                    'fulltext_score': normalized_score,
                                }
                        
                        # Calculate hybrid score
                        for key in combined:
                            vec_score = combined[key]['vector_score']
                            ft_score = combined[key]['fulltext_score']
                            combined[key]['score'] = (
                                HYBRID_VECTOR_WEIGHT * vec_score + 
                                HYBRID_FULLTEXT_WEIGHT * ft_score
                            )
                        
                        # Sort by hybrid score
                        matches = sorted(combined.values(), key=lambda x: x['score'], reverse=True)
                        matches = matches[:fetch_k]
                    else:
                        matches = vector_matches
                else:
                    matches = vector_matches
                
                # Apply reranking if enabled
                if ENABLE_RERANKING and len(matches) > 1:
                    matches = await rerank_results(query, matches, top_k=k)
                
                return matches[:k]

            stmt = (
                select(NoteChunk, Note)
                .join(Note, Note.id == NoteChunk.note_id)
                .where(
                    NoteChunk.user_id == user_id,
                    Note.status != "archived",
                )
            )
            rows = session.execute(stmt).all()

        query_vec = np.array(query_embedding_list, dtype=np.float32)
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
                    "note_id": note.id,
                    "chunk_index": chunk.chunk_index,
                    "chunk": chunk.text,
                    "score": distance,
                    "note": _serialize_note(note),
                }
            )

        scored.sort(key=lambda item: item["score"])
        
        # Apply reranking if enabled (fallback mode without pgvector)
        if ENABLE_RERANKING and len(scored) > 1:
            scored = await rerank_results(query, scored[:fetch_k], top_k=k)
        
        return scored[:k]
