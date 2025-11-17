#!/usr/bin/env python3

import sys
import os
from pathlib import Path

# Добавляем текущий каталог в путь
sys.path.insert(0, os.path.abspath('.'))

# Проверка наличия модулей
try:
    from transkribator_modules.main import main
    print("Импорт успешен!")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("sys.path:", sys.path)
    sys.exit(1)

if __name__ == "__main__":
    # Проверяем наличие .env файла
    if not Path(".env").exists():
        print("⚠️ Предупреждение: Файл .env не найден.")
        print("Создайте файл .env с необходимыми переменными окружения.")
    
    try:
        print("Запуск бота...")
        main()
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1) 