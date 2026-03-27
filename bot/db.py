"""
Работа с базой данных для нового бота.

Использует существующую инфраструктуру transkribator_modules:
- ProcessingJob — задача в очереди
- User — пользователь (telegram_id → id)
- Note — транскрипция хранится в notes.text
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Убедиться, что корень проекта в sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from transkribator_modules.db.database import SessionLocal
from transkribator_modules.db.models import ProcessingJob, ProcessingJobStatus, User, Note


# ── Пользователи ─────────────────────────────────────────────────────────────

async def ensure_user(telegram_id: int) -> int:
    """Найти или создать пользователя по telegram_id. Вернуть internal id."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=str(telegram_id),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user.id
    finally:
        db.close()


def get_user_id_by_telegram_id(telegram_id: int) -> Optional[int]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user.id if user else None
    finally:
        db.close()


# ── Задачи ────────────────────────────────────────────────────────────────────

def get_job_row(job_id: int) -> Optional[Dict[str, Any]]:
    """Вернуть dict с полями status / progress / error для job_id."""
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return None
        payload = job.payload or {}
        status_blob = payload.get("_status") or {}
        return {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "error": job.error,
            "payload": payload,
            "stage": status_blob.get("stage"),
            "stage_label": status_blob.get("stage_label"),
            "stage_progress": status_blob.get("stage_progress"),
        }
    finally:
        db.close()


# ── Транскрипции ─────────────────────────────────────────────────────────────

def get_transcript_for_job(job_id: int) -> Optional[str]:
    """
    Найти транскрипцию завершённого job.

    Сначала смотрим в artifacts, сохранённых в job.payload["_result"],
    затем в note, связанной с job.
    """
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return None

        # 1. Быстрый путь: воркер кладёт final_transcript в payload._result
        payload = job.payload or {}
        transcript = payload.get("_result", {}).get("final_transcript")
        if transcript:
            return transcript

        # 2. Через note_id
        note_id = payload.get("note_id") or getattr(job, "note_id", None)
        if note_id:
            note = db.get(Note, note_id)
            if note and note.text:
                return note.text

        # 3. Ищем последнюю note по user_id отсортированную по времени
        # (воркер создаёт Note в default_finalize_note)
        note = (
            db.query(Note)
            .filter(Note.user_id == job.user_id)
            .order_by(Note.created_at.desc())
            .first()
        )
        if note and note.text:
            return note.text

        return None
    finally:
        db.close()
