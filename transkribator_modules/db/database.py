"""
Модуль для работы с базой данных CyberKitty Transkribator
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import sqlite3
from pathlib import Path
from transkribator_modules.config import logger

from .models import Base, User, Plan, Transaction, Transcription, ApiKey, PromoCode, PromoActivation, DEFAULT_PLANS, PlanType

# Настройка базы данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./transkribator.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Путь к файлу базы данных
DB_PATH = Path("data/transkribator.db")

def init_database():
    """Инициализирует базу данных и создает необходимые таблицы."""
    try:
        # Создаем директорию для данных если не существует
        DB_PATH.parent.mkdir(exist_ok=True)
        
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
    
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    subscription_type TEXT DEFAULT 'basic',
                    subscription_until DATETIME,
                    files_processed INTEGER DEFAULT 0,
                    minutes_transcribed INTEGER DEFAULT 0,
                    total_characters INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица транскрипций
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    file_name TEXT,
                    file_size INTEGER,
                    duration INTEGER,
                    transcript TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            # Таблица промокодов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    description TEXT,
                    bonus_type TEXT,
                    bonus_value TEXT,
                    max_uses INTEGER DEFAULT 1,
                    current_uses INTEGER DEFAULT 0,
                    expires_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Таблица использованных промокодов
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS used_promos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    promo_code_id INTEGER,
                    used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes (id)
                )
            """)
            
            conn.commit()
            logger.info("База данных инициализирована успешно")
            
        # Инициализируем промокоды
        seed_promo_codes()
            
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

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
                current_plan=PlanType.FREE
            )
            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)
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
        
        return user
    
    def check_minutes_limit(self, user: User, minutes_needed: float) -> tuple[bool, str]:
        """Проверить, может ли пользователь использовать указанное количество минут"""
        # Сбрасываем счетчик, если прошел месяц
        self._reset_monthly_usage_if_needed(user)
        
        plan = self.get_user_plan(user)
        if not plan:
            return False, "План пользователя не найден"
        
        # Безлимитный план
        if plan.minutes_per_month is None:
            return True, "Безлимитный план"
        
        # Проверяем лимит
        if user.minutes_used_this_month + minutes_needed > plan.minutes_per_month:
            remaining = max(0, plan.minutes_per_month - user.minutes_used_this_month)
            return False, f"Превышен лимит плана. Осталось: {remaining:.1f} мин"
        
        return True, "Лимит не превышен"
    
    def add_minutes_usage(self, user: User, minutes_used: float) -> None:
        """Добавить использованные минуты"""
        self._reset_monthly_usage_if_needed(user)
        user.minutes_used_this_month += minutes_used
        user.total_minutes_transcribed += minutes_used
        user.updated_at = datetime.utcnow()
        self.db.commit()
    
    def get_user_plan(self, user: User) -> Optional[Plan]:
        """Получить текущий план пользователя"""
        return self.db.query(Plan).filter(Plan.name == user.current_plan).first()
    
    def get_usage_info(self, user: User) -> dict:
        """Получить информацию об использовании"""
        self._reset_monthly_usage_if_needed(user)
        plan = self.get_user_plan(user)
        
        info = {
            "current_plan": user.current_plan,
            "plan_display_name": plan.display_name if plan else "Неизвестный",
            "minutes_used_this_month": user.minutes_used_this_month,
            "total_minutes_transcribed": user.total_minutes_transcribed,
            "plan_expires_at": user.plan_expires_at
        }
        
        if plan and plan.minutes_per_month is not None:
            info["minutes_limit"] = plan.minutes_per_month
            info["minutes_remaining"] = max(0, plan.minutes_per_month - user.minutes_used_this_month)
            info["usage_percentage"] = (user.minutes_used_this_month / plan.minutes_per_month) * 100
        else:
            info["minutes_limit"] = None
            info["minutes_remaining"] = float('inf')
            info["usage_percentage"] = 0
        
        return info
    
    def upgrade_user_plan(self, user: User, new_plan: str, transaction_id: int = None) -> bool:
        """Обновить план пользователя"""
        plan = self.db.query(Plan).filter(Plan.name == new_plan).first()
        if not plan:
            return False
        
        user.current_plan = new_plan
        user.plan_expires_at = datetime.utcnow() + timedelta(days=30)  # 30 дней
        user.updated_at = datetime.utcnow()
        
        # Если переходим на новый план, сбрасываем месячное использование
        if new_plan != PlanType.FREE:
            user.minutes_used_this_month = 0.0
            user.last_reset_date = datetime.utcnow()
        
        self.db.commit()
        return True
    
    def _reset_monthly_usage_if_needed(self, user: User) -> None:
        """Сбросить месячное использование, если прошел месяц"""
        if user.last_reset_date:
            days_since_reset = (datetime.utcnow() - user.last_reset_date).days
            if days_since_reset >= 30:
                user.minutes_used_this_month = 0.0
                user.last_reset_date = datetime.utcnow()
                self.db.commit()

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

