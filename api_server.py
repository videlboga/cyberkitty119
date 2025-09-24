#!/usr/bin/env python3
import asyncio
import os
import tempfile
import uuid
import time
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, Query
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import httpx

# Добавляем корневую директорию проекта в sys.path
import sys
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio, format_transcript_with_llm
    from transkribator_modules.audio.extractor import extract_audio_from_video
    from transkribator_modules.config import logger, BOT_TOKEN
    from transkribator_modules.db.database import (
        init_database, get_db, UserService, ApiKeyService, TranscriptionService,
        calculate_audio_duration, get_plans, SessionLocal
    )
    from transkribator_modules.db.models import User, ApiKey
    from transkribator_modules.google_api import GoogleCredentialService, parse_state
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

app = FastAPI(
    title="Transkribator API",
    description="API для транскрибации видео с системой монетизации",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализируем базу данных при запуске
init_database()

# Настраиваем webhook для ЮКассы
from transkribator_modules.bot.yukassa_webhook import setup_yukassa_webhook
setup_yukassa_webhook(app)

# Создаем временные директории
TEMP_DIR = Path("/tmp/transkribator")
TEMP_DIR.mkdir(exist_ok=True)

# Pydantic модели для API
class PlanInfo(BaseModel):
    name: str
    display_name: str
    minutes_per_month: Optional[float]
    max_file_size_mb: float
    price_rub: float
    price_usd: float
    description: str
    features: List[str]

class UserInfo(BaseModel):
    telegram_id: int
    username: Optional[str]
    current_plan: str
    plan_display_name: str
    minutes_used_this_month: float
    minutes_limit: Optional[float]
    minutes_remaining: float
    usage_percentage: float
    total_minutes_transcribed: float

class ApiKeyInfo(BaseModel):
    name: str
    created_at: str
    last_used_at: Optional[str]
    minutes_limit: Optional[float]
    minutes_used: float
    is_active: bool

class TranscriptionResult(BaseModel):
    task_id: str
    filename: str
    file_size_mb: float
    audio_duration_minutes: float
    raw_transcript: str
    formatted_transcript: str
    transcript_length: int
    processing_time_seconds: float
    formatted_with_llm: bool

# Dependency для проверки API ключа
async def verify_api_key(
    authorization: str = Header(None),
    x_api_key: str = Header(None),
    api_key: str = Query(None),
    db = Depends(get_db)
) -> tuple[User, Optional[ApiKey]]:
    """Проверка API ключа и возврат пользователя"""

    # Получаем ключ из разных источников
    key = None
    if authorization and authorization.startswith("Bearer "):
        key = authorization[7:]
    elif x_api_key:
        key = x_api_key
    elif api_key:
        key = api_key

    if not key:
        raise HTTPException(
            status_code=401,
            detail="API ключ не предоставлен. Используйте заголовок Authorization: Bearer <key> или X-API-Key"
        )

    api_key_service = ApiKeyService(db)
    api_key_obj = api_key_service.verify_api_key(key)

    if not api_key_obj:
        raise HTTPException(
            status_code=401,
            detail="Недействительный API ключ"
        )

    user_service = UserService(db)
    user = db.query(User).filter(User.id == api_key_obj.user_id).first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="Пользователь не найден или заблокирован"
        )

    return user, api_key_obj

@app.get("/")
async def root():
    """Главная страница API"""
    return {
        "message": "Transkribator API v2.0",
        "version": "2.0.0",
        "features": ["Транскрибация видео", "Система монетизации", "API ключи", "Лимиты пользователей"],
        "endpoints": {
            "/transcribe": "POST - Загрузить видео для транскрибации (требует API ключ)",
            "/plans": "GET - Список доступных тарифных планов",
            "/user/info": "GET - Информация о пользователе и использовании",
            "/user/api-keys": "GET - Список API ключей пользователя",
            "/webhook/yukassa": "POST - Webhook для обработки платежей ЮКассы",
            "/health": "GET - Проверка состояния сервиса"
        }
    }

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    return {"status": "healthy", "service": "transkribator-api", "version": "2.0.0"}


async def _notify_google_result(telegram_id: Optional[int], message: str) -> None:
    if not BOT_TOKEN or not telegram_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={"chat_id": telegram_id, "text": message})
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to notify user about Google OAuth result",
            extra={"error": str(exc), "telegram_id": telegram_id},
        )


