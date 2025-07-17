#!/usr/bin/env python3
import asyncio
import os
import tempfile
import uuid
import time
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  # для раздачи сегментов аудио
from pydantic import BaseModel
import uvicorn
import httpx

# Добавляем корневую директорию проекта в sys.path
import sys
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.transcribe.transcriber import transcribe_audio, format_transcript_with_llm
    from transkribator_modules.audio.extractor import extract_audio_from_video
    from transkribator_modules.config import logger, BOT_TOKEN, MAX_MESSAGE_LENGTH, YUKASSA_WEBHOOK_SECRET
    from transkribator_modules.db.database import (
        init_database, get_db, UserService, ApiKeyService, TranscriptionService, 
        calculate_audio_duration, get_plans, DeepInfraJobService
    )
    from transkribator_modules.db.models import User, ApiKey
    
    # Импортируем ЮKassa сервис
    try:
        from transkribator_modules.payments.yukassa import YukassaPaymentService
        YUKASSA_AVAILABLE = True
    except ImportError:
        YUKASSA_AVAILABLE = False
        logger.warning("ЮKassa SDK не установлен")
        
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

# Создаем временные директории
TEMP_DIR = Path("/tmp/transkribator")
TEMP_DIR.mkdir(exist_ok=True)

# Pydantic модели для API
class PlanInfo(BaseModel):
    name: str
    display_name: str
    minutes_per_month: Optional[float]
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
            "/health": "GET - Проверка состояния сервиса"
        }
    }

@app.get("/health")
async def health_check():
    """Проверка состояния сервиса"""
    return {"status": "healthy", "service": "transkribator-api", "version": "2.0.0"}

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
        
        # Инициализируем сервисы
        user_service = UserService(db)
        
        # Оцениваем длительность аудио
        estimated_duration = calculate_audio_duration(file_size_mb)
        
        # Проверяем лимиты пользователя
        can_use, limit_message = user_service.check_minutes_limit(user, estimated_duration)
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
            formatting_service=formatting_service
        )
        
        # Обновляем использованные минуты
        user_service.add_minutes_usage(user, actual_duration)
        
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

# ---------------------------------------------------------------------------
# DeepInfra webhook (асинхронный вывод моделей)
# ---------------------------------------------------------------------------

# DeepInfra делает предварительный HEAD-запрос, чтобы убедиться, что URL достижим
# (документация: https://deepinfra.com/docs/advanced/webhooks). FastAPI по
# умолчанию отвечает 405, из-за чего DeepInfra помечает webhook как недоступный
# и удаляет задачу. Добавляем обработчик, который просто возвращает 200 OK.

@app.head("/deepinfra-webhook")
async def deepinfra_webhook_head():
    return Response(status_code=200)

