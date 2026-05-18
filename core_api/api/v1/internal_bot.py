from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy.orm import Session

from transkribator_modules.api.miniapp import get_db
from transkribator_modules.db.user_service import get_or_create_user_by_provider
from transkribator_modules.db.models import (
    ProcessingJob, User, Note, NoteQASession, NoteQAMessage
)

from core_api.api.v1.dependencies import verify_service_token

router = APIRouter(
    tags=["Internal Bot Compatibility"],
    dependencies=[Depends(verify_service_token)],
)

class EnsureUserRequest(BaseModel):
    telegram_id: int

@router.post("/ensure_user", summary="Ensure user exists")
def ensure_user(req: EnsureUserRequest):
    user_id = get_or_create_user_by_provider(
        provider="telegram",
        external_id=str(req.telegram_id),
        username=str(req.telegram_id),
    )
    return {"user_id": user_id}

@router.get("/user_id_by_tg/{telegram_id}")
def get_user_id_tg(telegram_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    return {"user_id": user.id if user else None}

@router.get("/jobs/{job_id}")
def get_job_row(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return {"job": None}
    
    payload = job.payload or {}
    status_blob = payload.get("_status") if isinstance(payload, dict) else {}
    if not isinstance(status_blob, dict): 
        status_blob = {}
        
    stage_window = None
    window_val = status_blob.get("stage_window")
    if isinstance(window_val, (list, tuple)) and len(window_val) == 2:
        try:
            stage_window = [int(window_val[0]), int(window_val[1])]
        except (TypeError, ValueError):
            pass
            
    return {"job": {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "payload": payload,
        "stage": status_blob.get("stage"),
        "stage_label": status_blob.get("stage_label"),
        "stage_progress": status_blob.get("stage_progress"),
        "stage_window": stage_window,
    }}

@router.get("/jobs/{job_id}/transcript")
def get_transcript_for_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return {"transcript": None}

    payload = job.payload or {}
    result_blob = payload.get("_result", {}) or {}
    transcript = result_blob.get("final_transcript") or result_blob.get("raw_transcript")
    if transcript:
        return {"transcript": transcript}

    note_id = payload.get("note_id") or getattr(job, "note_id", None)
    if note_id:
        note = db.get(Note, note_id)
        if note and note.text:
            return {"transcript": note.text}

    note = (
        db.query(Note)
        .filter(Note.user_id == job.user_id)
        .order_by(Note.created_at.desc())
        .first()
    )
    if note and note.text:
        return {"transcript": note.text}

    return {"transcript": None}

@router.get("/jobs/{job_id}/note")
def get_note_for_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        return {"note": None}

    payload = job.payload or {}
    status_blob = payload.get("_result") or {}
    note_id = (getattr(job, "note_id", None) or status_blob.get("note_id") or payload.get("note_id"))
    
    if not note_id:
        return {"note": None}
        
    note = db.get(Note, note_id)
    if not note:
        return {"note": None}
        
    tags = note.tags or []
    if isinstance(tags, str):
        try:
            import json as _json
            parsed = _json.loads(tags)
            tags = parsed if isinstance(parsed, list) else []
        except Exception:
            tags = []
            
    links = note.links or {}
    if isinstance(links, str):
        try:
            import json as _json
            parsed_links = _json.loads(links)
            links = parsed_links if isinstance(parsed_links, dict) else {}
        except Exception:
            links = {}

    return {"note": {
        "id": note.id,
        "user_id": note.user_id,
        "title": (note.draft_title or "").strip() or (note.summary or "").strip() or f"Заметка #{note.id}",
        "summary": (note.summary or "").strip(),
        "text": (note.text or "").strip(),
        "status": note.status,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "tags": [str(tag).strip() for tag in tags if str(tag).strip()],
        "links": {str(k).strip(): str(v).strip() for k, v in links.items() if str(k).strip()},
    }}

class EnsureQARequest(BaseModel):
    user_id: int
    note: Dict[str, Any]
    context_snapshot: str

@router.post("/qa/ensure")
def ensure_note_qa_session(req: EnsureQARequest, db: Session = Depends(get_db)):
    session = (
        db.query(NoteQASession)
        .filter(
            NoteQASession.user_id == req.user_id,
            NoteQASession.note_id == req.note["id"],
        )
        .first()
    )
    now = datetime.utcnow()
    tags = req.note.get("tags") or []
    if isinstance(tags, (set, tuple)):
        tags = list(tags)
    summary = req.note.get("summary") or ""
    title = req.note.get("title") or f"Заметка #{req.note['id']}"
    
    if session is None:
        session = NoteQASession(
            user_id=req.user_id,
            note_id=req.note["id"],
            title=title[:255],
            summary=summary,
            tags=list(tags),
            context_snapshot=req.context_snapshot,
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        db.add(session)
    else:
        session.title = title[:255]
        session.summary = summary
        session.tags = list(tags)
        session.context_snapshot = req.context_snapshot
        session.updated_at = now
        
    db.commit()
    db.refresh(session)
    return {"session_id": session.id}

@router.get("/qa/session_id")
def get_note_qa_session_for_user(user_id: int, note_id: int, db: Session = Depends(get_db)):
    session = (
        db.query(NoteQASession)
        .filter(
            NoteQASession.user_id == user_id,
            NoteQASession.note_id == note_id,
        )
        .first()
    )
    return {"session_id": session.id if session else None}

class QAMessageRequest(BaseModel):
    session_id: int
    role: str
    content: str

@router.post("/qa/message")
def record_note_qa_message(req: QAMessageRequest, db: Session = Depends(get_db)):
    session = db.get(NoteQASession, req.session_id)
    if session is None:
        return {"status": "error", "message": "session not found"}
        
    message = NoteQAMessage(
        session_id=req.session_id,
        role=req.role,
        content=req.content,
        created_at=datetime.utcnow(),
    )
    session.total_messages = (session.total_messages or 0) + 1
    session.last_message_at = datetime.utcnow()
    db.add(message)
    db.commit()
    return {"status": "ok"}

@router.get("/qa/payload/{session_id}")
def fetch_note_qa_session_payload(session_id: int, history_limit: int = 30, db: Session = Depends(get_db)):
    session = db.get(NoteQASession, session_id)
    if session is None:
        return {"payload": None}
        
    query = (
        db.query(NoteQAMessage)
        .filter(NoteQAMessage.session_id == session_id)
        .order_by(NoteQAMessage.created_at.desc(), NoteQAMessage.id.desc())
        .limit(history_limit)
    )
    rows = query.all()
    messages = [
        {"role": row.role, "content": row.content, "created_at": row.created_at}
        for row in reversed(rows)
    ]
    return {"payload": {
        "id": session.id,
        "note_id": session.note_id,
        "user_id": session.user_id,
        "title": session.title,
        "summary": session.summary,
        "tags": list(session.tags or []),
        "context_snapshot": session.context_snapshot or "",
        "messages": messages,
    }}

class EnqueueMediaRequest(BaseModel):
    user_id: int
    telegram_id: int
    file_id: str
    audio_path: str
    message_id: int

@router.post("/jobs/enqueue_media")
def enqueue_media(req: EnqueueMediaRequest):
    from transkribator_modules.jobs.media import MediaJobPayload, enqueue_media_job
    payload = MediaJobPayload(
        file_id=req.file_id,
        message_id=req.message_id,
        extra={
            "audio_path": req.audio_path,
            "telegram_id": req.telegram_id,
        },
    )
    job = enqueue_media_job(
        user_id=req.user_id,
        payload=payload,
    )
    return {"job_id": job.id}
