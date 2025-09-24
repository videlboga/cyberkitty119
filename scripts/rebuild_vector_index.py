"""Backfill Google vector index from existing notes."""

from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import Note, NoteStatus
from transkribator_modules.search import IndexService


def rebuild() -> int:
    index = IndexService()
    count = 0
    with SessionLocal() as session:
        notes = (
            session.query(Note)
            .filter(Note.status != NoteStatus.BACKLOG.value)
            .all()
        )
        payload = []
        for note in notes:
            payload.append(
                {
                    'note_id': note.id,
                    'user_id': note.user_id,
                    'text': note.text or '',
                    'summary': note.summary or '',
                }
            )
        count = index.rebuild(payload)
    return count


if __name__ == '__main__':
    total = rebuild()
    print(f'Reindexed {total} notes into PostgreSQL vector store.')
