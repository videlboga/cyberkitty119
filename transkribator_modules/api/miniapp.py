from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import shutil
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Literal
from threading import Lock
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from transkribator_modules.config import (
    BOT_TOKEN,
    logger,
    MAX_FILE_SIZE_MB,
    AUDIO_DIR,
    VIDEOS_DIR,
)
from transkribator_modules.db.database import (
    SessionLocal,
    UserService,
    NoteService,
    NoteGroupService,
    log_event,
    ReferralService,
)
from transkribator_modules.db.models import Note, NoteStatus, NoteVersion, Reminder, NoteGroup, User, PlanType, Event
from transkribator_modules.beta.agent_runtime import AgentSession, AgentUser, AgentResponse
from transkribator_modules.beta.note_utils import safe_parse_links, auto_finalize_note
from transkribator_modules.audio.extractor import extract_audio_from_video
from transkribator_modules.transcribe.transcriber_v4 import (
    compress_audio_for_api,
    transcribe_audio,
    format_transcript_with_llm,
    _basic_local_format,
)


TOKEN_TTL_SECONDS = int(os.getenv("MINIAPP_TOKEN_TTL", "86400"))  # 24 часа по умолчанию
SECRET_FALLBACK = os.getenv("MINIAPP_SECRET", BOT_TOKEN)
DEV_TIMEZONE = os.getenv("MINIAPP_DEV_TIMEZONE")
SUPER_ADMIN_IDS = {
    int(chunk.strip())
    for chunk in os.getenv("MINIAPP_SUPER_ADMIN_IDS", "648981358,176505507").split(",")
    if chunk.strip()
}
ALLOW_SUPER_ADMIN_UNVERIFIED = os.getenv("MINIAPP_ALLOW_SUPER_ADMIN_UNVERIFIED", "true").lower() in {
    "1",
    "true",
    "yes",
}

VIDEO_EXTENSIONS: Set[str] = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".webm",
    ".flv",
    ".wmv",
    ".m4v",
    ".3gp",
}

AUDIO_EXTENSIONS: Set[str] = {
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".m4a",
    ".wma",
    ".opus",
}

router = APIRouter(prefix="/miniapp", tags=["MiniApp"])


def get_db() -> Iterable[Session]:  # pragma: no cover - FastAPI dependency
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class MiniAppTokenManager:
    """Простейший HMAC-подписанный токен без внешних зависимостей."""

    @staticmethod
    def _secret() -> bytes:
        if not SECRET_FALLBACK:
            raise RuntimeError("MINIAPP_SECRET or BOT_TOKEN должен быть задан")
        return SECRET_FALLBACK.encode()

    @classmethod
    def sign(cls, payload: Dict[str, Any], ttl: int = TOKEN_TTL_SECONDS) -> str:
        data = payload.copy()
        now = int(time.time())
        data.setdefault("iat", now)
        data.setdefault("exp", now + ttl)
        blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        digest = hmac.new(cls._secret(), blob, hashlib.sha256).hexdigest()
        token = base64.urlsafe_b64encode(blob).decode().rstrip("=") + "." + digest
        return token

    @classmethod
    def verify(cls, token: str) -> Dict[str, Any]:
        try:
            blob_part, digest = token.split(".", 1)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise HTTPException(status_code=401, detail="Некорректный токен") from exc

        padded = blob_part + "=" * (-len(blob_part) % 4)
        try:
            blob = base64.urlsafe_b64decode(padded.encode())
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=401, detail="Некорректный токен") from exc

        expected_digest = hmac.new(cls._secret(), blob, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_digest, digest):
            raise HTTPException(status_code=401, detail="Недействительный токен")

        try:
            payload = json.loads(blob)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=401, detail="Некорректный токен") from exc

        exp = payload.get("exp")
        if exp and int(exp) < int(time.time()):
            raise HTTPException(status_code=401, detail="Токен истёк")
        return payload


def verify_telegram_init_data(raw_init_data: str) -> Dict[str, Any]:
    if not raw_init_data:
        raise HTTPException(status_code=400, detail="initData не передан")

    data = dict(parse_qsl(raw_init_data, strict_parsing=True))
    if "hash" not in data:
        raise HTTPException(status_code=400, detail="Отсутствует hash в initData")

    received_hash = data.get("hash")
    if received_hash is None:
        raise HTTPException(status_code=400, detail="Отсутствует hash в initData")

    data_for_hash = {k: v for k, v in data.items() if k != "hash"}
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_for_hash.items()))
    secret_key = hashlib.sha256(("WebAppData" + BOT_TOKEN).encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, calculated_hash):
        logger.warning(
            "MiniApp auth: hash mismatch",
            extra={"data": data_for_hash},
        )

    user_raw = data.get("user")
    if not user_raw:
        raise HTTPException(status_code=400, detail="initData не содержит user")

    try:
        user_payload = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Некорректный формат user в initData") from exc

    auth_date = data.get("auth_date")
    if auth_date and int(time.time()) - int(auth_date) > 86400:
        raise HTTPException(status_code=401, detail="initData истёк, запросите заново")

    data["user"] = user_payload
    return data


class AuthRequest(BaseModel):
    init_data: Optional[str] = Field(None, alias="initData")
    referral_code: Optional[str] = Field(None, alias="referralCode")
    utm_source: Optional[str] = Field(None, alias="utmSource")
    utm_medium: Optional[str] = Field(None, alias="utmMedium")
    utm_campaign: Optional[str] = Field(None, alias="utmCampaign")

    class Config:
        allow_population_by_field_name = True


class AuthResponseUser(BaseModel):
    id: int
    telegramId: int
    username: Optional[str]
    firstName: Optional[str]
    lastName: Optional[str]
    betaEnabled: bool
    timezone: Optional[str]
    plan: Optional[str]


