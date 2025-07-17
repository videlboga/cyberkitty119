#!/usr/bin/env python3
"""
Скрипт для запуска локального бота CyberKitty
"""

import sys
import os
from pathlib import Path

# Добавляем корневую директорию в путь
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.local_bot import main
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что вы находитесь в корневой директории проекта.")
    sys.exit(1)

if __name__ == "__main__":
    # Проверяем наличие .env файла
    if not Path(".env").exists():
        print("⚠️ Предупреждение: Файл .env не найден.")
        print("Создайте файл .env с необходимыми переменными окружения.")
    
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 