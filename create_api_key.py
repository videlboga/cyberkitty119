#!/usr/bin/env python3
"""
Скрипт для создания API ключа для локального бота
"""

import sys
import os
from pathlib import Path
import uuid

# Добавляем корневую директорию в путь
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.db.database import get_db, UserService, ApiKeyService
    from transkribator_modules.db.models import User, ApiKey
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)

def create_api_key_for_local_bot():
    """Создать API ключ для локального бота"""
    
    db = next(get_db())
    user_service = UserService(db)
    api_key_service = ApiKeyService(db)
    
    # Создаем пользователя для локального бота, если его нет
    local_bot_user = db.query(User).filter(User.telegram_id == 999999999).first()
    
    if not local_bot_user:
        print("Создаю пользователя для локального бота...")
        local_bot_user = user_service.create_user(
            telegram_id=999999999,
            username="local_bot",
            first_name="Local Bot",
            last_name="CyberKitty"
        )
        print(f"Пользователь создан: ID {local_bot_user.id}")
    
    # Создаем API ключ
    api_key_name = "local_bot_key"
    existing_key = db.query(ApiKey).filter(ApiKey.name == api_key_name).first()
    
    if existing_key:
        print(f"API ключ уже существует: {existing_key.key}")
        return existing_key.key
    
    # Генерируем новый ключ
    api_key_value = f"local_bot_{uuid.uuid4().hex[:16]}"
    
    api_key = api_key_service.create_api_key(
        user=local_bot_user,
        name=api_key_name,
        key=api_key_value,
        minutes_limit=None  # Безлимитный
    )
    
    print(f"✅ API ключ создан: {api_key_value}")
    print(f"Имя: {api_key.name}")
    print(f"Пользователь: {local_bot_user.telegram_id}")
    
    return api_key_value

if __name__ == "__main__":
    try:
        key = create_api_key_for_local_bot()
        print(f"\n🔑 Добавьте в .env файл:")
        print(f"LOCAL_API_KEY={key}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1) 