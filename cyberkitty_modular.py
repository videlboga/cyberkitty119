#!/usr/bin/env python3

"""
КиберКотик 119 - Telegram-бот для транскрибации видео/аудио.
Модульная версия.
"""

import sys
import os
from pathlib import Path

# Проверка наличия модулей
try:
    from transkribator_modules.main import main
except ImportError:
    print("❌ Ошибка: Модули transkribator_modules не найдены.")
    print("Убедитесь, что вы находитесь в корневой директории проекта.")
    sys.exit(1)

if __name__ == "__main__":
    # Проверяем наличие .env файла
    if not Path(".env").exists():
        print("⚠️ Предупреждение: Файл .env не найден.")
        print("Создайте файл .env с необходимыми переменными окружения.")
    
    try:
        main()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 