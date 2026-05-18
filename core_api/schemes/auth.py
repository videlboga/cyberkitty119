from pydantic import BaseModel
from typing import Optional

class TgAuthRequest(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    referral_code: Optional[str] = None

class TgAuthResponse(BaseModel):
    is_new_user: bool
    usage_reset: bool
    referral_bonus_applied: bool
    minutes_limit: int
    generations_limit: int