@app.post("/deepinfra-webhook")
async def deepinfra_webhook(request: Request, db = Depends(get_db)):
    """Принимает callback DeepInfra и сохраняет результат в БД.

    DeepInfra отправляет JSON с полями:
        request_id, inference_status.status, text, ...
    Мы сохраняем их в таблицу deepinfra_jobs, чтобы бот/клиенты смогли
    позднее забрать готовую транскрипцию.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    request_id = payload.get("request_id") or payload.get("id")
    status = payload.get("inference_status", {}).get("status", "unknown")
    text = payload.get("text") or ""
    model = payload.get("model") or payload.get("model_name")

    if not request_id:
        raise HTTPException(status_code=400, detail="Missing request_id")

    # Сохраняем в БД
    job_service = DeepInfraJobService(db)
    job_service.save_or_update_job(request_id, status, text, model)

    # --- Обработка Telegram callback --------------------------------------
    chat_id = request.query_params.get("chat_id")
    msg_id = request.query_params.get("msg_id")

    if status == "succeeded" and text and BOT_TOKEN and chat_id:
        # 1. Форматируем через LLM (best-effort)
        try:
            formatted = await format_transcript_with_llm(text)
            if formatted and len(formatted) >= len(text) * 0.9:
                text_to_send = formatted
            else:
                text_to_send = text
        except Exception as e:
            logger.warning(f"LLM format failed: {e}")
            text_to_send = text

        # Ограничиваем длину, иначе Telegram ругнётся
        if len(text_to_send) > MAX_MESSAGE_LENGTH:
            text_to_send = text_to_send[: MAX_MESSAGE_LENGTH - 10] + "…"

        base_url = os.getenv("TELEGRAM_API_URL", "http://telegram-bot-api:8081/bot")
        api_url = f"{base_url}{BOT_TOKEN}/editMessageText" if msg_id else f"{base_url}{BOT_TOKEN}/sendMessage"

        payload_send = {
            "chat_id": int(chat_id),
            "text": text_to_send,
            "parse_mode": None,
            "disable_web_page_preview": True,
        }
        if msg_id:
            payload_send["message_id"] = int(msg_id)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(api_url, json=payload_send)
                logger.info(f"Telegram API response {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Failed to send Telegram message: {e}")

    return {"ok": True, "request_id": request_id, "status": status}

@app.get("/transcription/{task_id}/status")
async def get_transcription_status(task_id: str, db = Depends(get_db)):
    """Получить статус транскрибации по task_id"""
    try:
        # Ищем задачу в базе данных
        job_service = DeepInfraJobService(db)
        job = job_service.get_job_by_request_id(task_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Задача {task_id} не найдена")
            
        return {
            "task_id": task_id,
            "status": job.status,
            "text": job.text if job.text else "",
            "model": job.model,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка получения статуса транскрибации {task_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

# ---------------------------------------------------------------------------
# Статическая раздача аудио-сегментов для DeepInfra (audio_url)
# ---------------------------------------------------------------------------
# Скрипт parallel_deepinfra.py копирует mp3-файлы в каталог "audio/url_segments".
# Благодаря шарингу volume ./audio ↔ /app/audio этот путь виден как хосту,
# так и контейнеру. Делим его через FastAPI статикой по URL /audio/<file>.

STATIC_AUDIO_DIR = Path("audio/url_segments")
STATIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(STATIC_AUDIO_DIR)), name="audio")

@app.get("/check_deepinfra_connection")
async def check_deepinfra_connection():
    """Проверка доступности DeepInfra API."""
    test_url = "https://api.deepinfra.com/"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(test_url, timeout=5)
            if response.status_code == 200:
                return {"status": "success", "message": f"DeepInfra API доступен. Статус: {response.status_code}"}
            else:
                return {"status": "failed", "message": f"DeepInfra API вернул статус: {response.status_code}", "response_text": response.text}
    except httpx.RequestError as e:
        return {"status": "failed", "message": f"Ошибка соединения с DeepInfra API: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Непредвиденная ошибка при проверке DeepInfra: {e}"}

# ---------------------------------------------------------------------------
# ЮKassa webhook обработчики
# ---------------------------------------------------------------------------

@app.head("/yukassa-webhook")
async def yukassa_webhook_head():
    """HEAD запрос для проверки webhook URL"""
    return Response(status_code=200)

@app.post("/yukassa-webhook")
async def yukassa_webhook(request: Request, db = Depends(get_db)):
    """Обработка webhook'ов от ЮKassa"""
    if not YUKASSA_AVAILABLE:
        raise HTTPException(status_code=503, detail="ЮKassa недоступен")
    
    try:
        # Получаем данные webhook'а
        webhook_data = await request.json()
        logger.info(f"Получен webhook от ЮKassa: {webhook_data.get('event', 'unknown')}")
        
        # Проверяем подпись webhook'а (если настроен секрет)
        if YUKASSA_WEBHOOK_SECRET:
            # TODO: Добавить проверку подписи webhook'а
            pass
        
        # Создаем сервис ЮKassa
        yukassa_service = YukassaPaymentService()
        
        # Обрабатываем webhook
        payment_info = yukassa_service.process_webhook(webhook_data)
        
        if payment_info and payment_info['status'] == 'succeeded':
            # Платеж успешен - активируем план
            user_id = payment_info['metadata'].get('user_id')
            plan_type = payment_info['metadata'].get('plan_type')
            
            if user_id and plan_type:
                # Импортируем функцию активации плана
                from transkribator_modules.bot.payments import activate_plan_after_payment
                
                # Активируем план
                await activate_plan_after_payment(user_id, payment_info)
                
                logger.info(f"План {plan_type} активирован для пользователя {user_id} через webhook")
                
                return {"status": "success", "message": "Платеж обработан"}
            else:
                logger.error(f"Не найдены user_id или plan_type в webhook: {payment_info}")
                return {"status": "error", "message": "Неверные данные платежа"}
        else:
            logger.info(f"Webhook не требует обработки: {webhook_data.get('event')}")
            return {"status": "ignored", "message": "Webhook не требует обработки"}
            
    except Exception as e:
        logger.error(f"Ошибка обработки webhook ЮKassa: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обработки webhook: {str(e)}")

@app.get("/yukassa-status")
async def yukassa_status():
    """Проверка статуса ЮKassa"""
    if not YUKASSA_AVAILABLE:
        return {"status": "unavailable", "message": "ЮKassa SDK не установлен"}
    
    try:
        yukassa_service = YukassaPaymentService()
        return {"status": "available", "message": "ЮKassa настроен и готов к работе"}
    except Exception as e:
        return {"status": "error", "message": f"Ошибка инициализации ЮKassa: {str(e)}"}

if __name__ == "__main__":
    # Запускаем сервер
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info"
    ) 