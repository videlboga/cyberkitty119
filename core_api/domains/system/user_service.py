from sqlalchemy.orm import Session
from datetime import datetime
from transkribator_modules.db.database import UserService
from transkribator_modules.db.database import PromoCodeService
from transkribator_modules.db.models import User, Transcription
from sqlalchemy import func
from core_api.schemes.system import UserProfileResponse, ActivePromo

class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.user_service = UserService(db)
        self.promo_service = PromoCodeService(db)

    def get_profile_by_telegram_id(self, telegram_id: int, tg_first_name: str = "", tg_last_name: str = "") -> UserProfileResponse:
        user = self.user_service.get_or_create_user(telegram_id=telegram_id)
        
        # update name if changed
        updated = False
        if tg_first_name and user.first_name != tg_first_name:
            user.first_name = tg_first_name
            updated = True
        if tg_last_name and user.last_name != tg_last_name:
            user.last_name = tg_last_name
            updated = True
        if updated:
            self.db.commit()

        usage_info = self.user_service.get_usage_info(user)
        active_promos_db = self.promo_service.get_user_active_promos(user)
        
        # Format plan status
        plan_status = ""
        if user.plan_expires_at:
            if user.plan_expires_at > datetime.utcnow():
                days_left = (user.plan_expires_at - datetime.utcnow()).days
                plan_status = f"(истекает через {days_left} дн.)"
            else:
                plan_status = "(истек)"
        elif user.current_plan != "free":
            plan_status = "(бессрочно 🎉)"
            
        active_promos = [
            ActivePromo(
                code=p.promo_code.code if p.promo_code else "",
                discount_percent=0, # Field does not exist on PromoCode model
                expires_at=p.activated_at  # placeholder or update if you have it
            ) for p in active_promos_db
        ]

        transcriptions_count = self.db.query(func.count(Transcription.id))\
            .filter(Transcription.user_id == user.id)\
            .scalar() or 0

        # Referral info
        from transkribator_modules.db.database import ReferralService
        ref_service = ReferralService(self.db)
        ref_link_code = ref_service.create_or_get_referral_code(user)
        stats = ref_service.get_referral_stats_for_user(user)
        referrals_count = stats.get('referrals_count', 0)
        reward_balance = stats.get('reward_balance', 0)

        # Google Drive connection status
        from transkribator_modules.google_api.credentials import GoogleCredentialService
        google_service = GoogleCredentialService(self.db)
        is_google_connected = google_service.get_credentials(user.id) is not None

        return UserProfileResponse(
            telegram_id=telegram_id,
            first_name=user.first_name,
            last_name=user.last_name,
            current_plan=user.current_plan,
            plan_display_name=usage_info['plan_display_name'],
            plan_status_text=plan_status,
            minutes_used_this_month=float(usage_info['minutes_used_this_month'] or 0),
            minutes_limit=float(usage_info['minutes_limit']) if usage_info.get('minutes_limit') is not None else None,
            minutes_remaining=float(usage_info['minutes_remaining']) if usage_info.get('minutes_remaining') is not None else None,
            generations_used_this_month=int(usage_info['generations_used_this_month'] or 0),
            generations_limit=int(usage_info['generations_limit'] or 0) if usage_info.get('generations_limit') is not None else 999999,
            generations_remaining=int(usage_info['generations_remaining'] or 0) if usage_info.get('generations_remaining') is not None else 999999,
            usage_percentage=float(usage_info['usage_percentage'] or 0),
            total_minutes_transcribed=float(usage_info['total_minutes_transcribed'] or 0),
            total_generations=int(usage_info.get('total_generations', 0)),
            created_at=user.created_at or datetime.utcnow(),
            updated_at=user.updated_at or datetime.utcnow(),
            transcriptions_count=transcriptions_count,
            active_promos=active_promos,
            referral_code=ref_link_code,
            referrals_count=referrals_count,
            reward_balance=reward_balance,
            is_google_connected=is_google_connected
        )
