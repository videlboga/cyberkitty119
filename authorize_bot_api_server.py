#!/usr/bin/env python3
"""
Скрипт для авторизации пользователя в Telegram Bot API Server
Создает TDLib сессию внутри контейнера для поддержки больших файлов
"""

import subprocess
import sys
import time
import os

def authorize_bot_api_server():
    """
    Авторизует пользователя в Bot API Server для поддержки больших файлов
    """
    
    print("🔐 Авторизация пользователя в Bot API Server")
    print("📱 Этот процесс требует интерактивного ввода номера телефона и кода")
    print("=" * 60)
    
    # API данные
    api_id = "29612572"
    api_hash = "fa4d9922f76dea00803d072510ced924"
    
    # Останавливаем существующие контейнеры
    print("🛑 Останавливаю существующие контейнеры...")
    subprocess.run("docker stop $(docker ps -q --filter='name=telegram-bot-api') 2>/dev/null || true", 
                   shell=True, capture_output=True)
    
    # Очищаем старые данные
    data_dir = "/home/cyberkitty/Project/transkribator/telegram-bot-api-data-new"
    print(f"🧹 Очищаю директорию данных: {data_dir}")
    if os.path.exists(data_dir):
        subprocess.run(f"rm -rf {data_dir}/*", shell=True)
    
    # Создаем директорию если не существует
    os.makedirs(data_dir, exist_ok=True)
    
    print("\n🚀 Запускаю Bot API Server в интерактивном режиме...")
    print("📞 Приготовьтесь ввести:")
    print("   1. Номер телефона (в формате +7XXXXXXXXXX)")
    print("   2. Код подтверждения из SMS/Telegram")
    print("   3. Пароль двухфакторной аутентификации (если включен)")
    print("\n⚠️  ВАЖНО: После успешной авторизации нажмите Ctrl+C для остановки")
    print("=" * 60)
    
    # Команда для запуска Bot API Server в интерактивном режиме
    cmd = [
        "docker", "run", "-it", "--rm",
        "--name", "telegram-bot-api-auth",
        "-p", "8083:8081",
        "-v", f"{data_dir}:/var/lib/telegram-bot-api",
        "-e", f"TELEGRAM_API_ID={api_id}",
        "-e", f"TELEGRAM_API_HASH={api_hash}",
        "aiogram/telegram-bot-api:latest",
        "--local",
        "--dir=/var/lib/telegram-bot-api",
        "--temp-dir=/tmp/telegram-bot-api",
        "--http-port=8081",
        "--verbosity=1"
    ]
    
    try:
        # Запускаем интерактивный процесс
        process = subprocess.run(cmd, check=False)
        
        if process.returncode == 0:
            print("\n✅ Авторизация завершена успешно!")
            print("🔍 Проверяю созданные файлы...")
            
            # Проверяем созданные файлы
            result = subprocess.run(["ls", "-la", data_dir], 
                                  capture_output=True, text=True)
            print(f"📁 Содержимое {data_dir}:")
            print(result.stdout)
            
            return True
        else:
            print(f"\n❌ Процесс завершился с кодом: {process.returncode}")
            return False
            
    except KeyboardInterrupt:
        print("\n\n✅ Авторизация прервана пользователем")
        print("🔍 Проверяю созданные файлы...")
        
        # Проверяем созданные файлы
        result = subprocess.run(["ls", "-la", data_dir], 
                              capture_output=True, text=True)
        print(f"📁 Содержимое {data_dir}:")
        print(result.stdout)
        
        return True
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        return False

def start_bot_api_server():
    """
    Запускает Bot API Server в фоновом режиме после авторизации
    """
    
    api_id = "29612572"
    api_hash = "fa4d9922f76dea00803d072510ced924"
    data_dir = "/home/cyberkitty/Project/transkribator/telegram-bot-api-data-new"
    
    print("\n🚀 Запускаю Bot API Server в фоновом режиме...")
    
    cmd = [
        "docker", "run", "-d",
        "--name", "telegram-bot-api-authorized",
        "-p", "8083:8081",
        "-v", f"{data_dir}:/var/lib/telegram-bot-api",
        "-e", f"TELEGRAM_API_ID={api_id}",
        "-e", f"TELEGRAM_API_HASH={api_hash}",
        "aiogram/telegram-bot-api:latest",
        "--local",
        "--dir=/var/lib/telegram-bot-api",
        "--temp-dir=/tmp/telegram-bot-api",
        "--http-port=8081"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Bot API Server запущен: {result.stdout.strip()}")
        
        # Ждем запуска
        time.sleep(3)
        
        # Проверяем статус
        test_cmd = ["curl", "-s", "http://localhost:8083/bot7907324843:AAEJMec9IeP89y0Taka4k7hbvpjd7F1Frl4/getMe"]
        test_result = subprocess.run(test_cmd, capture_output=True, text=True)
        
        if "first_name" in test_result.stdout:
            print("✅ Bot API Server работает и отвечает на запросы")
            return True
        else:
            print(f"⚠️  Bot API Server запущен, но тест не прошел: {test_result.stdout}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка запуска: {e}")
        print(f"Вывод: {e.stdout}")
        print(f"Ошибки: {e.stderr}")
        return False

if __name__ == "__main__":
    print("🔐 CyberKitty Bot API Server Authorization Tool")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--start-only":
        # Только запуск сервера (если авторизация уже была)
        success = start_bot_api_server()
    else:
        # Полная авторизация + запуск
        print("1️⃣ Этап 1: Авторизация пользователя")
        auth_success = authorize_bot_api_server()
        
        if auth_success:
            print("\n2️⃣ Этап 2: Запуск авторизованного сервера")
            success = start_bot_api_server()
        else:
            success = False
    
    if success:
        print("\n🎉 Готово! Bot API Server настроен и работает")
        print("📋 Теперь можно запускать бота для работы с большими файлами")
        print("🔗 URL: http://localhost:8083")
    else:
        print("\n❌ Настройка не завершена. Проверьте ошибки выше.")
        sys.exit(1) 