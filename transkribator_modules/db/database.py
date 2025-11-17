"""
Модуль для работы с базой данных CyberKitty Transkribator
"""

import os
import hashlib
import secrets
import json
from datetime import datetime, timedelta, time
from typing import Optional, List
from sqlalchemy import create_engine, desc, func, inspect
from sqlalchemy.orm import sessionmaker, Session, joinedload
from sqlalchemy.exc import IntegrityError
import sqlite3
from pathlib import Path
from sqlalchemy import text

from transkribator_modules.config import logger

from .models import (
    Base,
    User,
    Plan,
    Transaction,
    Transcription,
    ApiKey,
    PromoCode,
    PromoActivation,
    ReferralLink,
    ReferralVisit,
    ReferralAttribution,
    ReferralPayment,
    DEFAULT_PLANS,
    PlanType,
    Note,
    NoteChunk,
    NoteVersion,
    NoteEmbedding,
    Reminder,
    Event,
    GoogleCredential,
    NoteStatus,
    NoteGroup,
)

# Настройка базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./transkribator.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)

# Путь к файлу базы данных
DB_PATH = Path("data/cyberkitty19_transkribator.db")

# Карта отображаемых названий тарифов по их системным именам
DEFAULT_PLAN_DISPLAY_NAMES = {plan["name"]: plan["display_name"] for plan in DEFAULT_PLANS}

AGENT_ELIGIBLE_PLANS = {plan.value for plan in PlanType}

def init_database():
    """Инициализирует базу данных и создает необходимые таблицы."""
    backend = engine.url.get_backend_name()

    # Для PostgreSQL (и других не-sqlite бэкендов) полагаемся на миграции Alembic.
    if backend != "sqlite":
        logger.info("Skipping legacy SQLite bootstrap for backend %s", backend)
        return

    try:
        # Создаем директорию для данных если не существует
        DB_PATH.parent.mkdir(exist_ok=True)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            # Таблица пользователей (обновленная схема)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    current_plan TEXT DEFAULT 'free',
                    plan_expires_at DATETIME,
                    total_minutes_transcribed FLOAT DEFAULT 0.0,
                    minutes_used_this_month FLOAT DEFAULT 0.0,
                    last_reset_date DATE,
                    total_generations INTEGER DEFAULT 0,
                    generations_used_this_month INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    beta_enabled BOOLEAN DEFAULT 0,
                    google_connected BOOLEAN DEFAULT 0
                )
            """)

            # Гарантируем наличие beta_enabled в существующих БД
            cursor.execute("PRAGMA table_info(users)")
            user_columns = [row[1] for row in cursor.fetchall()]
            if "beta_enabled" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN beta_enabled BOOLEAN DEFAULT 0")
            if "google_connected" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN google_connected BOOLEAN DEFAULT 0")
            if "timezone" not in user_columns:
                cursor.execute("ALTER TABLE users ADD COLUMN timezone TEXT")

            # Таблица транскрипций
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    filename TEXT,
                    file_size_mb FLOAT,
                    audio_duration_minutes FLOAT,
                    raw_transcript TEXT,
                    formatted_transcript TEXT,
                    transcript_length INTEGER DEFAULT 0,
                    transcription_service TEXT DEFAULT 'deepinfra',
                    formatting_service TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    processing_time_seconds FLOAT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица транзакций
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_type TEXT,
                    amount_rub FLOAT,
                    amount_usd FLOAT,
                    amount_stars INTEGER,
                    currency TEXT,
                    provider_payment_charge_id TEXT,
                    telegram_payment_charge_id TEXT,
                    external_payment_id TEXT,
                    payment_method TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица API ключей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    key_hash TEXT UNIQUE NOT NULL,
                    name TEXT,
                    minutes_limit FLOAT,
                    minutes_used FLOAT DEFAULT 0.0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица заметок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (

                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    text TEXT,
                    summary TEXT,
                    type_hint TEXT,
                    type_confidence FLOAT DEFAULT 0.0,
                    raw_link TEXT,
                    current_version INTEGER DEFAULT 0,
                    draft_title TEXT,
                    draft_md TEXT,
                    tags TEXT,
                    links TEXT,
                    meta TEXT,
                    drive_file_id TEXT,
                    drive_path TEXT,
                    sheet_row_id TEXT,
                    status TEXT DEFAULT ingested,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_notes_user_ts ON notes(user_id, ts)")

            cursor.execute("PRAGMA table_info(notes)")
            note_columns = [row[1] for row in cursor.fetchall()]
            if "raw_link" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN raw_link TEXT")
            if "current_version" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN current_version INTEGER DEFAULT 0")
            if "draft_title" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN draft_title TEXT")
            if "draft_md" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN draft_md TEXT")
            if "meta" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN meta TEXT")
            if "drive_path" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN drive_path TEXT")
            if "sheet_row_id" not in note_columns:
                cursor.execute("ALTER TABLE notes ADD COLUMN sheet_row_id TEXT")
            if "status" in note_columns:
                cursor.execute("UPDATE notes SET status='ingested' WHERE status='new'")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS note_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id INTEGER,
                    version INTEGER,
                    title TEXT,
                    markdown TEXT,
                    meta TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (note_id) REFERENCES notes (id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_note_versions_note_id ON note_versions(note_id, version)")

            # Таблица эмбеддингов заметок
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS note_embeddings (
                    note_id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    embedding TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (note_id) REFERENCES notes (id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            cursor.execute("PRAGMA table_info(note_embeddings)")
            embedding_columns = [row[1] for row in cursor.fetchall()]
            if "updated_at" not in embedding_columns:
                cursor.execute("ALTER TABLE note_embeddings ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")

            # Таблица напоминаний
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    note_id INTEGER,
                    fire_ts DATETIME,
                    payload TEXT,
                    sent_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (note_id) REFERENCES notes (id)
                )
            """)

            # Таблица событий
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    kind TEXT,
                    payload TEXT,
                    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица групп заметок для мини-приложения
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS note_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    color TEXT,
                    tags TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица Google credentials
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS google_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    access_token TEXT,
                    refresh_token TEXT,
                    expiry DATETIME,
                    scopes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            # Таблица планов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL UNIQUE,
                    display_name VARCHAR NOT NULL,
                    minutes_per_month FLOAT,
                    max_file_size_mb FLOAT DEFAULT 100.0,
                    price_rub FLOAT DEFAULT 0.0,
                    price_usd FLOAT DEFAULT 0.0,
                    price_stars INTEGER DEFAULT 0,
                    description TEXT,
                    features TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Таблица промокодов (обновленная структура)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    plan_type TEXT NOT NULL,
                    duration_days INTEGER,
                    max_uses INTEGER DEFAULT 1,
                    current_uses INTEGER DEFAULT 0,
                    description TEXT,
                    bonus_type TEXT,
                    bonus_value TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME
                )
            """)

            # Таблица активаций промокодов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promo_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    promo_code_id INTEGER,
                    activated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes (id)
                )
            """)

            # Реферальные таблицы
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_telegram_id INTEGER NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_code TEXT NOT NULL,
                    visitor_telegram_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_attribution (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    visitor_telegram_id INTEGER UNIQUE NOT NULL,
                    referral_code TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS referral_payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_code TEXT NOT NULL,
                    payer_telegram_id INTEGER NOT NULL,
                    amount_rub REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.commit()

            # Миграция существующих таблиц
            migrate_database_schema(conn)

            logger.info("База данных инициализирована успешно")

        # Инициализируем промокоды
        init_promo_codes()

        # Инициализируем планы
        init_plans()

    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

    # Дополнительные проверки для PostgreSQL
    try:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS beta_enabled BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS google_connected BOOLEAN DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64)"))
            conn.commit()
    except Exception as exc:
        logger.warning("Не удалось добавить колонку beta_enabled", extra={"error": str(exc)})

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        logger.warning("Метаданные не применены", extra={"error": str(exc)})

