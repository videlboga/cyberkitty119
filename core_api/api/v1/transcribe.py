import asyncio
import os
import tempfile
import uuid
import time
import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from pydantic import BaseModel

from transkribator_modules.transcribe.transcriber_v4 import transcribe_audio, format_transcript_with_llm
from transkribator_modules.audio.extractor import extract_audio_from_video
from transkribator_modules.config import logger
from transkribator_modules.db.database import (
    calculate_audio_duration,
    UserService,
    TranscriptionService,
    ApiKeyService
)
from transkribator_modules.api.miniapp import get_db
from core_api.api.v1.dependencies import verify_api_key

router = APIRouter()

TEMP_DIR = Path(tempfile.gettempdir()) / "transkribator"
TEMP_DIR.mkdir(exist_ok=True)

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

@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_video(
    file: UploadFile = File(...),
    format_with_llm: bool = True,
    user_and_key: tuple = Depends(verify_api_key)
):
    """
    Транскрибирует загруженное видео с проверкой лимитов
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

        # Транскрибируем аудио
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

        try:
            from transkribator_modules.db.database import log_event as _log_event
            _log_event(user.id, "api_transcription_saved", {
                "filename": file.filename,
                "duration_min": actual_duration,
                "text_len": len(formatted_transcript or raw_transcript or ""),
                "formatting_service": formatting_service or "none",
            })
        except Exception:
            pass

        # Обновляем использование 
        user_service.add_usage(user, actual_duration)
        if api_key:
            api_key_service.add_api_key_usage(api_key, actual_duration)

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
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Внутренняя ошибка сервера: {str(e)}"
        )

    finally:
        try:
            if temp_video_path.exists():
                temp_video_path.unlink()
            if temp_audio_path.exists():
                temp_audio_path.unlink()
            logger.info(f"Временные файлы очищены для task_id: {task_id}")
        except Exception as e:
            logger.warning(f"Не удалось очистить временные файлы: {e}")

# ============================================================================
# WHISPER GPU PIPELINE ENDPOINTS
# ============================================================================

try:
    from pipeline_orchestrator import WhisperPipeline
    PIPELINE_AVAILABLE = True
except ImportError:
    PIPELINE_AVAILABLE = False
    logger.warning("Pipeline orchestrator not available - GPU transcription endpoint disabled")


class PipelineRequest(BaseModel):
    file_path: str
    language: str = "ru"


class PipelineResult(BaseModel):
    status: str
    job_id: str
    total_time: float
    preparation_time: float
    transcription_time: float
    result_file: str
    report_file: str
    segments: int
    audio_duration: float
    error: Optional[str] = None


@router.post("/api/v1/transcribe-gpu")
async def transcribe_gpu(request: PipelineRequest) -> PipelineResult:
    """
    Transcribe media file using local Whisper GPU (RTX 3070 Ti).
    """
    if not PIPELINE_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="GPU pipeline not available"
        )
    
    try:
        file_path = Path(request.file_path)
        
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {file_path}"
            )
        
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024 * 1024:  # 1GB
            logger.error(f"File too large: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size / 1024**3:.1f}GB (max 1GB)"
            )
        
        logger.info(f"Starting GPU transcription: {file_path.name} ({file_size / 1024**2:.1f}MB)")
        
        pipeline = WhisperPipeline()
        result = pipeline.process(file_path)
        
        if result["status"] != "success":
            logger.error(f"Pipeline failed: {result.get('error')}")
            return PipelineResult(
                status="error",
                job_id="",
                total_time=0,
                preparation_time=0,
                transcription_time=0,
                result_file="",
                report_file="",
                segments=0,
                audio_duration=0,
                error=result.get("error", "Unknown error")
            )
        
        logger.info(f"GPU transcription completed: {result['job_id']}")
        return PipelineResult(
            status="success",
            job_id=result["job_id"],
            total_time=result["total_time"],
            preparation_time=result["preparation_time"],
            transcription_time=result["transcription_time"],
            result_file=result["result_file"],
            report_file=result["report_file"],
            segments=result["segments"],
            audio_duration=result["audio_duration"]
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"GPU pipeline error: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {str(e)}"
        )


@router.get("/api/v1/pipeline-status")
async def pipeline_status() -> dict:
    """Get pipeline status and GPU information."""
    if not PIPELINE_AVAILABLE:
        return {
            "status": "unavailable",
            "gpu": None
        }
    
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
        gpu_memory = None
        
        if gpu_available:
            props = torch.cuda.get_device_properties(0)
            total_mem = props.total_memory / 1024**3
            free_mem = torch.cuda.mem_get_info()[0] / 1024**3
            gpu_memory = {
                "total_gb": round(total_mem, 1),
                "free_gb": round(free_mem, 1),
                "used_percent": round((1 - free_mem/total_mem) * 100, 1)
            }
        
        return {
            "status": "available",
            "gpu": {
                "available": gpu_available,
                "name": gpu_name,
                "memory": gpu_memory
            },
            "performance": {
                "single_file_time": "~57 seconds",
                "parallel_capacity": "5 concurrent",
                "throughput": "5.27 files/min max"
            }
        }
    except Exception as e:
        logger.error(f"Error getting pipeline status: {e}")
        return {
            "status": "error",
            "error": str(e)
        }
