from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from core_api.api.v1.dependencies import get_media_ingestion_service
from core_api.domains.ingestion.media_service import (
    MediaIngestionService,
    MediaIngestionError,
    JobNotFoundError,
)

router = APIRouter(tags=["Ingestion"])

class IngestMediaRequest(BaseModel):
    telegram_id: int
    file_id: str
    audio_path: str
    message_id: Optional[int] = None

class IngestMediaResponse(BaseModel):
    success: bool
    job_id: Optional[int] = None
    error: Optional[str] = None

class JobStatusResponse(BaseModel):
    id: int
    status: str
    progress: float
    error: Optional[str] = None
    stage: Optional[str] = None
    stage_label: Optional[str] = None
    stage_progress: Optional[float] = None
    result_transcript: Optional[str] = None
    note_id: Optional[int] = None

@router.post("/media", response_model=IngestMediaResponse)
async def ingest_binary_media(
    req: IngestMediaRequest,
    service: MediaIngestionService = Depends(get_media_ingestion_service),
):
    """Поставить скачанный файл в очередь на обработку."""
    try:
        job_id = service.enqueue_media_job(
            telegram_id=req.telegram_id,
            file_id=req.file_id,
            audio_path=req.audio_path,
            message_id=req.message_id,
        )
        return IngestMediaResponse(success=True, job_id=job_id)
    except MediaIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - защитный блок
        raise HTTPException(status_code=500, detail="Не удалось создать задачу") from exc


@router.get("/job/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: int,
    service: MediaIngestionService = Depends(get_media_ingestion_service),
):
    """Стянуть актуальный стейт по job_id для поллинга."""
    try:
        job_status = service.get_job_status(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        id=job_status.id,
        status=job_status.status,
        progress=job_status.progress,
        error=job_status.error,
        stage=job_status.stage,
        stage_label=job_status.stage_label,
        stage_progress=job_status.stage_progress,
        result_transcript=job_status.result_transcript,
        note_id=job_status.note_id,
    )