def get_db():
    """Получение сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_user(self, telegram_id: int, username: str = None,
                          first_name: str = None, last_name: str = None) -> User:
        """Получить или создать пользователя"""
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()

        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                current_plan=PlanType.FREE.value,
                plan_expires_at=None,
                beta_enabled=True,
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
            setattr(user, "_was_created", True)
        else:
            # Обновляем информацию пользователя
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
            if last_name:
                user.last_name = last_name
            user.updated_at = datetime.utcnow()
            self.db.commit()
            setattr(user, "_was_created", False)

        if getattr(user, "beta_enabled", None) is None and user.current_plan in AGENT_ELIGIBLE_PLANS:
            user.beta_enabled = True
            user.updated_at = datetime.utcnow()
            self.db.commit()

        # Обнуляем beta_enabled, если пришёл старый null
        if getattr(user, "beta_enabled", None) is None:
            user.beta_enabled = False
            self.db.commit()

        if getattr(user, "google_connected", None) is None:
            user.google_connected = False
            self.db.commit()

        if getattr(user, "timezone", None) == "":
            user.timezone = None
            self.db.commit()

        return user

    def check_usage_limit(self, user: User, minutes_needed: float = 0.0) -> tuple[bool, str]:
        """Проверить, может ли пользователь использовать сервис"""
        # Сбрасываем счетчики, если прошел месяц
        self._reset_monthly_usage_if_needed(user)

        plan = self.get_user_plan(user)
        if not plan:
            return False, "План пользователя не найден"

        if user.plan_expires_at and user.plan_expires_at <= datetime.utcnow():
            expires_at = user.plan_expires_at
            try:
                from transkribator_modules.jobs.plan_reminders import (  # pylint: disable=import-outside-toplevel
                    send_expired_notification,
                )

                send_expired_notification(user, expires_at)
            except Exception as exc:  # noqa: BLE001 - уведомление не критично
                logger.warning(
                    "Failed to send plan expiration notice",
                    extra={"user_id": user.id, "error": str(exc)},
                )
            user.current_plan = PlanType.FREE.value
            user.beta_enabled = True
            user.plan_expires_at = None
            user.updated_at = datetime.utcnow()
            self.db.commit()
            plan = self.get_user_plan(user)

        # Для бесплатного тарифа проверяем количество генераций
        if user.current_plan == "free":
            if user.generations_used_this_month >= 3:
                remaining = max(0, 3 - user.generations_used_this_month)
                return False, f"Превышен лимит бесплатного тарифа. Осталось генераций: {remaining}"
            return True, "Лимит не превышен"

        # Для платных тарифов проверяем минуты
        # Безлимитный план
        if plan.minutes_per_month is None:
            return True, "Безлимитный план"

        # Проверяем лимит минут
        if user.minutes_used_this_month + minutes_needed > plan.minutes_per_month:
            remaining = max(0, plan.minutes_per_month - user.minutes_used_this_month)
            return False, f"Превышен лимит плана. Осталось: {remaining:.1f} мин"

        return True, "Лимит не превышен"

    def check_minutes_limit(self, user: User, minutes_needed: float) -> tuple[bool, str]:
        """Проверить, может ли пользователь использовать указанное количество минут (устаревший метод)"""
        return self.check_usage_limit(user, minutes_needed)

    def add_usage(self, user: User, minutes_used: float = 0.0) -> None:
        """Добавить использование (минуты или генерацию)"""
        self._reset_monthly_usage_if_needed(user)

        # Для бесплатного тарифа считаем и генерации, и минуты
        if user.current_plan == "free":
            user.generations_used_this_month += 1
            user.total_generations += 1
            # Также считаем минуты для статистики
            user.minutes_used_this_month += minutes_used
            user.total_minutes_transcribed += minutes_used
        else:
            # Для платных тарифов считаем минуты
            user.minutes_used_this_month += minutes_used
            user.total_minutes_transcribed += minutes_used

        user.updated_at = datetime.utcnow()
        self.db.commit()

    def set_beta_enabled(self, user: User, enabled: bool) -> None:
        """Включить или выключить бета-режим для пользователя.

        merge() гарантирует, что объект привязан к текущей сессии даже если
        его передали отсоединённым (например, из FastAPI Depends).
        """
        state = inspect(user)
        if state.session is not self.db:
            # merge вернёт присоединённый экземпляр, если объект уже существует
            if state.identity is not None:
                user = self.db.merge(user)
            elif getattr(user, "id", None):
                user = (
                    self.db.query(User)
                    .filter(User.id == user.id)
                    .one_or_none()
                ) or user
            elif getattr(user, "telegram_id", None):
                user = (
                    self.db.query(User)
                    .filter(User.telegram_id == user.telegram_id)
                    .one_or_none()
                ) or user

        if user.current_plan in AGENT_ELIGIBLE_PLANS:
            user.beta_enabled = bool(enabled)
        else:
            user.beta_enabled = False
        user.updated_at = datetime.utcnow()
        self.db.commit()

    def set_timezone(self, user: User, timezone: str | None) -> None:
        user.timezone = timezone
        user.updated_at = datetime.utcnow()
        self.db.commit()

    def get_timezone(self, user: User) -> Optional[str]:
        value = getattr(user, "timezone", None)
        if value:
            return str(value)
        return None

    def is_beta_enabled(self, user: User) -> bool:
        """Проверить, активен ли бета-режим для пользователя"""
        allowed = user.current_plan in AGENT_ELIGIBLE_PLANS
        if not allowed:
            return False

        current_value = getattr(user, "beta_enabled", None)
        if current_value is None:
            user.beta_enabled = True
            user.updated_at = datetime.utcnow()
            self.db.commit()
            return True

        return bool(current_value)

    def set_google_connected(self, user: User, connected: bool) -> None:
        """Обновить флаг подключения Google для пользователя."""
        user.google_connected = connected
        user.updated_at = datetime.utcnow()
        self.db.commit()

    def add_minutes_usage(self, user: User, minutes_used: float) -> None:
        """Добавить использованные минуты (устаревший метод)"""
        self.add_usage(user, minutes_used)

    def get_user_plan(self, user: User) -> Optional[Plan]:
        """Получить текущий план пользователя"""
        return self.db.query(Plan).filter(Plan.name == user.current_plan).first()

    def get_usage_info(self, user: User) -> dict:
        """Получить информацию об использовании"""
        self._reset_monthly_usage_if_needed(user)
        plan = self.get_user_plan(user)

        if plan and getattr(plan, "display_name", None):
            plan_display_name = plan.display_name
        elif user.current_plan in DEFAULT_PLAN_DISPLAY_NAMES:
            plan_display_name = DEFAULT_PLAN_DISPLAY_NAMES[user.current_plan]
        elif user.current_plan:
            # Fallback to a human-readable variant of the raw plan slug
            plan_display_name = user.current_plan.replace("_", " ").strip()
        else:
            plan_display_name = "Неизвестный"

        info = {
            "current_plan": user.current_plan,
            "plan_display_name": plan_display_name or "Неизвестный",
            "minutes_used_this_month": user.minutes_used_this_month,
            "total_minutes_transcribed": user.total_minutes_transcribed,
            "generations_used_this_month": user.generations_used_this_month,
            "total_generations": user.total_generations,
            "plan_expires_at": user.plan_expires_at
        }

        # Для бесплатного тарифа показываем информацию о генерациях
        if user.current_plan == "free":
            info["generations_limit"] = 3
            info["generations_remaining"] = max(0, 3 - user.generations_used_this_month)
            info["usage_percentage"] = (user.generations_used_this_month / 3) * 100
            info["minutes_limit"] = None
            info["minutes_remaining"] = None
        elif plan and plan.minutes_per_month is not None:
            # Для платных тарифов показываем информацию о минутах
            info["minutes_limit"] = plan.minutes_per_month
            info["minutes_remaining"] = max(0, plan.minutes_per_month - user.minutes_used_this_month)
            info["usage_percentage"] = (user.minutes_used_this_month / plan.minutes_per_month) * 100
            info["generations_limit"] = None
            info["generations_remaining"] = None
        else:
            # Безлимитный план
            info["minutes_limit"] = None
            info["minutes_remaining"] = float('inf')
            info["usage_percentage"] = 0
            info["generations_limit"] = None
            info["generations_remaining"] = None

        return info

    def upgrade_user_plan(self, user: User, new_plan: str, transaction_id: int = None) -> bool:
        """Обновить план пользователя"""
        plan = self.db.query(Plan).filter(Plan.name == new_plan).first()
        if not plan:
            return False

        user.current_plan = new_plan
        now = datetime.utcnow()

        if new_plan == PlanType.FREE.value:
            user.plan_expires_at = None
        else:
            user.plan_expires_at = now + timedelta(days=30)

        user.beta_enabled = new_plan in AGENT_ELIGIBLE_PLANS

        user.updated_at = now

        # Если переходим на новый платный план, сбрасываем месячное использование
        if new_plan != PlanType.FREE.value:
            user.minutes_used_this_month = 0.0
            user.generations_used_this_month = 0
            user.last_reset_date = now
        else:
            # Для бесплатного тарифа отсчитываем генерации заново в текущем месяце
            user.generations_used_this_month = min(user.generations_used_this_month, 3)

        self.db.commit()
        return True

    def _reset_monthly_usage_if_needed(self, user: User) -> bool:
        """Сбросить месячное использование, если прошёл месяц.

        Возвращает True, если счётчики были сброшены в этом вызове.
        """
        reset = False
        now = datetime.utcnow()

        last_reset = getattr(user, "last_reset_date", None)
        if last_reset:
            days_since_reset = (now - last_reset).days
            if days_since_reset >= 30:
                user.minutes_used_this_month = 0.0
                user.generations_used_this_month = 0  # Сбрасываем и счётчик генераций
                user.last_reset_date = now
                self.db.commit()
                reset = True
        else:
            user.last_reset_date = now
            self.db.commit()

        setattr(user, "_usage_reset", reset)
        return reset


class NoteService:
    def __init__(self, db: Session):
        self.db = db

    def create_note(
        self,
        user: User,
        text: str,
        source: str = "telegram",
        summary: Optional[str] = None,
        type_hint: Optional[str] = None,
        type_confidence: Optional[float] = None,
        tags: Optional[list[str]] = None,
        links: Optional[dict] = None,
        drive_file_id: Optional[str] = None,
        status: Optional[str] = None,
        raw_link: Optional[str] = None,
        draft_title: Optional[str] = None,
        draft_md: Optional[str] = None,
        meta: Optional[dict] = None,
        create_version: bool = False,
        group_ids: Optional[list[int]] = None,
    ) -> Note:
        note = Note(
            user_id=user.id,
            ts=datetime.utcnow(),
            source=source,
            text=text,
            summary=summary,
            type_hint=type_hint,
            type_confidence=type_confidence or 0.0,
            raw_link=raw_link,
            draft_title=draft_title,
            draft_md=draft_md,
            tags=tags or [],
            links=links or {},
            meta=meta or {},
            drive_file_id=drive_file_id,
            status=status or NoteStatus.INGESTED.value,
        )
        self.db.add(note)
        if group_ids:
            groups = (
                self.db.query(NoteGroup)
                .filter(NoteGroup.user_id == user.id, NoteGroup.id.in_(group_ids))
                .all()
            )
            note.groups = groups
        else:
            note.groups = []
        self.db.commit()
        self.db.refresh(note)
        if create_version and draft_md:
            self.add_version(note, markdown=draft_md, title=draft_title, meta=meta)
        return note

    def get_note(self, note_id: int) -> Optional[Note]:
        return (
            self.db.query(Note)
            .options(joinedload(Note.groups))
            .filter(Note.id == note_id)
            .one_or_none()
        )

    def update_note_metadata(
        self,
        note: Note,
        *,
        summary: Optional[str] = None,
        tags: Optional[list[str]] = None,
        links: Optional[dict] = None,
        drive_file_id: Optional[str] = None,
        drive_path: Optional[str] = None,
        sheet_row_id: Optional[str] = None,
        status: Optional[str] = None,
        raw_link: Optional[str] = None,
        draft_title: Optional[str] = None,
        draft_md: Optional[str] = None,
        meta: Optional[dict] = None,
        type_hint: Optional[str] = None,
    ) -> Note:
        if summary is not None:
            note.summary = summary
        if tags is not None:
            note.tags = list(tags)
        if links is not None:
            existing_links = dict(note.links or {})
            existing_links.update(links)
            note.links = existing_links
        if drive_file_id is not None:
            note.drive_file_id = drive_file_id
        if drive_path is not None:
            note.drive_path = drive_path
        if sheet_row_id is not None:
            note.sheet_row_id = sheet_row_id
        if status is not None:
            note.status = status
        if raw_link is not None:
            note.raw_link = raw_link
        if draft_title is not None:
            note.draft_title = draft_title
        if draft_md is not None:
            note.draft_md = draft_md
        if meta is not None:
            merged_meta = dict(note.meta or {})
            merged_meta.update(meta)
            note.meta = merged_meta
        if type_hint is not None:
            note.type_hint = type_hint
        note.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(note)
        return note

    def add_version(
        self,
        note: Note,
        *,
        markdown: str,
        title: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> NoteVersion:
        next_version = (note.current_version or 0) + 1
        version_record = NoteVersion(
            note_id=note.id,
            version=next_version,
            title=title,
            markdown=markdown,
            meta=meta or {},
        )
        self.db.add(version_record)
        note.current_version = next_version
        note.draft_title = title
        note.draft_md = markdown
        if meta:
            merged_meta = dict(note.meta or {})
            merged_meta.update(meta)
            note.meta = merged_meta
        note.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(version_record)
        self.db.refresh(note)
        return version_record

    def update_status(self, note: Note, status: str) -> Note:
        note.status = status
        note.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(note)
        return note

    def mark_archived(self, note: Note) -> Note:
        note.status = "archived"
        note.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(note)
        try:
            from transkribator_modules.search import IndexService

            IndexService().remove(note.id, note.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to remove note from index",
                extra={"note_id": note.id, "user_id": note.user_id, "error": str(exc)},
            )
        return note

    def list_user_notes(self, user: User) -> List[Note]:
        return (
            self.db.query(Note)
            .options(joinedload(Note.groups))
            .filter(
                Note.user_id == user.id,
                Note.status != "archived",
            )
            .order_by(Note.ts.desc())
            .all()
        )

    def set_note_groups(self, note: Note, group_ids: list[int]) -> Note:
        if group_ids:
            groups = (
                self.db.query(NoteGroup)
                .filter(NoteGroup.user_id == note.user_id, NoteGroup.id.in_(group_ids))
                .all()
            )
        else:
            groups = []
        note.groups = groups
        note.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(note)
        return note


class NoteGroupService:
    def __init__(self, db: Session):
        self.db = db

    def list_groups(self, user_id: int) -> List[NoteGroup]:
        return (
            self.db.query(NoteGroup)
            .options(joinedload(NoteGroup.notes))
            .filter(NoteGroup.user_id == user_id)
            .order_by(NoteGroup.created_at.desc())
            .all()
        )

    def get_group(self, user_id: int, group_id: int) -> Optional[NoteGroup]:
        return (
            self.db.query(NoteGroup)
            .filter(NoteGroup.user_id == user_id, NoteGroup.id == group_id)
            .one_or_none()
        )

    def create_group(self, user_id: int, name: str, tags: list[str], color: Optional[str] = None) -> NoteGroup:
        group = NoteGroup(user_id=user_id, name=name, tags=list(dict.fromkeys(tags)), color=color)
        self.db.add(group)
        self.db.commit()
        self.db.refresh(group)
        return group

    def update_group(
        self,
        group: NoteGroup,
        *,
        name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        color: Optional[str] = None,
    ) -> NoteGroup:
        if name is not None:
            group.name = name
        if tags is not None:
            group.tags = list(dict.fromkeys(tags))
        if color is not None:
            group.color = color
        group.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(group)
        return group

    def delete_group(self, group: NoteGroup) -> None:
        self.db.delete(group)
        self.db.commit()

    def merge_groups(
        self,
        user_id: int,
        group_ids: list[int],
        *,
        name: str,
        color: Optional[str] = None,
    ) -> NoteGroup:
        groups = (
            self.db.query(NoteGroup)
            .filter(NoteGroup.user_id == user_id, NoteGroup.id.in_(group_ids))
            .all()
        )
        if not groups:
            raise ValueError("No groups found to merge")
        merged_tags: list[str] = []
        for group in groups:
            merged_tags.extend(group.tags or [])

        note_ids: set[int] = set()
        for group in groups:
            note_ids.update(note.id for note in group.notes or [])

        merged_group = NoteGroup(
            user_id=user_id,
            name=name,
            color=color,
            tags=list(dict.fromkeys(merged_tags)),
        )
        self.db.add(merged_group)
        for group in groups:
            self.db.delete(group)
        self.db.flush()

        if note_ids:
            notes = (
                self.db.query(Note)
                .filter(Note.user_id == user_id, Note.id.in_(note_ids))
                .all()
            )
            merged_group.notes = notes
        self.db.commit()
        self.db.refresh(merged_group)
        return merged_group

    def list_backlog(self, user: User, limit: int = 10) -> List[Note]:
        return (
            self.db.query(Note)
            .filter(Note.user_id == user.id, Note.status == NoteStatus.BACKLOG.value)
            .order_by(Note.ts.asc())
            .limit(limit)
            .all()
        )

    def schedule_backlog_reminder(self, user: User, note: Note) -> Reminder:
        """Создаёт или обновляет напоминание на 20:00 ближайшего дня."""

        now = datetime.utcnow()
        target_dt = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if target_dt <= now:
            target_dt += timedelta(days=1)

        existing = (
            self.db.query(Reminder)
            .filter(
                Reminder.user_id == user.id,
                Reminder.note_id == note.id,
                Reminder.sent_at.is_(None),
            )
            .first()
        )

        payload = json.dumps({"kind": "backlog_reminder", "note_id": note.id})

        if existing:
            existing.fire_ts = target_dt
            existing.payload = payload
            self.db.commit()
            self.db.refresh(existing)
            return existing

        reminder = Reminder(
            user_id=user.id,
            note_id=note.id,
            fire_ts=target_dt,
            payload=payload,
        )
        self.db.add(reminder)
        self.db.commit()
        self.db.refresh(reminder)
        return reminder

class ApiKeyService:
    def __init__(self, db: Session):
        self.db = db

    def generate_api_key(self, user: User, name: str = None, minutes_limit: float = None) -> tuple[str, ApiKey]:
        """Создать новый API ключ"""
        # Генерируем случайный ключ
        raw_key = f"sk-{secrets.token_urlsafe(48)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = ApiKey(
            user_id=user.id,
            key_hash=key_hash,
            name=name or f"API Key {datetime.now().strftime('%Y-%m-%d')}",
            minutes_limit=minutes_limit
        )

        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)

        return raw_key, api_key

    def verify_api_key(self, raw_key: str) -> Optional[ApiKey]:
        """Проверить API ключ"""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        api_key = self.db.query(ApiKey).filter(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True
        ).first()

        if api_key:
            # Обновляем время последнего использования
            api_key.last_used_at = datetime.utcnow()
            self.db.commit()

        return api_key

    def check_api_key_limits(self, api_key: ApiKey, minutes_needed: float) -> tuple[bool, str]:
        """Проверить лимиты API ключа"""
        if api_key.minutes_limit is None:
            return True, "Безлимитный ключ"

        if api_key.minutes_used + minutes_needed > api_key.minutes_limit:
            remaining = max(0, api_key.minutes_limit - api_key.minutes_used)
            return False, f"Превышен лимит API ключа. Осталось: {remaining:.1f} мин"

        return True, "Лимит не превышен"

    def add_api_key_usage(self, api_key: ApiKey, minutes_used: float) -> None:
        """Добавить использованные минуты для API ключа"""
        api_key.minutes_used += minutes_used
        self.db.commit()

class TranscriptionService:
    def __init__(self, db: Session):
        self.db = db

    def save_transcription(self, user: User, filename: str, file_size_mb: float,
                          audio_duration_minutes: float, raw_transcript: str,
                          formatted_transcript: str = None, processing_time: float = None,
                          transcription_service: str = "deepinfra",
                          formatting_service: str = None) -> Transcription:
        """Сохранить результат транскрибации"""
        transcription = Transcription(
            user_id=user.id,
            filename=filename,
            file_size_mb=file_size_mb,
            audio_duration_minutes=audio_duration_minutes,
            raw_transcript=raw_transcript,
            formatted_transcript=formatted_transcript or raw_transcript,
            transcript_length=len(formatted_transcript or raw_transcript),
            transcription_service=transcription_service,
            formatting_service=formatting_service,
            processing_time_seconds=processing_time
        )

        self.db.add(transcription)
        self.db.commit()
        self.db.refresh(transcription)

        return transcription

    def get_user_transcriptions(self, user: User, limit: int = 50) -> List[Transcription]:
        """Получить транскрибации пользователя"""
        return self.db.query(Transcription).filter(
            Transcription.user_id == user.id
        ).order_by(desc(Transcription.created_at)).limit(limit).all()

    def get_user_transcriptions_count(self, user: User) -> int:
        """Получить количество транскрибаций пользователя"""
        return self.db.query(Transcription).filter(
            Transcription.user_id == user.id
        ).count()

class TransactionService:
    def __init__(self, db: Session):
        self.db = db

    def create_transaction(self, user: User, plan_type: str,
                          amount_rub: float = None, amount_usd: float = None,
                          amount_stars: int = None,
                          payment_method: str = None,
                          currency: str = None,
                          provider_payment_charge_id: str = None,
                          telegram_payment_charge_id: str = None,
                          external_payment_id: str = None,
                          status: str = "completed") -> Transaction:
        """Создать новую транзакцию"""
        transaction = Transaction(
            user_id=user.id,
            plan_type=plan_type,
            amount_rub=amount_rub,
            amount_usd=amount_usd,
            amount_stars=amount_stars,
            payment_method=payment_method,
            status=status,
            currency=currency,
            provider_payment_charge_id=provider_payment_charge_id,
            telegram_payment_charge_id=telegram_payment_charge_id,
            external_payment_id=external_payment_id
        )

        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)

        if status == "completed" and amount_rub:
            try:
                referral_service = ReferralService(self.db)
                referral_service.record_referral_payment(user, amount_rub, commit=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to record referral payment",
                    extra={
                        "user_id": user.id,
                        "telegram_id": user.telegram_id,
                        "amount_rub": amount_rub,
                        "error": str(exc),
                    },
                )

        return transaction

    def get_user_transactions(self, user: User, limit: int = 50) -> List[Transaction]:
        """Получить транзакции пользователя"""
        return self.db.query(Transaction).filter(
            Transaction.user_id == user.id
        ).order_by(desc(Transaction.created_at)).limit(limit).all()

    def get_transaction_by_payment_id(self, payment_id: str) -> Optional[Transaction]:
        """Найти транзакцию по ID платежа"""
        return self.db.query(Transaction).filter(
            (Transaction.provider_payment_charge_id == payment_id) |
            (Transaction.telegram_payment_charge_id == payment_id) |
            (Transaction.external_payment_id == payment_id)
        ).first()

class PromoCodeService:
    def __init__(self, db: Session):
        self.db = db

    def create_promo_code(self, code: str, plan_type: str, duration_days: int = None,
                         max_uses: int = 1, description: str = None,
                         expires_at: datetime = None, bonus_type: str = None,
                         bonus_value: str = None) -> PromoCode:
        """Создать новый промокод"""
        promo = PromoCode(
            code=code.upper(),
            plan_type=plan_type,
            duration_days=duration_days,
            max_uses=max_uses,
            description=description,
            expires_at=expires_at,
            bonus_type=bonus_type,
            bonus_value=bonus_value
        )

        self.db.add(promo)
        self.db.commit()
        self.db.refresh(promo)

        return promo

    def get_promo_code(self, code: str) -> Optional[PromoCode]:
        """Получить промокод по коду"""
        return self.db.query(PromoCode).filter(
            PromoCode.code == code.upper(),
            PromoCode.is_active == True
        ).first()

    def validate_promo_code(self, code: str, user: User) -> tuple[bool, str, Optional[PromoCode]]:
        """Проверить валидность промокода для пользователя"""
        promo = self.get_promo_code(code)

        if not promo:
            return False, "🙈 Промокод не найден", None

        # Проверяем срок действия
        if promo.expires_at and promo.expires_at < datetime.utcnow():
            return False, "😿 Промокод истек", None

        # Проверяем лимит использований
        if promo.current_uses >= promo.max_uses:
            return False, "😼 Промокод уже использован максимальное количество раз", None

        # Проверяем, не использовал ли уже этот пользователь
        existing_activation = self.db.query(PromoActivation).filter(
            PromoActivation.user_id == user.id,
            PromoActivation.promo_code_id == promo.id
        ).first()

        if existing_activation and promo.code.upper() != "LIGHTKITTY":
            # Особая проверка для временных промокодов
            if promo.duration_days is not None:
                return False, "😏 Ой-ой-ой! Хитрюшка обнаружена! Этот промокод можно использовать только один раз. *виляет пальчиком*", None
            else:
                return False, "😺 Вы уже использовали этот промокод", None

        return True, "✅ Промокод валиден", promo

    def activate_promo_code(self, promo: PromoCode, user: User) -> PromoActivation:
        """Активировать промокод для пользователя"""
        # Вычисляем срок действия
        expires_at = None
        if promo.duration_days:
            expires_at = datetime.utcnow() + timedelta(days=promo.duration_days)

        # Создаем активацию
        activation = PromoActivation(
            user_id=user.id,
            promo_code_id=promo.id,
            expires_at=expires_at
        )

        # Обновляем счетчик использований
        promo.current_uses += 1

        # Обновляем план пользователя
        user.current_plan = promo.plan_type
        now = datetime.utcnow()
        if expires_at:
            user.plan_expires_at = expires_at
        elif promo.plan_type == PlanType.FREE.value:
            user.plan_expires_at = now + timedelta(days=7)
        else:
            user.plan_expires_at = None  # Бессрочный

        user.beta_enabled = promo.plan_type in {PlanType.BETA.value, PlanType.UNLIMITED.value}

        # Сбрасываем месячное использование при активации нового плана
        if promo.plan_type != PlanType.FREE.value:
            user.minutes_used_this_month = 0.0
            user.generations_used_this_month = 0
            user.last_reset_date = now

        self.db.add(activation)
        self.db.commit()
        self.db.refresh(activation)
        try:
            log_event(
                user,
                "promo_activated",
                {
                    "code": promo.code,
                    "plan": promo.plan_type,
                    "duration_days": promo.duration_days,
                },
            )
        except Exception:
            logger.debug("Failed to log promo activation", exc_info=True)

        return activation

    def get_user_active_promos(self, user: User) -> List[PromoActivation]:
        """Получить активные промокоды пользователя"""
        return self.db.query(PromoActivation).filter(
            PromoActivation.user_id == user.id,
            (PromoActivation.expires_at == None) | (PromoActivation.expires_at > datetime.utcnow())
        ).all()


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def add_event(self, user_id: int, kind: str, payload: dict) -> Event:
        event = Event(
            user_id=user_id,
            kind=kind,
            payload=json.dumps(payload, ensure_ascii=False),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def has_event(self, user_id: int, kind: str, note_id: int) -> bool:
        events = (
            self.db.query(Event)
            .filter(Event.user_id == user_id, Event.kind == kind)
            .all()
        )
        for event in events:
            try:
                data = json.loads(event.payload or "{}")
            except json.JSONDecodeError:
                continue
            if data.get("note_id") == note_id:
                return True
        return False

    def list_events(self, kind: str, limit: int = 20) -> list[Event]:
        return (
            self.db.query(Event)
            .filter(Event.kind == kind)
            .order_by(Event.ts.asc())
            .limit(limit)
            .all()
        )

    def delete_event(self, event: Event) -> None:
        self.db.delete(event)
        self.db.commit()

def get_plans() -> List[Plan]:
    """Получить все доступные планы"""
    db = SessionLocal()
    try:
        return db.query(Plan).filter(Plan.is_active == True).all()
    finally:
        db.close()

def calculate_audio_duration(file_size_mb: float) -> float:
    """Примерный расчет длительности аудио по размеру файла (очень приблизительно)"""
    # Грубая оценка: 1 МБ ≈ 1 минута для сжатого аудио
    # В реальности нужно использовать ffprobe или аналогичный инструмент
    return file_size_mb * 0.8  # Консервативная оценка

def get_media_duration(file_path: str) -> float:
    """Получает реальную длительность аудио/видео файла в минутах с помощью ffprobe"""
    import subprocess
    import json

    try:
        # Используем ffprobe для получения длительности
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(file_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            duration_seconds = float(data['format']['duration'])
            duration_minutes = duration_seconds / 60.0
            logger.info(f"Реальная длительность файла {file_path}: {duration_minutes:.2f} минут")
            return duration_minutes
        else:
            logger.warning(f"ffprobe не смог получить длительность файла {file_path}: {result.stderr}")
            # Fallback к приблизительному расчету
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            return calculate_audio_duration(file_size_mb)

    except subprocess.TimeoutExpired:
        logger.warning(f"ffprobe timeout для файла {file_path}")
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return calculate_audio_duration(file_size_mb)
    except Exception as e:
        logger.error(f"Ошибка при получении длительности файла {file_path}: {e}")
        # Fallback к приблизительному расчету
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return calculate_audio_duration(file_size_mb)

def migrate_database_schema(conn):
    """Мигрирует схему базы данных для совместимости с новыми моделями"""
    cursor = conn.cursor()

    try:
        # Проверяем, есть ли старые колонки в таблице users
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        # Добавляем недостающие колонки
        if 'last_name' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
            print("Добавлена колонка last_name")

        if 'current_plan' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN current_plan TEXT DEFAULT 'free'")
            print("Добавлена колонка current_plan")

        if 'plan_expires_at' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN plan_expires_at DATETIME")
            print("Добавлена колонка plan_expires_at")

        if 'total_minutes_transcribed' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN total_minutes_transcribed FLOAT DEFAULT 0.0")
            print("Добавлена колонка total_minutes_transcribed")

        if 'minutes_used_this_month' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN minutes_used_this_month FLOAT DEFAULT 0.0")
            print("Добавлена колонка minutes_used_this_month")

        if 'last_reset_date' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_reset_date DATE")
            print("Добавлена колонка last_reset_date")

        if 'updated_at' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            print("Добавлена колонка updated_at")

        if 'is_active' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1")
            print("Добавлена колонка is_active")

        # Добавляем новые колонки для генераций
        if 'total_generations' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN total_generations INTEGER DEFAULT 0")
            print("Добавлена колонка total_generations")

        if 'generations_used_this_month' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN generations_used_this_month INTEGER DEFAULT 0")
            print("Добавлена колонка generations_used_this_month")

        # Мигрируем данные из старых колонок
        if 'subscription_type' in columns and 'current_plan' in columns:
            cursor.execute("UPDATE users SET current_plan = subscription_type WHERE current_plan = 'free'")
            print("Мигрированы данные из subscription_type в current_plan")

        if 'minutes_transcribed' in columns and 'total_minutes_transcribed' in columns:
            cursor.execute("UPDATE users SET total_minutes_transcribed = minutes_transcribed WHERE total_minutes_transcribed = 0.0")
            print("Мигрированы данные из minutes_transcribed в total_minutes_transcribed")

        # Мигрируем таблицу transcriptions к новой структуре
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transcriptions'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(transcriptions)")
            columns = [col[1] for col in cursor.fetchall()]

            # Проверяем, нужно ли обновить структуру
            if 'filename' not in columns:
                print("Обновляем структуру таблицы transcriptions...")

                # Создаем новую таблицу с правильной структурой
                cursor.execute("""
                    CREATE TABLE transcriptions_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        filename TEXT,
                        file_size_mb FLOAT,
                        audio_duration_minutes FLOAT,
                        raw_transcript TEXT,
                        formatted_transcript TEXT,
                        transcript_length INTEGER DEFAULT 0,
                        transcription_service TEXT DEFAULT 'deepinfra',
                        formatting_service TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        processing_time_seconds FLOAT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                """)

                # Копируем данные из старой таблицы
                cursor.execute("""
                    INSERT INTO transcriptions_new (
                        id, user_id, filename, file_size_mb, audio_duration_minutes,
                        raw_transcript, formatted_transcript, transcript_length,
                        created_at
                    )
                    SELECT
                        id, user_id, file_name, file_size, duration,
                        transcript, transcript, LENGTH(transcript),
                        created_at
                    FROM transcriptions
                """)

                # Удаляем старую таблицу и переименовываем новую
                cursor.execute("DROP TABLE transcriptions")
                cursor.execute("ALTER TABLE transcriptions_new RENAME TO transcriptions")

                print("Таблица transcriptions обновлена")

        # Проверяем и создаем недостающие таблицы
        tables_to_create = {
            'plans': """
                CREATE TABLE plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL UNIQUE,
                    display_name VARCHAR NOT NULL,
                    minutes_per_month FLOAT,
                    max_file_size_mb FLOAT DEFAULT 100.0,
                    price_rub FLOAT DEFAULT 0.0,
                    price_usd FLOAT DEFAULT 0.0,
                    price_stars INTEGER DEFAULT 0,
                    description TEXT,
                    features TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'transactions': """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_type TEXT,
                    amount_rub FLOAT,
                    amount_usd FLOAT,
                    amount_stars INTEGER,
                    currency TEXT,
                    provider_payment_charge_id TEXT,
                    telegram_payment_charge_id TEXT,
                    external_payment_id TEXT,
                    payment_method TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """,
            'api_keys': """
                CREATE TABLE api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    key_hash TEXT UNIQUE NOT NULL,
                    name TEXT,
                    minutes_limit FLOAT,
                    minutes_used FLOAT DEFAULT 0.0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_used_at DATETIME,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """
        }

        for table_name, create_sql in tables_to_create.items():
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if not cursor.fetchone():
                cursor.execute(create_sql)
                print(f"Создана таблица {table_name}")
            else:
                # Для таблицы plans проверяем наличие колонки price_stars
                if table_name == 'plans':
                    cursor.execute("PRAGMA table_info(plans)")
                    plan_columns = [col[1] for col in cursor.fetchall()]
                    if 'price_stars' not in plan_columns:
                        cursor.execute("ALTER TABLE plans ADD COLUMN price_stars INTEGER DEFAULT 0")
                        print("Добавлена колонка price_stars в таблицу plans")
                elif table_name == 'transactions':
                    cursor.execute("PRAGMA table_info(transactions)")
                    transaction_columns = [col[1] for col in cursor.fetchall()]
                    if 'currency' not in transaction_columns:
                        cursor.execute("ALTER TABLE transactions ADD COLUMN currency TEXT")
                        print("Добавлена колонка currency в таблицу transactions")
                    if 'provider_payment_charge_id' not in transaction_columns:
                        cursor.execute("ALTER TABLE transactions ADD COLUMN provider_payment_charge_id TEXT")
                        print("Добавлена колонка provider_payment_charge_id в таблицу transactions")
                    if 'telegram_payment_charge_id' not in transaction_columns:
                        cursor.execute("ALTER TABLE transactions ADD COLUMN telegram_payment_charge_id TEXT")
                        print("Добавлена колонка telegram_payment_charge_id в таблицу transactions")
                    if 'external_payment_id' not in transaction_columns:
                        cursor.execute("ALTER TABLE transactions ADD COLUMN external_payment_id TEXT")
                        print("Добавлена колонка external_payment_id в таблицу transactions")

        # Дополнительная проверка таблицы promo_codes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='promo_codes'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(promo_codes)")
            promo_columns = [col[1] for col in cursor.fetchall()]
            if 'bonus_type' not in promo_columns:
                cursor.execute("ALTER TABLE promo_codes ADD COLUMN bonus_type TEXT")
                print("Добавлена колонка bonus_type в таблицу promo_codes")
            if 'bonus_value' not in promo_columns:
                cursor.execute("ALTER TABLE promo_codes ADD COLUMN bonus_value TEXT")
                print("Добавлена колонка bonus_value в таблицу promo_codes")

        conn.commit()
        print("Миграция схемы базы данных завершена")

    except Exception as e:
        print(f"Ошибка при миграции схемы: {e}")
        conn.rollback()
        raise

