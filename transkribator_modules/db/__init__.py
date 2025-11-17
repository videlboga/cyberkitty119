"""Database package exports for Transkribator."""

from .database import engine, SessionLocal, init_database
from .models import Base, ProcessingJob, ProcessingJobStatus


def init_db() -> None:
    """Backward-compatible helper to initialize database."""
    init_database()


__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "init_db",
    "init_database",
    "ProcessingJob",
    "ProcessingJobStatus",
]