def _html_response(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    content = f"""
    <html>
        <head>
            <meta charset='utf-8'/>
            <title>{title}</title>
            <style>body{{font-family:Arial,sans-serif;background:#0f172a;color:#e2e8f0;padding:40px;text-align:center}}a{{color:#38bdf8}}</style>
        </head>
        <body>
            <h1>{title}</h1>
            <p>{body}</p>
            <p>Можно вернуться в Telegram 🤖</p>
        </body>
    </html>
    """
    return HTMLResponse(content=content, status_code=status_code)


@app.get("/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    logger.info(
        "Google OAuth callback received",
        extra={"code_present": bool(code), "state": state, "error": error},
    )

    if error:
        return _html_response("Авторизация отклонена", f"Google вернул ошибку: {error}", status_code=400)

    if not code or not state:
        return _html_response("Ошибка", "Не найден параметр code/state в ответе Google", status_code=400)

    try:
        user_id, _ = parse_state(state)
    except ValueError as exc:
        logger.warning("Invalid Google OAuth state", extra={"error": str(exc)})
        return _html_response("Ошибка", "Некорректный state. Попробуйте начать авторизацию заново.", status_code=400)

    db = SessionLocal()
    telegram_id: Optional[int] = None
    try:
        user = db.query(User).filter(User.id == user_id).one_or_none()
        if not user:
            logger.error("User not found for Google OAuth", extra={"user_id": user_id})
            return _html_response("Ошибка", "Пользователь не найден. Попробуйте снова.", status_code=404)

        telegram_id = user.telegram_id

        google_service = GoogleCredentialService(db)
        flow = google_service.build_flow(state=state)
        flow.fetch_token(code=code)
        credentials = flow.credentials

        tokens = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }

        google_service.store_tokens(user_id, tokens, list(credentials.scopes or []))

        await _notify_google_result(
            telegram_id,
            "✅ Google Drive подключён. Возвращайся в Telegram — заметки будут сохраняться в Drive.",
        )

        return _html_response(
            "Google подключён",
            "Интеграция успешно настроена. Можно вернуться в чат с ботом.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Google OAuth callback failed",
            extra={"user_id": user_id, "error": str(exc)},
        )
        await _notify_google_result(
            telegram_id,
            "⚠️ Не удалось подключить Google. Попробуй ещё раз через личный кабинет.",
        )
        return _html_response(
            "Ошибка",
            "Не удалось завершить авторизацию. Попробуйте начать подключение заново.",
            status_code=500,
        )
    finally:
        db.close()

@app.get("/plans", response_model=List[PlanInfo])
async def get_plans_endpoint():
    """Получить список доступных тарифных планов"""
    plans = get_plans()
    result = []

    for plan in plans:
        features = []
        if plan.features:
            import json
            try:
                features = json.loads(plan.features)
            except:
                features = [plan.features]

        result.append(PlanInfo(
            name=plan.name,
            display_name=plan.display_name,
            minutes_per_month=plan.minutes_per_month,
            max_file_size_mb=plan.max_file_size_mb,
            price_rub=plan.price_rub,
            price_usd=plan.price_usd,
            description=plan.description or "",
            features=features
        ))

    return result

@app.get("/user/info", response_model=UserInfo)
async def get_user_info(user_and_key: tuple = Depends(verify_api_key)):
    """Получить информацию о пользователе и его использовании"""
    user, api_key = user_and_key
    db = next(get_db())

    user_service = UserService(db)
    usage_info = user_service.get_usage_info(user)

    return UserInfo(
        telegram_id=user.telegram_id,
        username=user.username,
        current_plan=usage_info["current_plan"],
        plan_display_name=usage_info["plan_display_name"],
        minutes_used_this_month=usage_info["minutes_used_this_month"],
        minutes_limit=usage_info["minutes_limit"],
        minutes_remaining=usage_info["minutes_remaining"],
        usage_percentage=usage_info["usage_percentage"],
        total_minutes_transcribed=usage_info["total_minutes_transcribed"]
    )