class AuthResponse(BaseModel):
    token: str
    expiresIn: int
    user: AuthResponseUser


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("MiniApp get_current_user: missing bearer token")
        raise HTTPException(status_code=401, detail="Требуется авторизация")

    token = authorization[7:]
    payload = MiniAppTokenManager.verify(token)
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Некорректный токен (нет user_id)")

    user = db.query(User).filter(User.id == user_id).one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


def _map_status_to_front(note: Note) -> str:
    status = (note.status or "").lower()
    meta = note.meta or {}
    if status == "archived" or meta.get("archived"):
        return "archived"
    if status in {NoteStatus.APPROVED.value, NoteStatus.PROCESSED.value}:
        return "completed"
    if status in {NoteStatus.DRAFT.value, NoteStatus.BACKLOG.value, NoteStatus.NEW.value}:
        return "in_progress"
    return "active"


def _map_status_from_front(status: Optional[str]) -> Optional[str]:
    if not status or status == "all":
        return None
    status = status.lower()
    mapping = {
        "active": NoteStatus.INGESTED.value,
        "in_progress": NoteStatus.DRAFT.value,
        "completed": NoteStatus.APPROVED.value,
        "archived": "archived",
    }
    return mapping.get(status, status)


def _map_type_from_front(note_type: Optional[str]) -> Optional[str]:
    if not note_type or note_type == "all":
        return None
    return note_type.lower()


