import os

from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    JSON,
    Table,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from enum import Enum

try:  # Optional pgvector support (PostgreSQL-only)
    from pgvector.sqlalchemy import Vector as PgVector
except ImportError:  # pragma: no cover - pgvector unavailable (e.g. sqlite tests)
    PgVector = None

try:
    from sqlalchemy.dialects.postgresql import JSONB  # type: ignore
except Exception:  # pragma: no cover - PostgreSQL driver not available
    JSONB = None

Base = declarative_base()


def _embedding_column_type():
    """Return appropriate SQLAlchemy column type for note chunk embeddings."""

    database_url = os.getenv('DATABASE_URL', '')
    use_pgvector = bool(PgVector) and database_url.startswith('postgresql')
    if use_pgvector:
        return PgVector(1536)
    return Text


def _json_column_type():
    """Return JSON/JSONB type depending on backend."""

    database_url = os.getenv('DATABASE_URL', '')
    if JSONB and database_url.startswith('postgresql'):
        return JSONB
    return JSON


JSONType = _json_column_type()


class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    BETA = "beta"
    UNLIMITED = "unlimited"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    # Текущий план
    current_plan = Column(String, default=PlanType.FREE)
    plan_expires_at = Column(DateTime, nullable=True)

    # Статистика использования
    total_minutes_transcribed = Column(Float, default=0.0)
    minutes_used_this_month = Column(Float, default=0.0)
    last_reset_date = Column(DateTime, default=datetime.utcnow)

    # Статистика генераций (для бесплатного тарифа)
    total_generations = Column(Integer, default=0)
    generations_used_this_month = Column(Integer, default=0)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    beta_enabled = Column(Boolean, default=False)
    google_connected = Column(Boolean, default=False)
    timezone = Column(String, nullable=True)

    # Связи
    transactions = relationship("Transaction", back_populates="user")
    transcriptions = relationship("Transcription", back_populates="user")
    notes = relationship("Note", back_populates="user")
    note_groups = relationship("NoteGroup", back_populates="user", cascade="all, delete-orphan")


class UserIdentifier(Base):
        """Link external provider identifiers to internal users.

        Examples:
            provider='telegram', external_id='123456789'
            provider='max', external_id='user-abc-123'
        """

        __tablename__ = "user_identifiers"

        id = Column(Integer, primary_key=True, index=True)
        user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
        provider = Column(String, nullable=False)
        external_id = Column(String, nullable=False)

        created_at = Column(DateTime, default=datetime.utcnow)

        __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_provider_external_id"),)

        # optional relationship back to user (weak)
        # user = relationship("User")

class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)  # free, basic, pro, unlimited
    display_name = Column(String, nullable=False)

    # Лимиты
    minutes_per_month = Column(Float, nullable=True)  # None для безлимитного
    max_file_size_mb = Column(Float, default=100.0)

    # Цены
    price_rub = Column(Float, default=0.0)
    price_usd = Column(Float, default=0.0)
    price_stars = Column(Integer, default=0)

    # Описание и особенности
    description = Column(Text, nullable=True)
    features = Column(Text, nullable=True)  # JSON строка с особенностями

    # Метаданные
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Данные транзакции (соответствует существующей БД)
    plan_type = Column(String, nullable=False)  # Название купленного плана

    # Суммы в разных валютах
    amount_rub = Column(Float, nullable=True)
    amount_usd = Column(Float, nullable=True)
    amount_stars = Column(Integer, nullable=True)  # Telegram Stars
    currency = Column(String, nullable=True)

    # Идентификаторы платежей
    provider_payment_charge_id = Column(String, nullable=True)
    telegram_payment_charge_id = Column(String, nullable=True)
    external_payment_id = Column(String, nullable=True)

    # Статус оплаты
    status = Column(String, default="pending")  # pending, completed, failed, refunded
    payment_method = Column(String, nullable=True)  # telegram_stars, stripe, yookassa, etc.

    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="transactions")

class Transcription(Base):
    __tablename__ = "transcriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Данные файла
    filename = Column(String, nullable=True)
    file_size_mb = Column(Float, nullable=False)
    audio_duration_minutes = Column(Float, nullable=False)

    # Результаты
    raw_transcript = Column(Text, nullable=True)
    formatted_transcript = Column(Text, nullable=True)
    transcript_length = Column(Integer, default=0)

    # Использованные сервисы
    transcription_service = Column(String, default="deepinfra")
    formatting_service = Column(String, nullable=True)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    processing_time_seconds = Column(Float, nullable=True)

    # Связи
    user = relationship("User", back_populates="transcriptions")