def init_plans():
    """Инициализация планов по умолчанию"""
    from .models import DEFAULT_PLANS, Plan

    db = SessionLocal()
    try:
        for plan_data in DEFAULT_PLANS:
            existing_plan = db.query(Plan).filter(Plan.name == plan_data["name"]).first()
            if not existing_plan:
                plan = Plan(
                    name=plan_data["name"],
                    display_name=plan_data["display_name"],
                    minutes_per_month=plan_data["minutes_per_month"],
                    max_file_size_mb=plan_data["max_file_size_mb"],
                    price_rub=plan_data["price_rub"],
                    price_usd=plan_data["price_usd"],
                    price_stars=plan_data.get("price_stars", 0),
                    features=plan_data.get("features", ""),
                    is_active=plan_data.get("is_active", True)
                )
                db.add(plan)
            else:
                existing_plan.display_name = plan_data["display_name"]
                existing_plan.minutes_per_month = plan_data["minutes_per_month"]
                existing_plan.max_file_size_mb = plan_data["max_file_size_mb"]
                existing_plan.price_rub = plan_data["price_rub"]
                existing_plan.price_usd = plan_data["price_usd"]
                existing_plan.price_stars = plan_data.get("price_stars", existing_plan.price_stars)
                existing_plan.features = plan_data.get("features", existing_plan.features or "")
                existing_plan.is_active = plan_data.get("is_active", True)

        db.commit()

    except Exception as e:
        print(f"Ошибка при создании планов: {e}")
        db.rollback()
    finally:
        db.close()

