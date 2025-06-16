#!/usr/bin/env python3
"""
Скрипт для создания TDLib сессии для Telegram Bot API Server
Этот скрипт создает необходимую сессию для работы с большими файлами через локальный Bot API Server
"""

import os
import asyncio
import json
from pyrogram import Client

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

# Получаем API данные из переменных окружения
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')
phone_number = os.getenv('PHONE_NUMBER')

if not api_id or not api_hash:
    print("❌ Ошибка: TELEGRAM_API_ID и TELEGRAM_API_HASH должны быть установлены в .env файле")
    exit(1)

if not phone_number:
    print("❌ Ошибка: PHONE_NUMBER должен быть установлен в .env файле")
    exit(1)

async def create_session():
    """Создает сессию TDLib для Bot API Server"""
    
    print("🔐 Создание TDLib сессии для Bot API Server...")
    print(f"📱 Номер телефона: {phone_number}")
    
    # Создаем клиент Pyrogram
    client = Client(
        "telegram_bot_api_session",
        api_id=int(api_id),
        api_hash=api_hash,
        phone_number=phone_number,
        workdir="./telegram-bot-api-data"  # Папка для сессионных файлов
    )
    
    try:
        # Подключаемся и авторизуемся
        await client.start()
        
        # Проверяем авторизацию
        me = await client.get_me()
        print(f"✅ Успешно авторизован как: {me.first_name} (@{me.username})")
        print(f"🆔 User ID: {me.id}")
        
        # Создаем конфигурацию для Bot API Server
        config = {
            'session_file': 'telegram_bot_api_session.session',
            'api_id': int(api_id),
            'api_hash': api_hash,
            'phone': phone_number,
            'user_id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'workdir': './telegram-bot-api-data'
        }
        
        # Создаем папку если не существует
        os.makedirs('./telegram-bot-api-data', exist_ok=True)
        
        # Сохраняем конфигурацию
        with open('./telegram-bot-api-data/bot_api_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print("✅ Сессия создана успешно!")
        print("📁 Файлы сессии:")
        print(f"   - ./telegram-bot-api-data/telegram_bot_api_session.session")
        print(f"   - ./telegram-bot-api-data/bot_api_config.json")
        print("")
        print("🚀 Теперь можно запускать Bot API Server с этой сессией")
        
    except Exception as e:
        print(f"❌ Ошибка при создании сессии: {e}")
        return False
    
    finally:
        await client.stop()
    
    return True

async def main():
    """Главная функция"""
    print("=" * 60)
    print("🤖 CyberKitty Transkribator - TDLib Session Creator")
    print("=" * 60)
    
    success = await create_session()
    
    if success:
        print("")
        print("📋 Следующие шаги:")
        print("1. Перезапустите Bot API Server контейнер")
        print("2. Убедитесь, что папка telegram-bot-api-data монтирована в контейнер")
        print("3. Проверьте работу с большими файлами")
        print("")
        print("💡 Подсказка: сессионные файлы сохранены в ./telegram-bot-api-data/")
    else:
        print("❌ Не удалось создать сессию")

if __name__ == "__main__":
    asyncio.run(main()) 