class NoteStatus(str, Enum):
    """Lifecycle statuses for notes."""

    INGESTED = "ingested"
    DRAFT = "draft"
    APPROVED = "approved"
    BACKLOG = "backlog"

    # Legacy statuses retained during migration
    NEW = "new"
    PROCESSED = "processed"
    PROCESSED_RAW = "processed_raw"


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ts = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String, default="telegram")
    text = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    type_hint = Column(String, nullable=True)
    type_confidence = Column(Float, default=0.0)
    raw_link = Column(String, nullable=True)
    current_version = Column(Integer, default=0)
    draft_title = Column(String, nullable=True)
    draft_md = Column(Text, nullable=True)
    tags = Column(MutableList.as_mutable(JSONType), default=list)
    links = Column(MutableDict.as_mutable(JSONType), default=dict)
    meta = Column(MutableDict.as_mutable(JSONType), default=dict)
    drive_file_id = Column(String, nullable=True)
    drive_path = Column(String, nullable=True)
    sheet_row_id = Column(String, nullable=True)
    status = Column(String, default=NoteStatus.INGESTED.value)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="notes")
    chunks = relationship("NoteChunk", back_populates="note", cascade="all, delete-orphan")
    versions = relationship("NoteVersion", back_populates="note", cascade="all, delete-orphan", order_by="NoteVersion.version")
    embedding = relationship("NoteEmbedding", back_populates="note", cascade="all, delete-orphan", uselist=False)
    reminders = relationship("Reminder", back_populates="note")
    groups = relationship("NoteGroup", secondary="note_group_links", back_populates="notes")


class NoteGroup(Base):
    __tablename__ = "note_groups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    color = Column(String, nullable=True)
    tags = Column(MutableList.as_mutable(JSONType), default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="note_groups")
    notes = relationship("Note", secondary="note_group_links", back_populates="groups")


note_group_links = Table(
    "note_group_links",
    Base.metadata,
    Column("note_id", Integer, ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("note_groups.id", ondelete="CASCADE"), primary_key=True),
    UniqueConstraint("note_id", "group_id", name="uq_note_group_links_note_group"),
)


class NoteChunk(Base):
    __tablename__ = "note_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    embedding = Column(_embedding_column_type(), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    note = relationship("Note", back_populates="chunks")
    user = relationship("User")


