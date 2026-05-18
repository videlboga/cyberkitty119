from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core_api.api.v1.dependencies import get_memory_search_service, verify_service_token
from core_api.domains.memory.search_service import (
    MemorySearchService,
    MemorySearchError,
    MemorySearchValidationError,
    MemorySearchServiceError,
)

router = APIRouter(tags=["Memory"])


class SearchRequest(BaseModel):
    telegram_id: int
    query: str


@router.get("/health")
def memory_health():
    return {"status": "memory domain ok"}


@router.post("/search", dependencies=[Depends(verify_service_token)])
async def search_memory(
    req: SearchRequest,
    service: MemorySearchService = Depends(get_memory_search_service),
):
    try:
        result = await service.search(telegram_id=req.telegram_id, query=req.query)
        return {"response": result.response_text}
    except MemorySearchValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MemorySearchServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except MemorySearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
