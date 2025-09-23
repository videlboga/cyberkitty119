from sqlalchemy import Column, Integer, BigInteger, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from enum import Enum

Base = declarative_base()

class PlanType(str, Enum):
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
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

    # Связи
    transactions = relationship("Transaction", back_populates="user")
    transcriptions = relationship("Transcription", back_populates="user")

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
    max_uses = Column(Integer, default=1)  # Сколько раз можно использовать
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
        "features": '["3 генерации в месяц", "Файлы до 50 МБ", "Базовое качество"]'
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
        "price_rub": 299.0,
        "price_usd": 0.0,
        "price_stars": 230,
        "description": "Для бизнеса и работы",
        "features": '["10 часов в месяц", "Файлы до 500 МБ", "API доступ", "Приоритет"]'
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