def init_promo_codes():
    """Инициализация промокодов по умолчанию"""
    db = SessionLocal()
    try:
        promo_service = PromoCodeService(db)

        # Промокод на 3 дня безлимитного тарифа
        if not promo_service.get_promo_code("KITTY3D"):
            promo_service.create_promo_code(
                code="KITTY3D",
                plan_type=PlanType.UNLIMITED.value,
                duration_days=3,
                max_uses=999999,  # Практически безлимитный
                description="🎁 3 дня безлимитного тарифа",
                expires_at=datetime.utcnow() + timedelta(days=365)  # Действует год
            )

        # Бессрочный безлимитный тариф (VIP промокод)
        if not promo_service.get_promo_code("LIGHTKITTY"):
            promo_service.create_promo_code(
                code="LIGHTKITTY",
                plan_type=PlanType.UNLIMITED.value,
                duration_days=None,  # Бессрочный
                max_uses=None,  # Не ограничиваем количество использований
                description="🎉 Бессрочный безлимитный тариф",
                expires_at=datetime.utcnow() + timedelta(days=365)  # Действует год
            )

        if not promo_service.get_promo_code("BETACAT"):
            promo_service.create_promo_code(
                code="BETACAT",
                plan_type=PlanType.BETA.value,
                duration_days=60,
                max_uses=999999,
                description="🐱 Два месяца beta-доступа",
                expires_at=datetime.utcnow() + timedelta(days=365)
            )

    except Exception as e:
        print(f"Ошибка при создании промокодов: {e}")
    finally:
        db.close()

