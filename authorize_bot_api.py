#!/usr/bin/env python3
"""
CyberKitty - Правильная авторизация пользователя в Bot API Server
Создает TDLib сессию напрямую через Bot API Server для поддержки файлов >50 МБ
"""

import subprocess
import sys
import time
import os

def authorize_bot_api_server():
    """
    Авторизует пользователя в Bot API Server через TDLib
    """
    
    print("🔐 CyberKitty - Авторизация пользователя в Bot API Server")
    print("📱 Этот процесс создаст TDLib сессию для больших файлов")
    print("=" * 60)
    
    # API данные
    api_id = "29612572"
    api_hash = "fa4d9922f76dea00803d072510ced924"
    
    # Останавливаем существующие контейнеры
    print("🛑 Останавливаю существующие контейнеры...")
    subprocess.run("docker stop $(docker ps -q --filter='name=telegram-bot-api') 2>/dev/null || true", 
                   shell=True, capture_output=True)
    
    # Очищаем директорию данных
    data_dir = "/home/cyberkitty/Project/transkribator/telegram-bot-api-data-new"
    print(f"🧹 Очищаю директорию данных: {data_dir}")
    subprocess.run(f"sudo rm -rf {data_dir}/*", shell=True)
    subprocess.run(f"sudo chown -R cyberkitty:cyberkitty {data_dir}", shell=True)
    
    print("\n🚀 Запускаю Bot API Server в режиме авторизации...")
    print("📱 Вам нужно будет ввести:")
    print("   1. Номер телефона (в формате +7XXXXXXXXXX)")
    print("   2. Код подтверждения из SMS/Telegram")
    print("   3. Пароль 2FA (если включен)")
    print("\n⚠️  ВАЖНО: После успешной авторизации нажмите Ctrl+C")
    print("=" * 60)
    
    # Команда для запуска Bot API Server в интерактивном режиме
    cmd = [
        "docker", "run", "-it", "--rm",
        "--name", "telegram-bot-api-auth",
        "-p", "8084:8081",
        "-v", f"{data_dir}:/var/lib/telegram-bot-api",
        "-e", f"TELEGRAM_API_ID={api_id}",
        "-e", f"TELEGRAM_API_HASH={api_hash}",
        "aiogram/telegram-bot-api:latest",
        "--local",
        "--dir=/var/lib/telegram-bot-api",
        "--temp-dir=/tmp/telegram-bot-api",
        "--http-port=8081",
        "--verbosity=2"
    ]
    
    try:
        # Запускаем интерактивную авторизацию
        print("🔄 Запускаю интерактивную авторизацию...")
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0 or result.returncode == 130:  # 130 = Ctrl+C
            print("\n✅ Авторизация завершена!")
            
            # Проверяем, создалась ли сессия
            if os.path.exists(f"{data_dir}") and os.listdir(data_dir):
                print("✅ TDLib сессия создана успешно!")
                
                # Запускаем Bot API Server в фоновом режиме
                print("🚀 Запускаю Bot API Server в фоновом режиме...")
                
                bg_cmd = [
                    "docker", "run", "-d",
                    "--name", "telegram-bot-api",
                    "-p", "8083:8081",
                    "-v", f"{data_dir}:/var/lib/telegram-bot-api",
                    "-e", f"TELEGRAM_API_ID={api_id}",
                    "-e", f"TELEGRAM_API_HASH={api_hash}",
                    "aiogram/telegram-bot-api:latest",
                    "--local",
                    "--dir=/var/lib/telegram-bot-api",
                    "--verbosity=1"
                ]
                
                subprocess.run(bg_cmd, check=True)
                
                # Ждем запуска
                print("⏳ Ожидаю запуска сервера...")
                time.sleep(5)
                
                # Проверяем работоспособность
                test_result = subprocess.run([
                    "curl", "-s", 
                    "http://localhost:8083/bot7907324843:AAEJMec9IeP89y0Taka4k7hbvpjd7F1Frl4/getMe"
                ], capture_output=True, text=True)
                
                if test_result.returncode == 0 and "ok" in test_result.stdout:
                    print("✅ Bot API Server работает с авторизованной сессией!")
                    print("🎉 Теперь можно тестировать большие файлы!")
                    print("\n📋 Следующие шаги:")
                    print("   1. Запустите бота: python transkribator_modules/main.py")
                    print("   2. Отправьте файл >50 МБ для тестирования")
                else:
                    print("❌ Ошибка при проверке Bot API Server")
                    print(f"Ответ: {test_result.stdout}")
            else:
                print("❌ TDLib сессия не была создана")
                print("Попробуйте запустить скрипт еще раз")
        else:
            print(f"❌ Ошибка авторизации (код: {result.returncode})")
            
    except KeyboardInterrupt:
        print("\n✅ Авторизация прервана пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    authorize_bot_api_server() 