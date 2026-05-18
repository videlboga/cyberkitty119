"""
Утилиты для автоматического логирования событий пользователей.
"""

import functools
from typing import Optional, Dict, Any, Callable
from telegram import Update
from telegram.ext import ContextTypes

from transkribator_modules.db.database import log_event, SessionLocal, UserService
from transkribator_modules.config import logger

try:
    from transkribator_modules.utils.error_notifier import notify_error
    ERROR_NOTIFIER_AVAILABLE = True
except ImportError:
    ERROR_NOTIFIER_AVAILABLE = False
    notify_error = None


def log_user_action(event_kind: str, extract_payload: Optional[Callable] = None):
    """
    Декоратор для автоматического логирования действий пользователя.
    
    Args:
        event_kind: Тип события (например, "bot_command_start")
        extract_payload: Опциональная функция для извлечения payload из аргументов
    
    Пример использования:
        @log_user_action("bot_command_start")
        async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
            
        @log_user_action("bot_button_process_transcript", lambda u, c: {"note_id": c.user_data.get("note_id")})
        async def process_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
            ...
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Выполняем оригинальную функцию
            result = await func(update, context, *args, **kwargs)
            
            # Логируем событие
            try:
                db = SessionLocal()
                try:
                    user_service = UserService(db)
                    db_user = user_service.get_or_create_user(
                        telegram_id=update.effective_user.id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name,
                    )
                    
                    # Извлекаем payload если предоставлена функция
                    payload = None
                    if extract_payload:
                        try:
                            payload = extract_payload(update, context)
                        except Exception:
                            payload = None
                    
                    # Логируем
                    log_event(db_user, event_kind, payload)
                    
                finally:
                    db.close()
            except Exception as exc:
                logger.debug(f"Failed to log event {event_kind}", extra={"error": str(exc)})
            
            return result
        return wrapper
    return decorator


def log_callback_action(event_prefix: str = "bot_button_"):
    """
    Декоратор для логирования callback query.
    Автоматически извлекает callback_data и использует его как event_kind.
    
    Args:
        event_prefix: Префикс для event_kind (по умолчанию "bot_button_")
    
    Пример:
        @log_callback_action()
        async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            # callback_data будет залогирован автоматически
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Выполняем оригинальную функцию
            result = await func(update, context, *args, **kwargs)
            
            # Логируем событие
            try:
                if update.callback_query and update.callback_query.data:
                    callback_data = update.callback_query.data
                    # Убираем user_id из callback_data если есть
                    clean_callback = callback_data.split("_")[:-1] if callback_data.endswith(f"_{update.effective_user.id}") else [callback_data]
                    event_kind = event_prefix + "_".join(clean_callback)
                    
                    db = SessionLocal()
                    try:
                        user_service = UserService(db)
                        db_user = user_service.get_or_create_user(
                            telegram_id=update.effective_user.id,
                            username=update.effective_user.username,
                            first_name=update.effective_user.first_name,
                            last_name=update.effective_user.last_name,
                        )
                        
                        payload = {"callback_data": callback_data}
                        log_event(db_user, event_kind, payload)
                        
                    finally:
                        db.close()
            except Exception as exc:
                logger.debug(f"Failed to log callback event", extra={"error": str(exc)})
            
            return result
        return wrapper
    return decorator


def log_media_event(media_type: str):
    """
    Декоратор для логирования получения медиафайлов.
    
    Args:
        media_type: Тип медиа ("video" или "audio")
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Логируем получение
            try:
                db = SessionLocal()
                try:
                    user_service = UserService(db)
                    db_user = user_service.get_or_create_user(
                        telegram_id=update.effective_user.id,
                        username=update.effective_user.username,
                        first_name=update.effective_user.first_name,
                        last_name=update.effective_user.last_name,
                    )
                    
                    event_kind = f"bot_media_{media_type}_received"
                    file_info = {}
                    
                    if media_type == "video" and update.message.video:
                        file_info = {
                            "file_id": update.message.video.file_id,
                            "file_size": update.message.video.file_size,
                            "duration": update.message.video.duration,
                            "mime_type": update.message.video.mime_type
                        }
                    elif media_type == "audio" and update.message.audio:
                        file_info = {
                            "file_id": update.message.audio.file_id,
                            "file_size": update.message.audio.file_size,
                            "duration": update.message.audio.duration,
                            "mime_type": update.message.audio.mime_type
                        }
                    
                    log_event(db_user, event_kind, file_info)
                    
                finally:
                    db.close()
            except Exception as exc:
                logger.debug(f"Failed to log media event", extra={"error": str(exc)})
            
            # Выполняем оригинальную функцию
            result = await func(update, context, *args, **kwargs)
            return result
        return wrapper
    return decorator


def safe_log_event(user_or_id, event_kind: str, payload: Optional[Dict[str, Any]] = None):
    """
    Безопасное логирование события без прерывания основного потока выполнения.
    
    Args:
        user_or_id: Объект User или telegram_id
        event_kind: Тип события
        payload: Опциональные данные события
    """
    try:
        log_event(user_or_id, event_kind, payload)
    except Exception as exc:
        logger.debug(f"Failed to log event {event_kind}", extra={"error": str(exc)})


async def log_and_notify_error(
    exception: Exception,
    user_id: Optional[int] = None,
    context: Optional[Dict[str, Any]] = None,
    error_kind: str = "error_critical"
):
    """
    Логирует ошибку в БД и отправляет уведомление в Telegram.
    
    Args:
        exception: Объект исключения
        user_id: ID пользователя (опционально)
        context: Дополнительный контекст
        error_kind: Тип события ошибки (по умолчанию "error_critical")
        
    Example:
        try:
            # some code
        except Exception as e:
            await log_and_notify_error(
                e,
                user_id=user.telegram_id,
                context={"endpoint": "/api/transcribe"},
                error_kind="error_transcription"
            )
    """
    # Логируем в БД
    payload = context.copy() if context else {}
    payload["error_type"] = type(exception).__name__
    payload["error_message"] = str(exception)
    payload["severity"] = "critical"
    
    if user_id:
        safe_log_event(user_id, error_kind, payload)
    else:
        safe_log_event(None, error_kind, payload)
    
    # Отправляем уведомление в Telegram
    if ERROR_NOTIFIER_AVAILABLE and notify_error:
        try:
            full_context = context.copy() if context else {}
            if user_id:
                full_context["user_id"] = user_id
            await notify_error(exception, full_context, severity="critical")
        except Exception as notify_exc:
            logger.error(f"Failed to send error notification: {notify_exc}")