def _serialize_payload(payload: Optional[object]) -> Optional[str]:
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return str(payload)

def log_event(user: User | int | None, kind: str, payload: Optional[object] = None) -> None:
    """Записывает событие пользователя в таблицу events."""
    if user is None or not kind:
        return
    if isinstance(user, User):
        user_id = user.id
    else:
        user_id = int(user)
    if not user_id:
        return

    entry = Event(
        user_id=user_id,
        kind=kind,
        payload=_serialize_payload(payload),
        ts=datetime.utcnow(),
    )
    db = SessionLocal()
    try:
        db.add(entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning(
            "Failed to log event",
            extra={"user_id": user_id, "kind": kind, "error": str(exc)},
        )
    finally:
        db.close()

def log_telegram_event(telegram_user, kind: str, payload: Optional[object] = None) -> None:
    """Записывает событие, идентифицируя пользователя по данным Telegram."""
    if telegram_user is None or not kind:
        return
    db = SessionLocal()
    try:
        user_service = UserService(db)
        user = user_service.get_or_create_user(
            telegram_id=getattr(telegram_user, "id", None),
            username=getattr(telegram_user, "username", None),
            first_name=getattr(telegram_user, "first_name", None),
            last_name=getattr(telegram_user, "last_name", None),
        )
        log_event(user, kind, payload)
    except Exception as exc:
        logger.warning(
            "Failed to log telegram event",
            extra={
                "telegram_id": getattr(telegram_user, "id", None),
                "kind": kind,
                "error": str(exc),
            },
        )
    finally:
        db.close()

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> dict | None:
    """Получает существующего пользователя или создает нового, возвращает словарь полей."""
    try:
        db = SessionLocal()
        try:
            user_service = UserService(db)
            user = user_service.get_or_create_user(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
            )

            return {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'current_plan': user.current_plan,
                'plan_expires_at': user.plan_expires_at,
                'total_minutes_transcribed': user.total_minutes_transcribed,
                'minutes_used_this_month': user.minutes_used_this_month,
                'last_reset_date': user.last_reset_date,
                'total_generations': user.total_generations,
                'generations_used_this_month': user.generations_used_this_month,
                'created_at': user.created_at,
                'updated_at': user.updated_at,
                'is_active': user.is_active,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при работе с пользователем {telegram_id}: {e}")
        return None

def get_user_stats(telegram_id: int) -> dict:
    """Получает статистику пользователя."""
    try:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.telegram_id == telegram_id).first()
            if not user:
                return {
                    'subscription_status': 'Бесплатный',
                    'subscription_until': 'Не ограничено',
                    'files_processed': 0,
                    'minutes_transcribed': 0,
                    'total_characters': 0,
                    'last_activity': 'Никогда',
                    'files_remaining': '30 минут',
                    'avg_duration': 0,
                }

            current_plan = user.current_plan or PlanType.FREE.value
            used_this_month = user.minutes_used_this_month or 0.0
            total_minutes = user.total_minutes_transcribed or 0.0

            files_remaining = 'Безлимит'
            if current_plan == PlanType.FREE.value:
                files_remaining = f'{max(0, 30 - used_this_month):.0f} мин'

            return {
                'subscription_status': current_plan.capitalize(),
                'subscription_until': user.plan_expires_at or 'Не ограничено',
                'files_processed': total_minutes,
                'minutes_transcribed': total_minutes,
                'total_characters': 0,
                'last_activity': user.updated_at or 'Никогда',
                'files_remaining': files_remaining,
                'avg_duration': 0,
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при получении статистики для {telegram_id}: {e}")
        return {}

def activate_promo_code(telegram_id: int, promo_code: str) -> dict:
    """Активирует промокод для пользователя через сервисы SQLAlchemy."""
    try:
        db = SessionLocal()
        try:
            user_service = UserService(db)
            promo_service = PromoCodeService(db)

            user = user_service.get_or_create_user(telegram_id=telegram_id)

            is_valid, message, promo = promo_service.validate_promo_code(promo_code, user)
            if not is_valid or not promo:
                return {'success': False, 'error': message}

            activation = promo_service.activate_promo_code(promo, user)
            expires_date = activation.expires_at

            if promo.plan_type == PlanType.UNLIMITED.value:
                bonus_desc = (
                    f"{promo.duration_days} дней безлимитного тарифа"
                    if promo.duration_days
                    else "Бессрочный безлимитный тариф"
                )
            else:
                bonus_desc = promo.description or f"План {promo.plan_type}"

            return {
                'success': True,
                'bonus': bonus_desc,
                'expires': expires_date.strftime('%d.%m.%Y') if expires_date else 'Бессрочно'
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при активации промокода {promo_code} для {telegram_id}: {e}")
        return {'success': False, 'error': 'Внутренняя ошибка'}

def update_user_transcription_stats(telegram_id: int, file_name: str, file_size: int,
                                  duration: int, transcript: str):
    """Обновляет статистику пользователя после транскрипции."""
    try:
        db = SessionLocal()
        try:
            user_service = UserService(db)
            transcription_service = TranscriptionService(db)

            user = user_service.get_or_create_user(telegram_id=telegram_id)

            file_size_mb = float(file_size) / (1024 * 1024) if file_size else 0.0
            duration_minutes = float(duration) / 60 if duration else 0.0

            transcription_service.save_transcription(
                user=user,
                filename=file_name,
                file_size_mb=file_size_mb,
                audio_duration_minutes=duration_minutes,
                raw_transcript=transcript,
                formatted_transcript=transcript,
                processing_time=None,
                transcription_service="legacy",
                formatting_service="legacy",
            )

            user_service.add_usage(user, duration_minutes)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при обновлении статистики для {telegram_id}: {e}")

# Добавляем базовые промокоды при инициализации
def seed_promo_codes():
    """Добавляет базовые промокоды в базу данных."""
    try:
        db = SessionLocal()
        try:
            promo_service = PromoCodeService(db)

            promo_codes = [
                dict(
                    code='WELCOME10',
                    description='Скидка 10% на первую подписку',
                    plan_type=PlanType.PRO.value,
                    duration_days=None,
                    bonus_type='discount',
                    bonus_value='10%',
                    max_uses=100,
                    expires_at=None,
                ),
                dict(
                    code='PREMIUM30',
                    description='30 дней PRO подписки бесплатно',
                    plan_type=PlanType.PRO.value,
                    duration_days=30,
                    bonus_type='subscription',
                    bonus_value='30 дней PRO',
                    max_uses=50,
                    expires_at=None,
                ),
                dict(
                    code='CYBERKITTY',
                    description='Специальный бонус от CyberKitty',
                    plan_type=PlanType.UNLIMITED.value,
                    duration_days=None,
                    bonus_type='bonus',
                    bonus_value='Дополнительные функции',
                    max_uses=25,
                    expires_at=None,
                ),
                dict(
                    code='BETACAT',
                    description='Две недели beta-доступа',
                    plan_type=PlanType.BETA.value,
                    duration_days=14,
                    bonus_type='subscription',
                    bonus_value='14 дней Beta',
                    max_uses=500,
                    expires_at=None,
                ),
            ]

            for data in promo_codes:
                if promo_service.get_promo_code(data['code']) is None:
                    promo_service.create_promo_code(**data)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Ошибка при создании промокодов: {e}")

# ===== Реферальная программа =====
class ReferralService:
    """Операции по работе с реферальной программой."""

    COMMISSION_RATE = 0.30
    REFERRAL_PROMO_CODE = "REFERRAL_SUPERCAT"
    REFERRAL_PROMO_DURATION_DAYS = 14
    REFERRAL_PROMO_MAX_USES = 1_000_000

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _generate_referral_code() -> str:
        return secrets.token_urlsafe(6).replace("-", "").replace("_", "")

    def _generate_unique_code(self) -> str:
        for _ in range(10):
            code = self._generate_referral_code()
            if not self.db.query(ReferralLink).filter(ReferralLink.code == code).first():
                return code
        raise RuntimeError("Не удалось сгенерировать уникальный реферальный код")

    def create_or_get_referral_code(self, user: User) -> str:
        link = (
            self.db.query(ReferralLink)
            .filter(ReferralLink.user_telegram_id == user.telegram_id)
            .order_by(ReferralLink.id.desc())
            .first()
        )
        if link:
            return link.code

        code = self._generate_unique_code()
        link = ReferralLink(user_telegram_id=user.telegram_id, code=code)
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return code

    def record_referral_visit(
        self,
        referral_code: str,
        visitor_telegram_id: int | None,
        *,
        commit: bool = True,
    ) -> None:
        if not referral_code:
            return

        link_exists = (
            self.db.query(ReferralLink)
            .filter(ReferralLink.code == referral_code)
            .first()
        )
        if not link_exists:
            return

        visit = ReferralVisit(
            referral_code=referral_code,
            visitor_telegram_id=visitor_telegram_id,
        )
        self.db.add(visit)

        if visitor_telegram_id:
            exists = (
                self.db.query(ReferralAttribution)
                .filter(ReferralAttribution.visitor_telegram_id == visitor_telegram_id)
                .first()
            )
            if not exists:
                self.db.add(
                    ReferralAttribution(
                        visitor_telegram_id=visitor_telegram_id,
                        referral_code=referral_code,
                    )
                )

        if commit:
            self.db.commit()

    def attribute_user_referral(
        self,
        visitor_telegram_id: int,
        referral_code: str,
        *,
        commit: bool = True,
    ) -> None:
        if not referral_code:
            return

        link_exists = (
            self.db.query(ReferralLink)
            .filter(ReferralLink.code == referral_code)
            .first()
        )
        if not link_exists:
            return

        exists = (
            self.db.query(ReferralAttribution)
            .filter(ReferralAttribution.visitor_telegram_id == visitor_telegram_id)
            .first()
        )
        if exists:
            return

        self.db.add(
            ReferralAttribution(
                visitor_telegram_id=visitor_telegram_id,
                referral_code=referral_code,
            )
        )
        if commit:
            self.db.commit()

    def get_attribution_code_for_user(self, payer_telegram_id: int) -> str | None:
        record = (
            self.db.query(ReferralAttribution)
            .filter(ReferralAttribution.visitor_telegram_id == payer_telegram_id)
            .first()
        )
        return record.referral_code if record else None

    def record_referral_payment(
        self,
        user: User,
        amount_rub: float | None,
        *,
        commit: bool = False,
    ) -> Optional[ReferralPayment]:
        if amount_rub is None:
            return None

        referral_code = self.get_attribution_code_for_user(user.telegram_id)
        if not referral_code:
            return None

        payment = ReferralPayment(
            referral_code=referral_code,
            payer_telegram_id=user.telegram_id,
            amount_rub=float(amount_rub),
        )
        self.db.add(payment)

        if commit:
            self.db.commit()
            self.db.refresh(payment)

        try:
            log_event(
                user,
                "referral_commission_recorded",
                {
                    "referral_code": referral_code,
                    "amount_rub": float(amount_rub),
                    "commission_rate": self.COMMISSION_RATE,
                    "commission_amount": round(float(amount_rub) * self.COMMISSION_RATE, 2),
                },
            )
        except Exception:
            logger.debug("Failed to log referral commission", exc_info=True)

        return payment

    def get_referral_stats_for_user(self, user: User) -> dict:
        codes = [
            code
            for (code,) in self.db.query(ReferralLink.code).filter(
                ReferralLink.user_telegram_id == user.telegram_id
            )
        ]
        if not codes:
            return {"visits": 0, "paid_count": 0, "total_amount": 0.0, "balance": 0.0}

        visits = (
            self.db.query(func.count(ReferralVisit.id))
            .filter(ReferralVisit.referral_code.in_(codes))
            .scalar()
            or 0
        )
        paid_count, total_amount = (
            self.db.query(
                func.count(ReferralPayment.id),
                func.coalesce(func.sum(ReferralPayment.amount_rub), 0.0),
            )
            .filter(ReferralPayment.referral_code.in_(codes))
            .one()
        )

        total_amount = float(total_amount or 0.0)
        balance = round(total_amount * self.COMMISSION_RATE, 2)

        return {
            "visits": int(visits),
            "paid_count": int(paid_count or 0),
            "total_amount": total_amount,
            "balance": balance,
        }

    def apply_referral_welcome_bonus(self, user: User) -> bool:
        """Применить реферальный бонус: 14 дней beta-доступа"""
        # Проверяем, не был ли уже активирован бонус
        if user.current_plan != PlanType.FREE.value:
            return False
        
        # Даем 14 дней beta-доступа
        expires_at = datetime.utcnow() + timedelta(days=self.REFERRAL_PROMO_DURATION_DAYS)
        user.current_plan = PlanType.BETA.value
        user.plan_expires_at = expires_at
        user.beta_enabled = True
        
        # Сбрасываем месячное использование
        user.minutes_used_this_month = 0.0
        user.generations_used_this_month = 0
        user.last_reset_date = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(user)

        try:
            log_event(
                user,
                "referral_bonus_applied",
                {
                    "duration_days": self.REFERRAL_PROMO_DURATION_DAYS,
                    "plan_type": PlanType.BETA.value,
                    "expires_at": expires_at.isoformat(),
                },
            )
        except Exception:
            logger.debug("Failed to log referral bonus application", exc_info=True)

        return True
