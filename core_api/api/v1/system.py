from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from pydantic import BaseModel
from core_api.api.v1.dependencies import verify_api_key

from core_api.schemes.system import UserProfileResponse
from core_api.domains.system.user_service import ProfileService

# Временно импортируем существующие зависимости, пока они не переедут в domains/
from transkribator_modules.api.miniapp import get_db
from transkribator_modules.db.database import UserService
from transkribator_modules.db.models import User
import json

# Этот роутер будет монтироваться по префиксу /api/v1/system
router = APIRouter()

# Описание Pydantic моделей (временная заглушка, их вынесем в schemes позже)
class PlanInfo(BaseModel):
    name: str
    display_name: str
    minutes_per_month: int
    max_file_size_mb: int
    price_rub: int
    price_usd: int
    description: str
    features: List[str]

class UserInfo(BaseModel):
    telegram_id: int
    username: str | None
    current_plan: str
    plan_display_name: str
    minutes_used_this_month: int
    minutes_limit: int
    minutes_remaining: int
    usage_percentage: float
    total_minutes_transcribed: int


@router.get("/health", tags=["System"])
async def health_check():
    """Базовая проверка состояния нового Core API."""
    return {"status": "healthy", "service": "core-api", "version": "2.0.0"}


@router.get("/plans", response_model=List[PlanInfo], tags=["Billing"])
async def get_plans_endpoint():
    """Получить список доступных тарифных планов (Перенесено из api_server.py)"""
    from transkribator_modules.db.repository.users import get_plans  # Временный импорт
    
    plans = get_plans()
    result = []

    for plan in plans:
        features = []
        if plan.features:
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


@router.get("/user/info", response_model=UserInfo, tags=["Users"])
async def get_user_info(user_and_key: tuple = Depends(verify_api_key)):
    """Получить информацию о пользователе и его использовании"""
    user, _ = user_and_key
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

@router.get("/profile/tg/{telegram_id}", response_model=UserProfileResponse, tags=["Users"])
async def get_tg_user_profile(telegram_id: int, first_name: str = "", last_name: str = ""):
    """Получить агрегированный профиль пользователя для Telegram Бота."""
    db = next(get_db())
    service = ProfileService(db)
    return service.get_profile_by_telegram_id(telegram_id, first_name, last_name)

from core_api.schemes.system import PromoActivationRequest, PromoActivationResponse, UserStatsResponse

@router.post("/promo/activate", response_model=PromoActivationResponse, tags=["Billing"])
async def activate_promo(request: PromoActivationRequest):
    """Активировать промокод."""
    from transkribator_modules.db.database import activate_promo_code
    result = activate_promo_code(request.telegram_id, request.promo_code)
    
    if result.get("success"):
        return PromoActivationResponse(
            success=True,
            bonus=result.get("bonus"),
            expires=result.get("expires")
        )
    return PromoActivationResponse(success=False, error=result.get("error", "Unknown error"))

@router.get("/stats/tg/{telegram_id}", response_model=UserStatsResponse, tags=["Users"])
async def get_user_stats_api(telegram_id: int):
    """Получить статистику пользователя."""
    from transkribator_modules.db.database import get_user_stats
    stats = get_user_stats(telegram_id)
    return UserStatsResponse(
        subscription_status=str(stats.get('subscription_status', 'Бесплатный')),
        subscription_until=str(stats.get('subscription_until', 'Не ограничено')),
        files_processed=int(stats.get('files_processed', 0)),
        minutes_transcribed=float(stats.get('minutes_transcribed', 0)),
        total_characters=int(stats.get('total_characters', 0)),
        last_activity=str(stats.get('last_activity', 'Никогда')),
        files_remaining=str(stats.get('files_remaining', '30 минут')),
        avg_duration=float(stats.get('avg_duration', 0))
    )

