from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from core_api.api.v1.dependencies import verify_api_key

router = APIRouter(prefix="/payments", tags=["payments"])

# Simple mock for plans logic that will be migrated here
PLAN_PRICES_STARS = {
    "pro": 230,
    "unlimited": 538,
}

PLAN_PRICES_RUB = {
    "basic": 0.0,
    "pro": 299.0,
    "unlimited": 699.0,
}

PLAN_DESCRIPTIONS = {
    "basic": {
        "title": "Бесплатный план",
        "description": "3 генерации в месяц, файлы до 50 МБ",
        "features": ["3 генерации в месяц", "Файлы до 50 МБ", "Базовое качество", "Без оплаты"]
    },
    "pro": {
        "title": "Профессиональный план",
        "description": "600 минут в месяц, API доступ, файлы до 500 МБ",
        "features": ["600 минут транскрибации в месяц", "Файлы до 500 МБ", "Приоритетная обработка", "API доступ с ключами", "Экспорт в разных форматах"]
    },
    "unlimited": {
        "title": "Безлимитный план",
        "description": "Безлимитные минуты, файлы до 2 ГБ, расширенный API",
        "features": ["Безлимитные минуты транскрибации", "Файлы до 2 ГБ", "Максимальный приоритет", "Расширенный API доступ", "Поддержка 24/7"]
    }
}

@router.get("/plans")
async def get_plans(api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    return {
        "stars": PLAN_PRICES_STARS,
        "rub": PLAN_PRICES_RUB,
        "descriptions": PLAN_DESCRIPTIONS
    }

@router.post("/invoice")
async def create_invoice(payload: Dict[str, Any], api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    plan_id = payload.get("plan_id")
    telegram_id = payload.get("telegram_id")
    currency = payload.get("currency", "stars")

    if plan_id not in PLAN_DESCRIPTIONS:
        raise HTTPException(status_code=400, detail="Invalid plan_id")

    if currency == "rub":
        price = PLAN_PRICES_RUB.get(plan_id, 0.0)
        if price <= 0:
            raise HTTPException(status_code=400, detail="Plan has no rub price")
        try:
            from transkribator_modules.payments.yukassa import YukassaPaymentService
            ys = YukassaPaymentService()
            payment_info = ys.create_payment(
                user_id=telegram_id,
                plan_type=plan_id,
                amount=price,
                description=f"Подписка CyberKitty {plan_id.title()}"
            )
            return {
                "status": "success",
                "invoice_payload": f"plan_{plan_id}",
                "title": PLAN_DESCRIPTIONS[plan_id]["title"],
                "confirmation_url": payment_info.get("confirmation_url")
            }
        except Exception as e:
            # logger.error(f"Yukassa error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Stars logic
        return {
            "status": "success",
            "invoice_payload": f"plan_{plan_id}",
            "title": PLAN_DESCRIPTIONS[plan_id]["title"]
        }

@router.post("/success")
async def handle_payment_success(payload: Dict[str, Any], api_key: str = Depends(verify_api_key)) -> Dict[str, Any]:
    # Logic to add stars/balance/subscription
    return {"status": "success", "message": "Payment recorded"}