class NoteVersion(Base):
    __tablename__ = "note_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    title = Column(String, nullable=True)
    markdown = Column(Text, nullable=False)
    meta = Column(MutableDict.as_mutable(JSONType), default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    note = relationship("Note", back_populates="versions")


class NoteEmbedding(Base):
    __tablename__ = "note_embeddings"

    note_id = Column(Integer, ForeignKey("notes.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    embedding = Column(_embedding_column_type(), nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    note = relationship("Note", back_populates="embedding")
    user = relationship("User")



class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=True)
    fire_ts = Column(DateTime, nullable=False)
    payload = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    user = relationship("User")
    note = relationship("Note", back_populates="reminders")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    kind = Column(String, nullable=False)
    payload = Column(Text, nullable=True)
    ts = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class GoogleCredential(Base):
    __tablename__ = "google_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    access_token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    expiry = Column(DateTime, nullable=True)
    scopes = Column(Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Данные ключа
    key_hash = Column(String, unique=True, nullable=False)  # Хеш ключа
    name = Column(String, nullable=True)  # Название ключа

    # Лимиты для API ключа
    minutes_limit = Column(Float, nullable=True)  # Лимит минут для этого ключа
    minutes_used = Column(Float, default=0.0)

    # Метаданные
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Связи
    user = relationship("User")

class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)  # Сам промокод

    # Что дает промокод
    plan_type = Column(String, nullable=False)  # unlimited
    duration_days = Column(Integer, nullable=True)  # None для бессрочного

    # Лимиты использования
    max_uses = Column(Integer, nullable=True)  # None -> бесконечное количество
    current_uses = Column(Integer, default=0)  # Сколько раз уже использовали

    # Метаданные
    description = Column(String, nullable=True)  # Описание промокода
    bonus_type = Column(String, nullable=True)
    bonus_value = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Когда промокод истекает

    # Связи с активациями
    activations = relationship("PromoActivation", back_populates="promo_code")

class PromoActivation(Base):
    __tablename__ = "promo_activations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)

    # Метаданные активации
    activated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Когда закончится действие промокода

    # Связи
    user = relationship("User")
    promo_code = relationship("PromoCode", back_populates="activations")


class ReferralLink(Base):
    __tablename__ = "referral_links"

    id = Column(Integer, primary_key=True, index=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralVisit(Base):
    __tablename__ = "referral_visits"

    id = Column(Integer, primary_key=True, index=True)
    referral_code = Column(String, nullable=False, index=True)
    visitor_telegram_id = Column(BigInteger, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralAttribution(Base):
    __tablename__ = "referral_attribution"

    id = Column(Integer, primary_key=True, index=True)
    visitor_telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    referral_code = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReferralPayment(Base):
    __tablename__ = "referral_payments"

    id = Column(Integer, primary_key=True, index=True)
    referral_code = Column(String, nullable=False, index=True)
    payer_telegram_id = Column(BigInteger, nullable=False, index=True)
    amount_rub = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# Предустановленные планы (обновленные описания)
DEFAULT_PLANS = [
    {
        "name": PlanType.FREE,
        "display_name": "🆓 Бесплатный",
        "minutes_per_month": None,  # Для бесплатного тарифа считаем генерации, а не минуты
        "max_file_size_mb": 50.0,
        "price_rub": 0.0,
        "price_usd": 0.0,
        "price_stars": 0,
        "description": "Попробуйте наш сервис бесплатно",
        "features": '["3 видео в месяц", "Файлы до 50 МБ", "Базовое качество", "Доступ к агенту с лимитами плана"]'
    },
    {
        "name": PlanType.BASIC,
        "display_name": "⭐ Базовый",
        "minutes_per_month": 180.0,  # 3 часа
        "max_file_size_mb": 200.0,
        "price_rub": 0.0,
        "price_usd": 0.0,
        "price_stars": 0,
        "description": "План устарел",
        "features": '["План недоступен"]',
        "is_active": False
    },
    {
        "name": PlanType.PRO,
        "display_name": "💎 Профессиональный",
        "minutes_per_month": 600.0,  # 10 часов
        "max_file_size_mb": 500.0,
        "price_rub": 1.0,
        "price_usd": 0.0,
        "price_stars": 230,
        "description": "Для бизнеса и работы",
        "features": '["10 часов в месяц", "Файлы до 500 МБ", "API доступ", "Приоритет"]'
    },
    {
        "name": PlanType.BETA,
        "display_name": "🐾 Супер Кот (архив)",
        "minutes_per_month": None,
        "max_file_size_mb": 2000.0,
        "price_rub": 0.0,
        "price_usd": 0.0,
        "price_stars": 0,
        "description": "План закрыт. Используйте стандартные тарифы.",
        "features": '["План недоступен"]',
        "is_active": False
    },
    {
        "name": PlanType.UNLIMITED,
        "display_name": "🚀 Безлимитный",
        "minutes_per_month": None,  # Безлимитный
        "max_file_size_mb": 2000.0,
        "price_rub": 699.0,
        "price_usd": 0.0,
        "price_stars": 538,
        "description": "Максимальные возможности",
        "features": '["Безлимитные минуты", "Файлы до 2 ГБ", "VIP поддержка", "Все функции"]'
    }
]


class ProcessingJobStatus(str, Enum):
    """Статусы задач обработки медиа."""

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingJob(Base):
    """Запись фоновой задачи обработки."""

    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note_id = Column(Integer, ForeignKey("notes.id"), nullable=True)
    job_type = Column(String(50), nullable=False)
    status = Column(String(32), nullable=False, default=ProcessingJobStatus.QUEUED.value)
    payload = Column(JSON, nullable=True)
    progress = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    locked_by = Column(String(64), nullable=True)
    locked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"ProcessingJob(id={self.id}, job_type={self.job_type!r}, "
            f"status={self.status!r}, user_id={self.user_id})"
        )


class NoteQASession(Base):
    """Persisted QA sessions for note-level conversations."""

    __tablename__ = "note_qa_sessions"

    id = Column(Integer, primary_key=True)
    note_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    tags = Column(MutableList.as_mutable(JSONType), default=list)
    context_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    total_messages = Column(Integer, nullable=False, default=0)

    note = relationship("Note")
    user = relationship("User")
    messages = relationship(
        "NoteQAMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("note_id", "user_id", name="uq_note_qa_sessions_note_user"),
    )


class NoteQAMessage(Base):
    """Individual messages that belong to QA sessions."""

    __tablename__ = "note_qa_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        Integer,
        ForeignKey("note_qa_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(32), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    session = relationship("NoteQASession", back_populates="messages")
