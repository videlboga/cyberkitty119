#!/bin/bash

# Скрипт для авторизации Pyrogram в Docker контейнере

set -e

echo "🔐 Авторизация Pyrogram в Docker"
echo "================================"

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден!"
    echo "Создайте файл .env с TELEGRAM_API_ID и TELEGRAM_API_HASH"
    exit 1
fi

# Проверяем, что переменные заданы
if ! grep -q "TELEGRAM_API_ID" .env || ! grep -q "TELEGRAM_API_HASH" .env; then
    echo "❌ В .env файле не заданы TELEGRAM_API_ID или TELEGRAM_API_HASH"
    echo "Добавьте эти переменные в .env файл:"
    echo "TELEGRAM_API_ID=ваш_api_id"
    echo "TELEGRAM_API_HASH=ваш_api_hash"
    exit 1
fi

echo "🔨 Сборка Pyrogram Docker образа..."
docker-compose build pyro-worker

echo ""
echo "🚀 Запуск контейнера для авторизации..."

# Запускаем контейнер в интерактивном режиме для авторизации
docker-compose run --rm pyro-worker python -m transkribator_modules.workers.pyro_auth

echo ""
echo "✅ Авторизация завершена!"
echo ""
echo "📝 Теперь вы можете:"
echo "  make start-docker  - Запустить все сервисы"
echo "  ./scripts/docker-shell.sh pyro  - Подключиться к Pyrogram воркеру" 