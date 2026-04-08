from fastapi import Depends, Header, Query, HTTPException
from typing import Optional
from sqlalchemy.orm import Session
from transkribator_modules.api.miniapp import get_db
from transkribator_modules.db.models import User, ApiKey
from transkribator_modules.db.database import ApiKeyService, UserService

async def verify_api_key(
    authorization: str = Header(None),
    x_api_key: str = Header(None),
    api_key: str = Query(None),
    db: Session = Depends(get_db)
) -> tuple[User, Optional[ApiKey]]:
    """Проверка API ключа и возврат пользователя (вынесено из api_server.py)"""
    key = None
    if authorization and authorization.startswith("Bearer "):
        key = authorization[7:]
    elif x_api_key:
        key = x_api_key
    elif api_key:
        key = api_key

    if not key:
        raise HTTPException(
            status_code=401,
            detail="API ключ не предоставлен. Используйте заголовок Authorization: Bearer ..."
        )

    api_key_service = ApiKeyService(db)
    api_key_obj = api_key_service.verify_api_key(key)

    if not api_key_obj:
        raise HTTPException(
            status_code=401,
            detail="Недействительный API ключ"
        )

    user = db.query(User).filter(User.id == api_key_obj.user_id).first()

    if not user or getattr(user, "is_active", True) is False:
        raise HTTPException(
            status_code=401,
            detail="Пользователь не найден или заблокирован"
        )

    return user, api_key_obj
