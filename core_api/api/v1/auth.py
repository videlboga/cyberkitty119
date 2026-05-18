from fastapi import APIRouter, Depends
from core_api.schemes.auth import TgAuthRequest, TgAuthResponse
from core_api.domains.auth.auth_service import AuthService
from transkribator_modules.api.miniapp import get_db

router = APIRouter()

@router.post("/tg/start", response_model=TgAuthResponse, tags=["Auth"])
async def telegram_start_endpoint(req: TgAuthRequest, db = Depends(get_db)):
    """Вызывается ботом при отправке команды /start пользователем"""
    service = AuthService(db)
    return service.auth_telegram_user(req)
