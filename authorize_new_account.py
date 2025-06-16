#!/usr/bin/env python3
"""
CyberKitty - Скрипт для создания TDLib сессии пользователя через Pyrogram
Создает авторизованную сессию для Bot API Server для поддержки файлов >50 МБ
"""

import os
import sys
import asyncio
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded

# API данные
API_ID = 29612572
API_HASH = "fa4d9922f76dea00803d072510ced924"

# Путь для сохранения сессии
SESSION_NAME = "user_session"
SESSION_DIR = "/home/cyberkitty/Project/transkribator/telegram-bot-api-data-new"

async def create_user_session():
    """
    Создает авторизованную пользовательскую сессию для Bot API Server
    """
    
    print("🔐 CyberKitty - Создание TDLib сессии пользователя (Pyrogram)")
    print("=" * 60)
    print("📱 Этот процесс создаст авторизованную сессию ОДИН РАЗ")
    print("🎯 После создания Bot API Server сможет работать с файлами >50 МБ")
    print("🛡️ Pyrogram безопаснее Telethon - меньше риск блокировки")
    print("=" * 60)
    
    # Создаем директорию если не существует
    os.makedirs(SESSION_DIR, exist_ok=True)
    
    # Полный путь к сессии
    session_path = os.path.join(SESSION_DIR, SESSION_NAME)
    
    # Создаем клиент Pyrogram
    app = Client(
        session_path,
        api_id=API_ID,
        api_hash=API_HASH,
        workdir=SESSION_DIR
    )
    
    try:
        print("🔌 Подключаемся к Telegram через Pyrogram...")
        await app.start()
        
        # Получаем информацию о пользователе
        me = await app.get_me()
        print(f"✅ Успешно авторизован!")
        print(f"👤 Пользователь: {me.first_name} {me.last_name or ''}")
        print(f"📱 Username: @{me.username or 'без username'}")
        print(f"📞 Телефон: {me.phone_number}")
        print(f"🆔 ID: {me.id}")
        
        print(f"💾 Сессия сохранена в: {session_path}.session")
        print("🎉 Готово! Теперь можно запускать Bot API Server с поддержкой больших файлов")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
        
    finally:
        await app.stop()

def main():
    """
    Главная функция
    """
    try:
        # Проверяем наличие pyrogram
        import pyrogram
        print(f"📦 Pyrogram версия: {pyrogram.__version__}")
    except ImportError:
        print("❌ Pyrogram не установлен!")
        print("💡 Установите: pip install pyrogram")
        return False
    
    # Запускаем создание сессии
    success = asyncio.run(create_user_session())
    
    if success:
        print("\n" + "=" * 60)
        print("🚀 СЛЕДУЮЩИЕ ШАГИ:")
        print("1. Запустите Bot API Server с созданной сессией")
        print("2. Укажите правильный database_directory в docker run")
        print("3. Проверьте работу с файлами >50 МБ")
        print("=" * 60)
        print("\n💡 Команда для запуска Bot API Server:")
        print("docker run -d --name telegram-bot-api \\")
        print("  -p 8083:8081 \\")
        print(f"  -v {SESSION_DIR}:/var/lib/telegram-bot-api \\")
        print("  -e TELEGRAM_API_ID=29612572 \\")
        print("  -e TELEGRAM_API_HASH=fa4d9922f76dea00803d072510ced924 \\")
        print("  aiogram/telegram-bot-api:latest \\")
        print("  --local --dir=/var/lib/telegram-bot-api")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 