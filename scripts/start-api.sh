#!/bin/bash

# Скрипт запуска API сервера Cyberkitty19 Transkribator
set -e

echo "🌐 Запуск API сервера Cyberkitty19 Transkribator..."

# Проверяем наличие .env файла
if [ ! -f .env ]; then
    echo "❌ Файл .env не найден!"
    echo "📝 Скопируйте env.sample в .env и заполните необходимые переменные:"
    echo "   cp env.sample .env"
    exit 1
fi

# Проверяем наличие виртуального окружения
if [ ! -d "venv" ]; then
    echo "📦 Создаем виртуальное окружение..."
    python3 -m venv venv
fi

# Активируем виртуальное окружение
echo "🔧 Активируем виртуальное окружение..."
source venv/bin/activate

# Устанавливаем зависимости для API
echo "📥 Устанавливаем зависимости для API..."
pip install -r requirements/api.txt

# Создаем необходимые директории
mkdir -p videos audio transcriptions

# Запускаем API сервер
echo "🚀 Запускаем API сервер на http://localhost:8000..."
python api_server.py 