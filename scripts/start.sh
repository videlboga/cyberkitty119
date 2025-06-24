#!/bin/bash

# Скрипт запуска Cyberkitty19 Transkribator
set -e

echo "🐱 Запуск Cyberkitty19 Transkribator..."

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

# Устанавливаем зависимости
echo "📥 Устанавливаем зависимости..."
pip install -r requirements.txt

# Создаем необходимые директории
mkdir -p videos audio transcriptions

# Запускаем бота
echo "🚀 Запускаем Telegram бота..."
python cyberkitty_modular.py 