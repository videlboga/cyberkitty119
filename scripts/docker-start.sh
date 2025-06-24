#!/bin/bash

# Скрипт для запуска Cyberkitty19 Transkribator в Docker

set -e

echo "🐳 Запуск Cyberkitty19 Transkribator в Docker"
echo "================================"

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден!"
    echo "Создайте файл .env с необходимыми настройками."
    exit 1
fi

echo "🔨 Сборка Docker образов..."
docker-compose build

echo ""
echo "🚀 Запуск сервисов..."
docker-compose up -d

echo ""
echo "⏳ Ожидание запуска сервисов..."
sleep 5

echo ""
echo "📊 Статус контейнеров:"
docker-compose ps

echo ""
echo "✅ Сервисы запущены!"
echo ""
echo "📊 Полезные команды:"
echo "  make logs        - Просмотр логов"
echo "  make status      - Статус сервисов"
echo "  make stop-docker - Остановка сервисов" 