class TransactionService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_transaction(self, user: User, plan_purchased: str, 
                          amount_rub: float = None, amount_usd: float = None, 
                          amount_stars: int = None, currency: str = "RUB",
                          payment_provider: str = None,
                          provider_payment_charge_id: str = None,
                          telegram_payment_charge_id: str = None,
                          metadata: str = None) -> Transaction:
        """Создать новую транзакцию"""
        transaction = Transaction(
            user_id=user.id,
            plan_purchased=plan_purchased,
            amount_rub=amount_rub,
            amount_usd=amount_usd,
            amount_stars=amount_stars,
            currency=currency,
            payment_provider=payment_provider,
            provider_payment_charge_id=provider_payment_charge_id,
            telegram_payment_charge_id=telegram_payment_charge_id,
            transaction_metadata=metadata,
            status="completed",  # Для Telegram Stars сразу completed
            completed_at=datetime.utcnow()
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
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
                         expires_at: datetime = None) -> PromoCode:
        """Создать новый промокод"""
        promo = PromoCode(
            code=code.upper(),
            plan_type=plan_type,
            duration_days=duration_days,
            max_uses=max_uses,
            description=description,
            expires_at=expires_at
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
        
        if existing_activation:
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
        if expires_at:
            user.plan_expires_at = expires_at
        else:
            user.plan_expires_at = None  # Бессрочный
        
        # Сбрасываем месячное использование при активации нового плана
        user.minutes_used_this_month = 0.0
        user.last_reset_date = datetime.utcnow()
        
        self.db.add(activation)
        self.db.commit()
        self.db.refresh(activation)
        
        return activation
    
    def get_user_active_promos(self, user: User) -> List[PromoActivation]:
        """Получить активные промокоды пользователя"""
        return self.db.query(PromoActivation).filter(
            PromoActivation.user_id == user.id,
            (PromoActivation.expires_at == None) | (PromoActivation.expires_at > datetime.utcnow())
        ).all()

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

def init_promo_codes():
    """Инициализация промокодов по умолчанию"""
    db = SessionLocal()
    try:
        promo_service = PromoCodeService(db)
        
        # Промокод на 3 дня безлимитного тарифа
        if not promo_service.get_promo_code("KITTY3D"):
            promo_service.create_promo_code(
                code="KITTY3D",
                plan_type=PlanType.UNLIMITED,
                duration_days=3,
                max_uses=999999,  # Практически безлимитный
                description="🎁 3 дня безлимитного тарифа",
                expires_at=datetime.utcnow() + timedelta(days=365)  # Действует год
            )
        
        # Бессрочный безлимитный тариф (VIP промокод)
        if not promo_service.get_promo_code("LIGHTKITTY"):
            promo_service.create_promo_code(
                code="LIGHTKITTY", 
                plan_type=PlanType.UNLIMITED,
                duration_days=None,  # Бессрочный
                max_uses=999999,  # Практически безлимитный
                description="🎉 Бессрочный безлимитный тариф",
                expires_at=datetime.utcnow() + timedelta(days=365)  # Действует год
            )
            
    except Exception as e:
        print(f"Ошибка при создании промокодов: {e}")
    finally:
        db.close() 

def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> dict:
    """Получает существующего пользователя или создает нового."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Пытаемся найти пользователя
            cursor.execute(
                "SELECT * FROM users WHERE telegram_id = ?", 
                (telegram_id,)
            )
            user = cursor.fetchone()
            
            if user:
                # Обновляем последнюю активность
                cursor.execute(
                    "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                    (telegram_id,)
                )
                conn.commit()
                
                columns = ['id', 'telegram_id', 'username', 'first_name', 'subscription_type', 
                          'subscription_until', 'files_processed', 'minutes_transcribed', 
                          'total_characters', 'created_at', 'last_activity']
                return dict(zip(columns, user))
            else:
                # Создаем нового пользователя
                cursor.execute("""
                    INSERT INTO users (telegram_id, username, first_name)
                    VALUES (?, ?, ?)
                """, (telegram_id, username, first_name))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                return {
                    'id': user_id,
                    'telegram_id': telegram_id,
                    'username': username,
                    'first_name': first_name,
                    'subscription_type': 'basic',
                    'subscription_until': None,
                    'files_processed': 0,
                    'minutes_transcribed': 0,
                    'total_characters': 0,
                    'created_at': datetime.now(),
                    'last_activity': datetime.now()
                }
                
    except Exception as e:
        logger.error(f"Ошибка при работе с пользователем {telegram_id}: {e}")
        return None

def get_user_stats(telegram_id: int) -> dict:
    """Получает статистику пользователя."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT subscription_type, subscription_until, files_processed, 
                       minutes_transcribed, total_characters, last_activity
                FROM users WHERE telegram_id = ?
            """, (telegram_id,))
            
            result = cursor.fetchone()
            
            if result:
                subscription_type, subscription_until, files_processed, minutes_transcribed, total_characters, last_activity = result
                
                return {
                    'subscription_status': subscription_type.capitalize() if subscription_type else 'Базовый',
                    'subscription_until': subscription_until or 'Не ограничено',
                    'files_processed': files_processed or 0,
                    'minutes_transcribed': minutes_transcribed or 0,
                    'total_characters': total_characters or 0,
                    'last_activity': last_activity or 'Никогда',
                    'files_remaining': 'Безлимит' if subscription_type != 'basic' else '30 минут',
                    'avg_duration': (minutes_transcribed // files_processed) if files_processed > 0 else 0
                }
            else:
                return {
                    'subscription_status': 'Базовый',
                    'subscription_until': 'Не ограничено',
                    'files_processed': 0,
                    'minutes_transcribed': 0,
                    'total_characters': 0,
                    'last_activity': 'Никогда',
                    'files_remaining': '30 минут',
                    'avg_duration': 0
                }
                
    except Exception as e:
        logger.error(f"Ошибка при получении статистики для {telegram_id}: {e}")
        return {}

def activate_promo_code(telegram_id: int, promo_code: str) -> dict:
    """Активирует промокод для пользователя."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Проверяем существование промокода
            cursor.execute("""
                SELECT id, description, bonus_type, bonus_value, max_uses, current_uses, expires_at
                FROM promo_codes WHERE code = ?
            """, (promo_code,))
            
            promo = cursor.fetchone()
            
            if not promo:
                return {'success': False, 'error': 'Промокод не найден'}
            
            promo_id, description, bonus_type, bonus_value, max_uses, current_uses, expires_at = promo
            
            # Проверяем, не истек ли промокод
            if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
                return {'success': False, 'error': 'Промокод истек'}
            
            # Проверяем лимит использований
            if current_uses >= max_uses:
                return {'success': False, 'error': 'Промокод исчерпан'}
            
            # Проверяем, не использовал ли пользователь этот промокод
            cursor.execute("""
                SELECT id FROM used_promos 
                WHERE user_id = (SELECT id FROM users WHERE telegram_id = ?) 
                AND promo_code_id = ?
            """, (telegram_id, promo_id))
            
            if cursor.fetchone():
                return {'success': False, 'error': 'Промокод уже использован'}
            
            # Получаем пользователя
            user = get_or_create_user(telegram_id)
            if not user:
                return {'success': False, 'error': 'Ошибка пользователя'}
            
            # Применяем бонус (пока только заглушка)
            if bonus_type == 'subscription':
                # Здесь можно добавить логику обновления подписки
                pass
            
            # Записываем использование промокода
            cursor.execute("""
                INSERT INTO used_promos (user_id, promo_code_id)
                VALUES (?, ?)
            """, (user['id'], promo_id))
            
            # Увеличиваем счетчик использований
            cursor.execute("""
                UPDATE promo_codes SET current_uses = current_uses + 1
                WHERE id = ?
            """, (promo_id,))
            
            conn.commit()
            
            return {
                'success': True,
                'bonus': description or bonus_value,
                'expires': expires_at or 'Не ограничено'
            }
            
    except Exception as e:
        logger.error(f"Ошибка при активации промокода {promo_code} для {telegram_id}: {e}")
        return {'success': False, 'error': 'Внутренняя ошибка'}

def update_user_transcription_stats(telegram_id: int, file_name: str, file_size: int, 
                                  duration: int, transcript: str):
    """Обновляет статистику пользователя после транскрипции."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Получаем пользователя
            user = get_or_create_user(telegram_id)
            if not user:
                return
            
            # Добавляем запись о транскрипции
            cursor.execute("""
                INSERT INTO transcriptions (user_id, file_name, file_size, duration, transcript)
                VALUES (?, ?, ?, ?, ?)
            """, (user['id'], file_name, file_size, duration, transcript))
            
            # Обновляем статистику пользователя
            cursor.execute("""
                UPDATE users SET 
                    files_processed = files_processed + 1,
                    minutes_transcribed = minutes_transcribed + ?,
                    total_characters = total_characters + ?,
                    last_activity = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (duration // 60, len(transcript), user['id']))
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Ошибка при обновлении статистики для {telegram_id}: {e}")

# Добавляем базовые промокоды при инициализации
def seed_promo_codes():
    """Добавляет базовые промокоды в базу данных."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            promo_codes = [
                ('WELCOME10', 'Скидка 10% на первую подписку', 'discount', '10%', 100, None),
                ('PREMIUM30', '30 дней PRO подписки бесплатно', 'subscription', '30 дней PRO', 50, None),
                ('CYBERKITTY', 'Специальный бонус от CyberKitty', 'bonus', 'Дополнительные функции', 25, None)
            ]
            
            for code, description, bonus_type, bonus_value, max_uses, expires_at in promo_codes:
                cursor.execute("""
                    INSERT OR IGNORE INTO promo_codes 
                    (code, description, bonus_type, bonus_value, max_uses, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (code, description, bonus_type, bonus_value, max_uses, expires_at))
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"Ошибка при создании промокодов: {e}") 