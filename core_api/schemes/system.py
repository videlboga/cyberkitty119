from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class ActivePromo(BaseModel):
    code: str
    discount_percent: int
    expires_at: Optional[datetime]

class UserProfileResponse(BaseModel):
    telegram_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    current_plan: str
    plan_display_name: str
    plan_status_text: str  # e.g., "(истекает через 5 дн.)"
    
    # Usage
    minutes_used_this_month: float
    minutes_limit: float
    minutes_remaining: float
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