def _normalise_datetime(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.utcfromtimestamp(value).isoformat() + "Z"
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        candidate = candidate.replace("Z", "+00:00") if candidate.endswith("Z") else candidate
        try:
            return datetime.fromisoformat(candidate).isoformat()
        except ValueError:
            return value
    if isinstance(value, dict):
        for key in ("datetime", "date", "scheduled_at", "scheduled_for"):
            inner = value.get(key)
            if inner:
                normalised = _normalise_datetime(inner)
                if normalised:
                    return normalised
    return None


def _extract_scheduled_at(note: Note) -> Optional[str]:
    meta = note.meta or {}
    for key in (
        "scheduled_at",
        "scheduled_for",
        "due_at",
        "due_date",
        "reminder_at",
        "event_at",
        "calendar_at",
        "next_reminder",
    ):
        value = meta.get(key)
        scheduled = _normalise_datetime(value)
        if scheduled:
            return scheduled
    if isinstance(meta.get("reminder"), dict):
        scheduled = _normalise_datetime(meta["reminder"].get("at"))
        if scheduled:
            return scheduled
    return None


def _extract_note_tags(note: Note) -> Set[str]:
    tags_lower: Set[str] = set()
    for tag in note.tags or []:
        if tag:
            tags_lower.add(str(tag).strip().lower())
    meta = note.meta or {}
    meta_tags = meta.get("tags")
    if isinstance(meta_tags, list):
        for tag in meta_tags:
            if tag:
                tags_lower.add(str(tag).strip().lower())
    return tags_lower


def _build_group_maps(groups: Iterable[NoteGroup]) -> Tuple[Dict[int, NoteGroup], Dict[int, Set[str]]]:
    group_lookup: Dict[int, NoteGroup] = {}
    group_tags_map: Dict[int, Set[str]] = {}
    for group in groups:
        group_lookup[group.id] = group
        group_tags_map[group.id] = {str(tag).strip().lower() for tag in (group.tags or []) if tag}
    return group_lookup, group_tags_map


def _serialise_note(
    note: Note,
    group_lookup: Optional[Dict[int, NoteGroup]] = None,
    group_tags_map: Optional[Dict[int, Set[str]]] = None,
) -> Dict[str, Any]:
    meta = note.meta or {}
    created_at = note.created_at or note.ts or datetime.utcnow()
    updated_at = note.updated_at or created_at
    title = note.draft_title or meta.get("title") or meta.get("name")
    if not title:
        if note.summary:
            title = note.summary.split(". ")[0][:120]
        else:
            title = f"Заметка #{note.id}"
    content = note.draft_md or meta.get("markdown") or note.text
    summary = note.summary or meta.get("summary")
    color = meta.get("color")
    if not color and isinstance(meta.get("ui"), dict):
        color = meta["ui"].get("color")
    attachments: List[Dict[str, Any]] = []
    raw_attachments = meta.get("attachments")
    if isinstance(raw_attachments, list):
        for item in raw_attachments:
            if not isinstance(item, dict):
                continue
            attachments.append(
                {
                    "id": str(item.get("id") or item.get("file_id") or item.get("name") or len(attachments)),
                    "name": item.get("name") or item.get("filename") or "Вложение",
                    "type": item.get("type") or item.get("kind") or "file",
                    "url": item.get("url") or item.get("link"),
                }
            )
    groups = list(getattr(note, "groups", []) or [])
    if not groups and group_lookup and group_tags_map:
        note_tags = _extract_note_tags(note)
        if note_tags:
            seen_ids: Set[int] = set()
            for group_id, tags in group_tags_map.items():
                if not tags or group_id in seen_ids:
                    continue
                if note_tags & tags:
                    group = group_lookup.get(group_id)
                    if group:
                        groups.append(group)
                        seen_ids.add(group_id)

    scheduled_at = _extract_scheduled_at(note)
    if not scheduled_at:
        scheduled_at = created_at.isoformat()

    return {
        "id": note.id,
        "title": title,
        "summary": summary,
        "content": content,
        "tags": list(note.tags or []),
        "groupIds": [group.id for group in groups],
        "groups": [
            {
                "id": group.id,
                "name": group.name,
                "color": group.color,
            }
            for group in groups
        ],
        "status": _map_status_to_front(note),
        "type": (note.type_hint or meta.get("type") or "note"),
        "createdAt": created_at.isoformat(),
        "updatedAt": updated_at.isoformat(),
        "scheduledAt": scheduled_at,
        "color": color,
        "attachments": attachments,
        "source": note.source,
    }


class NoteAttachmentModel(BaseModel):
    id: str
    name: str
    type: str
    url: Optional[str]

class NoteGroupSummaryModel(BaseModel):
    id: int
    name: str
    color: Optional[str]


class NoteModel(BaseModel):
    id: int
    title: Optional[str]
    summary: Optional[str]
    content: Optional[str]
    tags: List[str]
    groupIds: List[int] = []
    groups: List[NoteGroupSummaryModel] = []
    status: Optional[str]
    type: Optional[str]
    createdAt: datetime
    updatedAt: datetime
    scheduledAt: Optional[str]
    color: Optional[str]
    attachments: List[NoteAttachmentModel] = []
    source: Optional[str]


class NotesListResponse(BaseModel):
    items: List[NoteModel]
    total: int
    page: int
    pageSize: int
    availableTags: List[str]


class NoteCreateRequest(BaseModel):
    title: Optional[str]
    summary: Optional[str]
    content: Optional[str]
    tags: List[str] = []
    status: Optional[str]
    type: Optional[str]
    scheduledAt: Optional[str]
    color: Optional[str]
    source: Optional[str] = "miniapp"
    groupIds: Optional[List[int]] = None


class NoteUpdateRequest(NoteCreateRequest):
    createVersion: bool = False


class NoteDetailResponse(BaseModel):
    note: NoteModel


class NoteVersionModel(BaseModel):
    version: int
    title: Optional[str]
    content: str
    createdAt: datetime
    meta: Dict[str, Any] = {}


class NoteHistoryResponse(BaseModel):
    versions: List[NoteVersionModel]


class BetaStatusResponse(BaseModel):
    enabled: bool


class EventKindStat(BaseModel):
    kind: str
    count: int


class EventEntry(BaseModel):
    ts: datetime
    kind: str
    userId: int
    telegramId: Optional[int]
    username: Optional[str]
    payload: Optional[dict]


class EventAnalyticsResponse(BaseModel):
    total: int
    hours: int
    byKind: List[EventKindStat]
    events: List[EventEntry]


class BetaStatusUpdateRequest(BaseModel):
    enabled: bool


class GroupModel(BaseModel):
    id: int
    name: str
    color: Optional[str]
    tags: List[str]
    noteCount: int
    updatedAt: datetime


class GroupCreateRequest(BaseModel):
    name: str
    color: Optional[str]
    tags: List[str] = []


class GroupUpdateRequest(BaseModel):
    name: Optional[str]
    color: Optional[str]
    tags: Optional[List[str]]


class GroupMergeRequest(BaseModel):
    ids: List[int]
    name: str
    color: Optional[str]


class GroupSuggestionModel(BaseModel):
    id: str
    name: str
    tags: List[str]
    confidence: float


class CalendarEventModel(BaseModel):
    id: str
    noteId: Optional[int]
    title: str
    timestamp: str
    status: str
    type: Optional[str]
    tags: List[str] = []


class CalendarResponse(BaseModel):
    events: List[CalendarEventModel]


class AgentHistoryItemModel(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentActiveNoteModel(BaseModel):
    id: int
    summary: Optional[str]
    title: Optional[str]
    type: Optional[str]


class AgentSessionResponse(BaseModel):
    messages: List[AgentHistoryItemModel]
    activeNote: Optional[AgentActiveNoteModel]
    suggestions: List[str]


class AgentMessageRequest(BaseModel):
    message: str
    noteId: Optional[int] = Field(None, alias="noteId")


class AgentActivateRequest(BaseModel):
    noteId: int = Field(..., alias="noteId")


class MiniAppAgentManager:
    def __init__(self) -> None:
        self._sessions: dict[int, AgentSession] = {}
        self._lock = Lock()

    def get_session(self, user: User) -> AgentSession:
        with self._lock:
            session = self._sessions.get(user.id)
            if session:
                return session
            telegram_id = int(user.telegram_id) if user.telegram_id else int(user.id)
            agent_user = AgentUser(
                telegram_id=telegram_id,
                db_id=int(user.id),
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            session = AgentSession(agent_user)
            self._sessions[user.id] = session
            return session

    def reset(self, user_id: int) -> None:
        with self._lock:
            self._sessions.pop(user_id, None)


agent_session_manager = MiniAppAgentManager()


def _coerce_suggestions(values: Optional[Iterable[str]]) -> List[str]:
    result: List[str] = []
    if not values:
        return result
    for item in values:
        if not item:
            continue
        candidate = str(item).strip()
        if candidate:
            result.append(candidate)
    return result


def _clean_user_message(content: str) -> str:
    lines = [line.rstrip() for line in (content or "").splitlines()]
    result: list[str] = []
    skip_prefixes = ("Сейчас (", "Сейчас:")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(prefix) for prefix in skip_prefixes):
            continue
        if stripped.lower().startswith("сообщение пользователя:"):
            stripped = stripped.partition(":")[2].strip()
            if stripped:
                result.append(stripped)
            continue
        result.append(stripped)
    return "\n".join(result).strip()


def _serialise_agent_history(session: AgentSession) -> List[AgentHistoryItemModel]:
    items: List[AgentHistoryItemModel] = []
    for entry in session.history:
        if not isinstance(entry, dict):
            continue
        role_raw = entry.get("role")
        content_raw = entry.get("content")
        content = str(content_raw or "").strip()
        if not content:
            continue
        role: Literal["user", "assistant"]
        if role_raw == "user":
            role = "user"
            content = _clean_user_message(content)
        elif role_raw == "assistant":
            role = "assistant"
        else:
            role = "assistant"
        items.append(AgentHistoryItemModel(role=role, content=content))
    return items


def _build_active_note_payload(session: AgentSession, db: Session) -> Optional[AgentActiveNoteModel]:
    note_id = session.active_note_id
    if not note_id:
        return None
    note_service = NoteService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != session.user_db_id:
        return None
    summary = session.active_note_summary or note.summary or note.draft_title
    title = note.draft_title or note.summary or None
    note_type = session.active_note_type or (note.type_hint or None)
    return AgentActiveNoteModel(
        id=note.id,
        summary=summary,
        title=title,
        type=note_type,
    )


def _build_agent_session_response(
    session: AgentSession,
    db: Session,
    *,
    suggestions: Optional[Iterable[str]] = None,
) -> AgentSessionResponse:
    return AgentSessionResponse(
        messages=_serialise_agent_history(session),
        activeNote=_build_active_note_payload(session, db),
        suggestions=_coerce_suggestions(list(suggestions) if suggestions is not None else []),
    )


def _activate_note_for_session(session: AgentSession, note_id: int, user: User, db: Session) -> None:
    note_service = NoteService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    links = safe_parse_links(note.links)
    session.set_active_note(note, links=links, local_artifact=False)


def _detect_media_type(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    raise HTTPException(status_code=400, detail="Неподдерживаемый формат файла")


def _ensure_file_size(path: Path) -> None:
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    size = path.stat().st_size if path.exists() else 0
    if size > max_bytes:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail="Файл слишком большой")


def _write_upload_file(upload: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    upload.file.seek(0)
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    _ensure_file_size(destination)
    return destination


async def _transcribe_media_file(media_path: Path, media_type: str) -> tuple[str, list[Path]]:
    cleanup: list[Path] = []
    source_path = media_path
    try:
        if media_type == "video":
            audio_path = AUDIO_DIR / f"{media_path.stem}_{uuid.uuid4().hex}.wav"
            success = await extract_audio_from_video(str(media_path), str(audio_path))
            if not success:
                raise HTTPException(status_code=500, detail="Не удалось извлечь аудио из видео.")
            cleanup.append(audio_path)
            source_path = audio_path

        processed_path_str = await compress_audio_for_api(str(source_path))
        processed_path = Path(processed_path_str)
        if processed_path != source_path:
            cleanup.append(processed_path)

        transcript = await transcribe_audio(processed_path_str)
        if not transcript or not transcript.strip():
            raise HTTPException(status_code=502, detail="Не удалось распознать речь в файле.")

        formatted = await format_transcript_with_llm(transcript)
        if not formatted:
            formatted = _basic_local_format(transcript)

        return formatted, cleanup
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("File transcription failed", extra={"path": str(media_path), "error": str(exc)})
        raise HTTPException(status_code=500, detail="Не удалось обработать файл.") from exc


def _cleanup_paths(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            continue


@router.post("/auth", response_model=AuthResponse)
def authenticate(
    request: AuthRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    user_service = UserService(db)
    raw_init = request.init_data
    header_init = None

    if not raw_init and http_request is not None:
        header_init = (
            http_request.headers.get("x-telegram-init-data")
            or http_request.headers.get("x-telegram-webapp-init-data")
        )
        if header_init:
            raw_init = header_init

    if not raw_init:
        logger.warning(
            "MiniApp auth: initData missing",
            extra={"has_header": bool(header_init)},
        )
        raise HTTPException(status_code=400, detail="initData не передан")

    payload = verify_telegram_init_data(raw_init)
    user_payload = payload["user"]
    telegram_id = user_payload.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="user.id не найден в initData")

    user = user_service.get_or_create_user(
        telegram_id=telegram_id,
        username=user_payload.get("username"),
        first_name=user_payload.get("first_name"),
        last_name=user_payload.get("last_name"),
    )
    is_new_user = bool(getattr(user, "_was_created", False))

    referral_code = request.referral_code
    if not referral_code and http_request is not None:
        referral_code = http_request.query_params.get("ref")
    referral_code = referral_code.strip() if referral_code else None

    utm_source = request.utm_source or (
        http_request.query_params.get("utm_source") if http_request is not None else None
    )
    utm_medium = request.utm_medium or (
        http_request.query_params.get("utm_medium") if http_request is not None else None
    )
    utm_campaign = request.utm_campaign or (
        http_request.query_params.get("utm_campaign") if http_request is not None else None
    )
    timezone = (
        payload.get("timezone")
        or payload.get("user", {}).get("time_zone")
        or DEV_TIMEZONE
    )
    if timezone:
        try:
            user_service.set_timezone(user, timezone)
        except Exception:
            logger.debug("Failed to set timezone", exc_info=True)

    referral_bonus_applied = False
    if referral_code:
        referral_service = ReferralService(db)
        try:
            referral_service.record_referral_visit(referral_code, telegram_id)
        except Exception:
            logger.debug("Failed to record referral visit", exc_info=True)

        if is_new_user:
            try:
                activation = referral_service.apply_referral_welcome_bonus(user)
                referral_bonus_applied = activation is not None
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to apply referral welcome bonus",
                    extra={
                        "user_id": user.id,
                        "telegram_id": telegram_id,
                        "referral_code": referral_code,
                        "error": str(exc),
                    },
                )

    logger.info(
        "MiniApp auth: success",
        extra={
            "telegram_id": telegram_id,
            "username": user_payload.get("username"),
            "has_timezone": bool(timezone),
            "beta_enabled": bool(user.beta_enabled),
            "user_id": user.id,
            "referral_code": referral_code,
            "referral_bonus_applied": referral_bonus_applied,
        },
    )
    try:
        log_event(
            user,
            "miniapp_auth",
            {
                "username": user.username,
                "timezone": timezone,
                "via_header": bool(header_init),
                "referral_code": referral_code,
                "referral_bonus_applied": referral_bonus_applied,
                "utm_source": utm_source,
                "utm_medium": utm_medium,
                "utm_campaign": utm_campaign,
                "is_new_user": is_new_user,
            },
        )
    except Exception:
        logger.debug("Failed to log miniapp auth", exc_info=True)

    token = MiniAppTokenManager.sign({"user_id": user.id, "telegram_id": user.telegram_id})
    response_user = AuthResponseUser(
        id=user.id,
        telegramId=user.telegram_id,
        username=user.username,
        firstName=user.first_name,
        lastName=user.last_name,
        betaEnabled=bool(user.beta_enabled),
        timezone=user.timezone,
        plan=user.current_plan,
    )
    return AuthResponse(token=token, expiresIn=TOKEN_TTL_SECONDS, user=response_user)


@router.get("/user/beta", response_model=BetaStatusResponse)
def get_beta_status(
    current_user: User = Depends(get_current_user),
) -> BetaStatusResponse:
    enabled = bool(current_user.beta_enabled)
    logger.info(
        "MiniApp beta status fetched",
        extra={
            "user_id": current_user.id,
            "telegram_id": current_user.telegram_id,
            "beta_enabled": enabled,
        },
    )
    try:
        log_event(current_user, "miniapp_beta_status", {"enabled": enabled})
    except Exception:
        logger.debug("Failed to log beta status fetch", exc_info=True)
    return BetaStatusResponse(enabled=enabled)


@router.post("/user/beta", response_model=BetaStatusResponse)
def update_beta_status(
    payload: BetaStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BetaStatusResponse:
    user_service = UserService(db)

    user_service.set_beta_enabled(current_user, payload.enabled)
    db.refresh(current_user)
    enabled = bool(current_user.beta_enabled)
    logger.info(
        "MiniApp beta status updated",
        extra={
            "user_id": current_user.id,
            "telegram_id": current_user.telegram_id,
            "beta_enabled": enabled,
        },
    )
    try:
        log_event(current_user, "miniapp_beta_update", {"enabled": enabled})
    except Exception:
        logger.debug("Failed to log beta update", exc_info=True)
    return BetaStatusResponse(enabled=enabled)


@router.get("/agent/session", response_model=AgentSessionResponse)
def get_agent_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSessionResponse:
    session = agent_session_manager.get_session(current_user)
    try:
        log_event(
            current_user,
            "miniapp_agent_session_fetch",
            {"history_len": len(session.history)},
        )
    except Exception:
        logger.debug("Failed to log agent session fetch", exc_info=True)
    return _build_agent_session_response(session, db)


@router.post("/agent/activate", response_model=AgentSessionResponse)
def activate_agent_note(
    payload: AgentActivateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSessionResponse:
    session = agent_session_manager.get_session(current_user)
    _activate_note_for_session(session, payload.noteId, current_user, db)
    try:
        log_event(current_user, "miniapp_agent_activate_note", {"note_id": payload.noteId})
    except Exception:
        logger.debug("Failed to log agent note activation", exc_info=True)
    return _build_agent_session_response(session, db)


@router.post("/agent/messages", response_model=AgentSessionResponse)
async def send_agent_message(
    payload: AgentMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSessionResponse:
    text = (payload.message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message не может быть пустым")

    session = agent_session_manager.get_session(current_user)
    if payload.noteId:
        _activate_note_for_session(session, payload.noteId, current_user, db)
    try:
        log_event(
            current_user,
            "miniapp_agent_message",
            {"note_id": payload.noteId, "message_length": len(text)},
        )
    except Exception:
        logger.debug("Failed to log agent message", exc_info=True)

    response: AgentResponse = await session.handle_user_message(text)
    return _build_agent_session_response(session, db, suggestions=response.suggestions)


@router.post("/agent/upload", response_model=AgentSessionResponse)
async def upload_agent_media(
    file: UploadFile = File(...),
    note_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AgentSessionResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Файл не передан")

    media_type = _detect_media_type(file.filename)
    target_dir = VIDEOS_DIR if media_type == "video" else AUDIO_DIR
    unique_name = f"miniapp_{uuid.uuid4().hex}{Path(file.filename).suffix.lower()}"
    stored_path = target_dir / unique_name
    note_id_value: Optional[int] = None
    if note_id:
        try:
            note_id_value = int(note_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Некорректный идентификатор заметки") from exc

    cleanup_paths: list[Path] = []
    try:
        saved_path = _write_upload_file(file, stored_path)
        cleanup_paths.append(saved_path)
        transcript, extra_cleanup = await _transcribe_media_file(saved_path, media_type)
        cleanup_paths.extend(extra_cleanup)

        note_service = NoteService(db)
        note = note_service.create_note(
            user=current_user,
            text=transcript,
            source="miniapp-upload",
            status=NoteStatus.INGESTED.value,
        )
        try:
            log_event(
                current_user,
                "miniapp_agent_upload",
                {
                    "note_id": note.id,
                    "media_type": media_type,
                    "filename": file.filename,
                },
            )
        except Exception:
            logger.debug("Failed to log agent upload", exc_info=True)

        try:
            await auto_finalize_note(note.id)
            db.refresh(note)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "auto_finalize_note failed for upload",
                extra={"note_id": note.id, "error": str(exc)},
            )

        session = agent_session_manager.get_session(current_user)
        session.set_active_note(note, local_artifact=False)
        payload = {
            "note_id": note.id,
            "text": transcript,
            "summary": note.summary,
            "created": True,
            "source": "miniapp-upload",
        }
        response = await session.handle_ingest(payload)
        return _build_agent_session_response(session, db, suggestions=response.suggestions)
    finally:
        _cleanup_paths(cleanup_paths)


@router.get("/analytics/events", response_model=EventAnalyticsResponse)
def events_analytics(
    hours: int = Query(6, ge=1, le=168),
    db: Session = Depends(get_db),
) -> EventAnalyticsResponse:
    since = datetime.utcnow() - timedelta(hours=hours)
    base_query = db.query(Event).filter(Event.ts >= since)
    total = base_query.count()

    kind_counts = (
        db.query(Event.kind, func.count(Event.id))
        .filter(Event.ts >= since)
        .group_by(Event.kind)
        .all()
    )

    events = (
        db.query(Event, User)
        .join(User, User.id == Event.user_id)
        .filter(Event.ts >= since)
        .order_by(Event.ts.desc())
        .limit(200)
        .all()
    )

    entries: List[EventEntry] = []
    for event, user in events:
        payload_dict = None
        if event.payload:
            try:
                payload_dict = json.loads(event.payload)
            except Exception:
                payload_dict = {"raw": event.payload}
        entries.append(
            EventEntry(
                ts=event.ts,
                kind=event.kind,
                userId=user.id,
                telegramId=user.telegram_id,
                username=user.username,
                payload=payload_dict,
            )
        )

    return EventAnalyticsResponse(
        total=total,
        hours=hours,
        byKind=[EventKindStat(kind=row[0], count=row[1]) for row in kind_counts],
        events=entries,
    )


def _filter_notes(
    notes: List[Note],
    *,
    status: Optional[str],
    note_type: Optional[str],
    group_id: Optional[int],
    tags: List[str],
    search: Optional[str],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
    group_tags_map: Optional[Dict[int, Set[str]]] = None,
) -> List[Note]:
    filtered: List[Note] = []
    status_db = _map_status_from_front(status)
    type_db = _map_type_from_front(note_type)
    requested_tags = {tag.lower() for tag in tags if tag}
    search_lower = search.lower() if search else None
    tag_cache: Dict[int, Set[str]] = {}

    for note in notes:
        if status_db and not _status_matches(note.status, status_db):
            continue
        if type_db and (note.type_hint or "").lower() != type_db:
            continue
        if group_id:
            note_groups = getattr(note, "groups", []) or []
            direct_match = any(group.id == group_id for group in note_groups)
            tag_match = False
            if not direct_match and group_tags_map and group_id in group_tags_map:
                if note.id not in tag_cache:
                    tag_cache[note.id] = _extract_note_tags(note)
                note_tags = tag_cache[note.id]
                tag_match = bool(note_tags and note_tags & group_tags_map[group_id])
            if not direct_match and not tag_match:
                continue
        if requested_tags:
            note_tags = {t.lower() for t in (note.tags or [])}
            if not requested_tags.issubset(note_tags):
                continue
        if date_from and (note.ts or note.created_at or datetime.utcnow()) < date_from:
            continue
        if date_to and (note.ts or note.created_at or datetime.utcnow()) > date_to:
            continue
        if search_lower and not _note_matches_search(note, search_lower):
            continue
        filtered.append(note)
    return filtered


def _status_matches(current_status: Optional[str], expected: str) -> bool:
    current = (current_status or "").lower()
    if expected == "archived":
        return current == "archived"
    if expected == NoteStatus.INGESTED.value:
        return current in {NoteStatus.INGESTED.value, "active"}
    if expected == NoteStatus.DRAFT.value:
        return current in {NoteStatus.DRAFT.value, NoteStatus.BACKLOG.value, "in_progress"}
    if expected == NoteStatus.APPROVED.value:
        return current in {NoteStatus.APPROVED.value, NoteStatus.PROCESSED.value, "completed"}
    return current == expected


def _note_matches_search(note: Note, needle: str) -> bool:
    haystacks = [
        note.summary or "",
        note.text or "",
        note.draft_md or "",
        note.draft_title or "",
    ]
    meta = note.meta or {}
    for key in ("summary", "title", "markdown", "description"):
        value = meta.get(key)
        if isinstance(value, str):
            haystacks.append(value)
    combined = "\n".join(haystacks).lower()
    return needle in combined


def _resolve_period(period: Optional[str], date_from: Optional[str], date_to: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    if period == "custom":
        start = _parse_datetime_safe(date_from)
        end = _parse_datetime_safe(date_to)
        return start, end
    today = datetime.utcnow().date()
    if period == "today":
        start = datetime.combine(today, datetime.min.time())
        end = datetime.combine(today, datetime.max.time())
        return start, end
    if period == "week":
        end = datetime.utcnow()
        start = end - timedelta(days=7)
        return start, end
    if period == "month":
        start = datetime.combine(today.replace(day=1), datetime.min.time())
        if start.month == 12:
            end = datetime(start.year + 1, 1, 1)
        else:
            end = datetime(start.year, start.month + 1, 1)
        return start, end
    return None, None


def _parse_datetime_safe(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    candidate = candidate.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Некорректный формат даты: {value}") from exc


@router.get("/notes", response_model=NotesListResponse)
def list_notes(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    period: Optional[str] = Query("week"),
    status: Optional[str] = Query("all"),
    note_type: Optional[str] = Query("all", alias="type"),
    tags: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    group_id: Optional[int] = Query(None, alias="groupId"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotesListResponse:
    note_service = NoteService(db)
    group_service = NoteGroupService(db)
    notes = note_service.list_user_notes(current_user)
    groups = group_service.list_groups(current_user.id)
    group_lookup, group_tags_map = _build_group_maps(groups)
    tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else []
    start_dt, end_dt = _resolve_period(period, date_from, date_to)
    filtered = _filter_notes(
        notes,
        status=status,
        note_type=note_type,
        group_id=group_id,
        tags=tags_list,
        search=search,
        date_from=start_dt,
        date_to=end_dt,
        group_tags_map=group_tags_map,
    )
    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = filtered[start:end]
    available_tags = sorted({tag for note in notes for tag in (note.tags or [])})
    items = [NoteModel(**_serialise_note(note, group_lookup, group_tags_map)) for note in paginated]
    return NotesListResponse(items=items, total=total, page=page, pageSize=page_size, availableTags=available_tags)


@router.post("/notes", response_model=NoteDetailResponse, status_code=201)
async def create_note(
    payload: NoteCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteDetailResponse:
    note_service = NoteService(db)
    group_service = NoteGroupService(db)
    text = payload.content or payload.summary or payload.title or ""
    note = note_service.create_note(
        user=current_user,
        text=text,
        source=payload.source or "miniapp",
        summary=payload.summary,
        tags=payload.tags,
        draft_title=payload.title,
        draft_md=payload.content,
        meta=_build_note_meta(payload),
        status=_map_status_from_front(payload.status) or NoteStatus.DRAFT.value,
        type_hint=_map_type_from_front(payload.type),
        create_version=bool(payload.content),
        group_ids=payload.groupIds or [],
    )
    await auto_finalize_note(note.id)
    db.refresh(note)
    groups = group_service.list_groups(current_user.id)
    group_lookup, group_tags_map = _build_group_maps(groups)
    serialised = NoteModel(**_serialise_note(note, group_lookup, group_tags_map))
    try:
        log_event(
            current_user,
            "miniapp_note_created",
            {
                "note_id": note.id,
                "has_content": bool(payload.content),
                "status": serialised.status,
                "tags": payload.tags or [],
            },
        )
    except Exception:
        logger.debug("Failed to log note creation", exc_info=True)
    return NoteDetailResponse(note=serialised)


def _build_note_meta(payload: NoteCreateRequest) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if payload.color:
        meta["color"] = payload.color
    if payload.scheduledAt:
        meta["scheduled_at"] = payload.scheduledAt
    return meta


@router.get("/notes/{note_id}", response_model=NoteDetailResponse)
def get_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteDetailResponse:
    note_service = NoteService(db)
    group_service = NoteGroupService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    groups = group_service.list_groups(current_user.id)
    group_lookup, group_tags_map = _build_group_maps(groups)
    return NoteDetailResponse(note=NoteModel(**_serialise_note(note, group_lookup, group_tags_map)))


@router.patch("/notes/{note_id}", response_model=NoteDetailResponse)
async def update_note(
    note_id: int,
    payload: NoteUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteDetailResponse:
    note_service = NoteService(db)
    group_service = NoteGroupService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Заметка не найдена")

    meta_updates = _build_note_meta(payload)
    if payload.createVersion and payload.content:
        note_service.add_version(note, markdown=payload.content, title=payload.title, meta=meta_updates or None)

    note = note_service.update_note_metadata(
        note,
        summary=payload.summary,
        tags=payload.tags,
        draft_title=payload.title,
        draft_md=payload.content,
        meta=meta_updates or None,
        status=_map_status_from_front(payload.status),
        type_hint=_map_type_from_front(payload.type),
    )
    if payload.groupIds is not None:
        note = note_service.set_note_groups(note, payload.groupIds)
    await auto_finalize_note(note.id)
    db.refresh(note)
    groups = group_service.list_groups(current_user.id)
    group_lookup, group_tags_map = _build_group_maps(groups)
    serialised = NoteModel(**_serialise_note(note, group_lookup, group_tags_map))
    try:
        log_event(
            current_user,
            "miniapp_note_updated",
            {
                "note_id": note.id,
                "status": serialised.status,
                "tags": payload.tags or note.tags or [],
            },
        )
    except Exception:
        logger.debug("Failed to log note update", exc_info=True)
    return NoteDetailResponse(note=serialised)


@router.delete("/notes/{note_id}", status_code=204)
def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    note_service = NoteService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Заметка не найдена")
    note_service.mark_archived(note)
    return Response(status_code=204)


@router.get("/notes/{note_id}/history", response_model=NoteHistoryResponse)
def get_note_history(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NoteHistoryResponse:
    note_service = NoteService(db)
    note = note_service.get_note(note_id)
    if not note or note.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Заметка не найдена")

    versions: List[NoteVersion] = list(note.versions or [])
    items = [
        NoteVersionModel(
            version=version.version,
            title=version.title,
            content=version.markdown,
            createdAt=version.created_at,
            meta=version.meta or {},
        )
        for version in sorted(versions, key=lambda item: item.version)
    ]
    return NoteHistoryResponse(versions=items)


@router.get("/groups", response_model=List[GroupModel])
def list_groups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[GroupModel]:
    group_service = NoteGroupService(db)
    note_service = NoteService(db)
    groups = group_service.list_groups(current_user.id)
    notes = note_service.list_user_notes(current_user)
    _, group_tags_map = _build_group_maps(groups)
    note_counts = _calculate_group_counts(groups, notes, group_tags_map)
    return [
        GroupModel(
            id=group.id,
            name=group.name,
            color=group.color,
            tags=list(group.tags or []),
            noteCount=note_counts.get(group.id, 0),
            updatedAt=group.updated_at or group.created_at,
        )
        for group in groups
    ]


def _calculate_group_counts(
    groups: List[NoteGroup],
    notes: List[Note],
    group_tags_map: Optional[Dict[int, Set[str]]] = None,
) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    note_map = {note.id: note for note in notes}
    tag_cache: Dict[int, Set[str]] = {}
    for group in groups:
        direct_count = len(getattr(group, "notes", []) or [])
        if direct_count:
            counts[group.id] = direct_count
            continue
        tags = group_tags_map.get(group.id) if group_tags_map else None

        def note_matches(target_note: Note) -> bool:
            note_groups = getattr(target_note, "groups", []) or []
            if any(g.id == group.id for g in note_groups):
                return True
            if not tags:
                return False
            if target_note.id not in tag_cache:
                tag_cache[target_note.id] = _extract_note_tags(target_note)
            return bool(tag_cache[target_note.id] & tags)

        counts[group.id] = sum(1 for note in note_map.values() if note_matches(note))
    return counts


@router.post("/groups", response_model=GroupModel, status_code=201)
def create_group(
    payload: GroupCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupModel:
    group_service = NoteGroupService(db)
    note_service = NoteService(db)
    group = group_service.create_group(current_user.id, payload.name.strip(), payload.tags, payload.color)
    _, group_tags_map = _build_group_maps([group])
    note_counts = _calculate_group_counts([group], note_service.list_user_notes(current_user), group_tags_map)
    return GroupModel(
        id=group.id,
        name=group.name,
        color=group.color,
        tags=list(group.tags or []),
        noteCount=note_counts.get(group.id, 0),
        updatedAt=group.updated_at or group.created_at,
    )


@router.patch("/groups/{group_id}", response_model=GroupModel)
def update_group(
    group_id: int,
    payload: GroupUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupModel:
    group_service = NoteGroupService(db)
    note_service = NoteService(db)
    group = group_service.get_group(current_user.id, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    group = group_service.update_group(group, name=payload.name, tags=payload.tags, color=payload.color)
    _, group_tags_map = _build_group_maps([group])
    note_counts = _calculate_group_counts([group], note_service.list_user_notes(current_user), group_tags_map)
    return GroupModel(
        id=group.id,
        name=group.name,
        color=group.color,
        tags=list(group.tags or []),
        noteCount=note_counts.get(group.id, 0),
        updatedAt=group.updated_at or group.created_at,
    )


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    group_service = NoteGroupService(db)
    group = group_service.get_group(current_user.id, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    group_service.delete_group(group)
    return Response(status_code=204)


@router.post("/groups/merge", response_model=GroupModel)
def merge_groups(
    payload: GroupMergeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupModel:
    if len(payload.ids) < 2:
        raise HTTPException(status_code=400, detail="Для объединения необходимо минимум две группы")
    group_service = NoteGroupService(db)
    note_service = NoteService(db)
    try:
        merged = group_service.merge_groups(current_user.id, payload.ids, name=payload.name.strip(), color=payload.color)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _, group_tags_map = _build_group_maps([merged])
    note_counts = _calculate_group_counts([merged], note_service.list_user_notes(current_user), group_tags_map)
    return GroupModel(
        id=merged.id,
        name=merged.name,
        color=merged.color,
        tags=list(merged.tags or []),
        noteCount=note_counts.get(merged.id, 0),
        updatedAt=merged.updated_at or merged.created_at,
    )


@router.get("/groups/suggestions", response_model=List[GroupSuggestionModel])
def group_suggestions(
    limit: int = Query(5, ge=1, le=10),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[GroupSuggestionModel]:
    group_service = NoteGroupService(db)
    note_service = NoteService(db)
    groups = group_service.list_groups(current_user.id)
    notes = note_service.list_user_notes(current_user)
    existing_tags = {tag.lower() for group in groups for tag in (group.tags or [])}
    counter: Counter[str] = Counter()
    for note in notes:
        for tag in note.tags or []:
            counter[tag.lower()] += 1
    suggestions: List[GroupSuggestionModel] = []
    max_count = counter.most_common(1)[0][1] if counter else 1
    for tag, count in counter.most_common():
        if tag in existing_tags:
            continue
        if len(tag) < 3 or count < 2:
            continue
        confidence = 0.4 + (count / max_count) * 0.5
        suggestions.append(
            GroupSuggestionModel(
                id=f"suggest-{tag}",
                name=tag.title(),
                tags=[tag],
                confidence=round(min(confidence, 0.99), 2),
            )
        )
        if len(suggestions) >= limit:
            break
    return suggestions


@router.get("/calendar", response_model=CalendarResponse)
def calendar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarResponse:
    note_service = NoteService(db)
    notes = note_service.list_user_notes(current_user)
    events: List[CalendarEventModel] = []
    for note in notes:
        scheduled = _extract_scheduled_at(note)
        if not scheduled:
            continue
        events.append(
            CalendarEventModel(
                id=f"note-{note.id}",
                noteId=note.id,
                title=note.draft_title or note.summary or f"Заметка #{note.id}",
                timestamp=scheduled,
                status=_map_status_to_front(note),
                type=note.type_hint,
                tags=list(note.tags or []),
            )
        )

    reminder_rows: List[Reminder] = (
        db.query(Reminder)
        .filter(Reminder.user_id == current_user.id, Reminder.fire_ts.isnot(None))
        .order_by(Reminder.fire_ts.asc())
        .all()
    )
    for reminder in reminder_rows:
        payload = {}
        try:
            payload = json.loads(reminder.payload or "{}")
        except json.JSONDecodeError:
            pass
        events.append(
            CalendarEventModel(
                id=f"reminder-{reminder.id}",
                noteId=payload.get("note_id"),
                title=payload.get("title") or "Напоминание",
                timestamp=(reminder.fire_ts or datetime.utcnow()).isoformat(),
                status=payload.get("status") or "in_progress",
                type=payload.get("type"),
                tags=payload.get("tags") or [],
            )
        )
    events.sort(key=lambda event: event.timestamp)
    return CalendarResponse(events=events)


def create_miniapp_app() -> FastAPI:
    app = FastAPI(title="CyberKitty MiniApp API", version="1.0.0")
    origins = os.getenv("MINIAPP_ALLOWED_ORIGINS")
    allow_origins = [origin.strip() for origin in origins.split(",") if origin.strip()] if origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    app.include_router(router)

    @app.get("/health")
    def health() -> Dict[str, str]:  # pragma: no cover - trivial
        return {"status": "ok"}

    return app


app = create_miniapp_app()


__all__ = ["router", "create_miniapp_app", "app"]
