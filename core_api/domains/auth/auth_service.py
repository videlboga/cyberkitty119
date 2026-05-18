from sqlalchemy.orm import Session
from transkribator_modules.db.database import UserService, ReferralService, log_event
from transkribator_modules.config import logger
from core_api.schemes.auth import TgAuthRequest, TgAuthResponse

class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_service = UserService(db)

    def auth_telegram_user(self, req: TgAuthRequest) -> TgAuthResponse:
        user = self.user_service.get_or_create_user(
            telegram_id=req.telegram_id,
            username=req.username,
            first_name=req.first_name,
            last_name=req.last_name,
        )
        
        usage_reset = bool(getattr(user, "_usage_reset", False))
        was_created = bool(getattr(user, "_was_created", False))
        
        if hasattr(user, "_usage_reset"): delattr(user, "_usage_reset")
        if hasattr(user, "_was_created"): delattr(user, "_was_created")
        
        referral_bonus_applied = False
        if req.referral_code:
            ref_service = ReferralService(self.db)
            try:
                ref_service.record_referral_visit(req.referral_code, req.telegram_id)
            except Exception as exc:
                logger.warning("Failed to record referral visit", extra={"error": str(exc)})
                
            try:
                ref_service.attribute_user_referral(req.telegram_id, req.referral_code)
            except Exception as exc:
                logger.debug("Failed to attribute referral user", extra={"error": str(exc)})
                
            if was_created:
                try:
                    referral_bonus_applied = ref_service.apply_referral_welcome_bonus(user)
                except Exception as exc:
                    logger.warning("Failed to apply referral bonus", extra={"error": str(exc)})

        # Get usage info strictly after potential referal bonus is applied
        usage_info = self.user_service.get_usage_info(user)

        if was_created:
            try:
                log_event(req.telegram_id, "user_registered", {
                    "telegram_id": req.telegram_id,
                    "username": req.username,
                })
            except Exception as exc:
                logger.debug("Failed to log user_registered", extra={"error": str(exc)})
                
        return TgAuthResponse(
            is_new_user=was_created,
            usage_reset=usage_reset,
            referral_bonus_applied=referral_bonus_applied,
            minutes_limit=int(usage_info.get("minutes_limit", 0)),
            generations_limit=int(usage_info.get("generations_limit", 0))
        )