@app.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_video(
    file: UploadFile = File(...),
    format_with_llm: bool = True,
    user_and_key: tuple = Depends(verify_api_key)
):
    """
    Транскрибирует загруженное видео с проверкой лимитов

    - **file**: Видеофайл для транскрибации
    - **format_with_llm**: Форматировать ли результат с помощью LLM (по умолчанию True)
    """
    user, api_key = user_and_key
    db = next(get_db())

    # Проверяем тип файла по расширению и content_type
    video_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
    audio_extensions = {'.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.wma'}

    file_extension = Path(file.filename).suffix.lower() if file.filename else ''
    is_valid_extension = file_extension in video_extensions or file_extension in audio_extensions
    is_valid_content_type = file.content_type and file.content_type.startswith(('video/', 'audio/'))

    if not (is_valid_extension or is_valid_content_type):
        raise HTTPException(
            status_code=400,
            detail="Поддерживаются только видео и аудио файлы"
        )

    # Генерируем уникальный ID для обработки
    task_id = str(uuid.uuid4())
    start_time = time.time()
    logger.info(f"Начинаю обработку файла {file.filename}, task_id: {task_id}, пользователь: {user.telegram_id}")

    # Создаем временные файлы
    temp_video_path = TEMP_DIR / f"{task_id}_video"
    temp_audio_path = TEMP_DIR / f"{task_id}_audio.wav"

    try:
        # Сохраняем загруженный файл
        logger.info(f"Сохраняю загруженный файл: {file.filename}")
        with open(temp_video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        file_size_mb = len(content) / (1024 * 1024)
        logger.info(f"Файл сохранен, размер: {file_size_mb:.1f} МБ")

        # Проверяем лимиты размера файла
        user_service = UserService(db)
        plan = user_service.get_user_plan(user)

        if plan and file_size_mb > plan.max_file_size_mb:
            raise HTTPException(
                status_code=413,
                detail=f"Файл слишком большой. Максимальный размер для вашего плана: {plan.max_file_size_mb} МБ"
            )

        # Оцениваем длительность аудио
        estimated_duration = calculate_audio_duration(file_size_mb)

        # Проверяем лимиты пользователя
        can_use, limit_message = user_service.check_usage_limit(user, estimated_duration)
        if not can_use:
            raise HTTPException(
                status_code=429,
                detail=f"Превышен лимит использования: {limit_message}"
            )

        # Проверяем лимиты API ключа
        if api_key:
            api_key_service = ApiKeyService(db)
            can_use_api, api_limit_message = api_key_service.check_api_key_limits(api_key, estimated_duration)
            if not can_use_api:
                raise HTTPException(
                    status_code=429,
                    detail=f"Превышен лимит API ключа: {api_limit_message}"
                )

        # Извлекаем аудио из видео
        logger.info("Извлекаю аудио из видео...")
        success = await extract_audio_from_video(temp_video_path, temp_audio_path)

        if not success or not temp_audio_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Не удалось извлечь аудио из видеофайла"
            )

        audio_size_mb = temp_audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"Аудио извлечено, размер: {audio_size_mb:.1f} МБ")

        # Более точный расчет длительности после извлечения аудио
        actual_duration = calculate_audio_duration(audio_size_mb)

        # Транскрибируем аудио (с разбивкой на сегменты для больших файлов)
        logger.info("Начинаю транскрибацию через DeepInfra API...")
        raw_transcript = await transcribe_audio(temp_audio_path)

        if not raw_transcript:
            raise HTTPException(
                status_code=500,
                detail="Не удалось получить транскрипцию от API"
            )

        logger.info(f"Получена сырая транскрипция длиной {len(raw_transcript)} символов")

        # Форматируем транскрипцию, если требуется
        formatted_transcript = raw_transcript
        formatting_service = None

        if format_with_llm:
            logger.info("Форматирую транскрипцию с помощью LLM...")
            try:
                formatted_result = await format_transcript_with_llm(raw_transcript)
                if formatted_result and formatted_result != raw_transcript:
                    formatted_transcript = formatted_result
                    formatting_service = "openrouter"
                    logger.info("Транскрипция отформатирована")
                else:
                    logger.info("Форматирование не изменило текст или не удалось")
            except Exception as e:
                logger.warning(f"Ошибка при форматировании: {e}, используем сырую транскрипцию")

        processing_time = time.time() - start_time

        # Сохраняем результат в базу данных
        transcription_service = TranscriptionService(db)
        transcription_record = transcription_service.save_transcription(
            user=user,
            filename=file.filename,
            file_size_mb=file_size_mb,
            audio_duration_minutes=actual_duration,
            raw_transcript=raw_transcript,
            formatted_transcript=formatted_transcript,
            processing_time=processing_time,
            transcription_service="deepinfra",
            formatting_service=formatting_service or "none"
        )

        # Обновляем использование (минуты или генерации)
        user_service.add_usage(user, actual_duration)

        # Обновляем использованные минуты для API ключа
        if api_key:
            api_key_service.add_api_key_usage(api_key, actual_duration)

        # Возвращаем результат
        result = TranscriptionResult(
            task_id=task_id,
            filename=file.filename,
            file_size_mb=round(file_size_mb, 2),
            audio_duration_minutes=round(actual_duration, 2),
            raw_transcript=raw_transcript,
            formatted_transcript=formatted_transcript,
            transcript_length=len(formatted_transcript),
            processing_time_seconds=round(processing_time, 2),
            formatted_with_llm=format_with_llm and (formatted_transcript != raw_transcript)
        )

        logger.info(f"Транскрибация завершена успешно, task_id: {task_id}, время: {processing_time:.1f}с")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обработке файла {file.filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

    finally:
        # Очищаем временные файлы
        try:
            if temp_video_path.exists():
                temp_video_path.unlink()
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            logger.info(f"Временные файлы очищены для task_id: {task_id}")
        except Exception as e:
            logger.warning(f"Не удалось очистить временные файлы: {e}")

if __name__ == "__main__":
    # Запускаем сервер
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
