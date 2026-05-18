from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ActivePromo(BaseModel):
    code: str
    discount_percent: int
    expires_at: Optional[datetime]

class PromoActivationRequest(BaseModel):
    telegram_id: int
    promo_code: str

class PromoActivationResponse(BaseModel):
    success: bool
    bonus: Optional[str] = None
    expires: Optional[str] = None
    error: Optional[str] = None

class UserProfileResponse(BaseModel):
    telegram_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    current_plan: str
    plan_display_name: str
    plan_status_text: str  # e.g., "(истекает через 5 дн.)"
    
    # Usage
    minutes_used_this_month: float
    minutes_limit: Optional[float]
    minutes_remaining: Optional[float]
    generations_used_this_month: int
    generations_limit: int
    generations_remaining: int
    usage_percentage: float
    total_minutes_transcribed: float
    total_generations: int
    
    # Activity
    created_at: datetime
    updated_at: Optional[datetime]
    transcriptions_count: int
    
    # Extra
    active_promos: list[ActivePromo]
    referral_code: Optional[str]
    referrals_count: int
    reward_balance: int
    is_google_connected: bool

class UserStatsResponse(BaseModel):
    subscription_status: str
    subscription_until: str
    files_processed: int
    minutes_transcribed: float
    total_characters: int
    last_activity: str
    files_remaining: str
    avg_duration: float
