#!/bin/bash

# Скрипт для тестирования Cyberkitty19 Transkribator в Docker

set -e

echo "🐳 Тестирование Cyberkitty19 Transkribator в Docker"
echo "======================================"

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    echo "❌ Файл .env не найден!"
    echo "Создайте файл .env с необходимыми настройками."
    echo "Пример:"
    echo "TELEGRAM_BOT_TOKEN=your_bot_token_here"
    echo "TELEGRAM_API_ID=21532963"
    echo "TELEGRAM_API_HASH=66e38ebc131425924c2680e6c8fb6c09"
    exit 1
fi

# Проверяем наличие токена бота
if ! grep -q "TELEGRAM_BOT_TOKEN=" .env || grep -q "your_bot_token_here" .env; then
    echo "⚠️ Внимание: Токен Telegram бота не настроен в .env файле"
    echo "Установите реальный токен бота для тестирования"
fi

echo "📋 Проверка конфигурации..."
echo "TELEGRAM_API_ID: $(grep TELEGRAM_API_ID .env | cut -d'=' -f2)"
echo "TELEGRAM_API_HASH: $(grep TELEGRAM_API_HASH .env | cut -d'=' -f2 | head -c 10)..."
echo "PYROGRAM_WORKER_ENABLED: $(grep PYROGRAM_WORKER_ENABLED .env | cut -d'=' -f2)"

echo ""
echo "🔨 Сборка Docker образов..."
docker-compose build

echo ""
echo "🚀 Запуск сервисов..."
docker-compose up -d

echo ""
echo "⏳ Ожидание запуска сервисов..."
sleep 10

echo ""
echo "📊 Статус контейнеров:"
docker-compose ps

echo ""
echo "📝 Логи Pyrogram воркера:"
echo "========================"
docker-compose logs pyro-worker | tail -20

echo ""
echo "📝 Логи основного бота:"
echo "======================"
docker-compose logs bot | tail -20

echo ""
echo "🔍 Проверка работы сервисов..."

# Проверяем, что контейнеры запущены
if docker-compose ps | grep -q "Up"; then
    echo "✅ Контейнеры запущены успешно"
else
    echo "❌ Проблемы с запуском контейнеров"
    docker-compose logs
    exit 1
fi

echo ""
echo "🎯 Инструкции по тестированию:"
echo "=============================="
echo "1. Убедитесь, что в .env файле указан реальный токен бота"
echo "2. Найдите вашего бота в Telegram"
echo "3. Отправьте команду /start"
echo "4. Попробуйте отправить небольшое видео для тестирования"
echo ""
echo "📊 Полезные команды:"
echo "==================="
echo "Просмотр логов в реальном времени:"
echo "  docker-compose logs -f bot"
echo "  docker-compose logs -f pyro-worker"
echo ""
echo "Перезапуск сервисов:"
echo "  docker-compose restart"
echo ""
echo "Остановка сервисов:"
echo "  docker-compose down"
echo ""
echo "Подключение к контейнеру для отладки:"
echo "  docker-compose exec bot bash"
echo "  docker-compose exec pyro-worker bash"

echo ""
echo "✅ Тестовая среда готова!" 