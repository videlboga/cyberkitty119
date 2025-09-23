#!/bin/bash

# Скрипт для входа в интерактивную оболочку Docker контейнера

set -e

echo "🐳 Вход в интерактивную оболочку Docker"
echo "======================================="

# Функция для показа доступных контейнеров
show_containers() {
    echo "📦 Доступные контейнеры:"
    echo "1) cyberkitty19-transkribator-bot (основной бот)"
    echo "2) cyberkitty19-transkribator-api (API сервер)"
    echo ""
}

# Проверяем, запущены ли контейнеры
if ! docker-compose ps | grep -q "Up"; then
    echo "⚠️  Контейнеры не запущены. Запускаем..."
    docker-compose up -d
    sleep 3
fi

# Если передан аргумент, используем его
if [ -n "$1" ]; then
    case "$1" in
        "bot"|"1")
            CONTAINER="cyberkitty19-transkribator-bot"
            ;;
        "api"|"2")
            CONTAINER="cyberkitty19-transkribator-api"
            ;;
        *)
            echo "❌ Неизвестный контейнер: $1"
            show_containers
            exit 1
            ;;
    esac
else
    # Интерактивный выбор
    show_containers
    read -p "Выберите контейнер (1-2): " choice
    
    case "$choice" in
        1|bot)
            CONTAINER="cyberkitty19-transkribator-bot"
            ;;
        2|api)
            CONTAINER="cyberkitty19-transkribator-api"
            ;;
        *)
            echo "❌ Неверный выбор"
            exit 1
            ;;
    esac
fi

echo "🔗 Подключение к контейнеру: $CONTAINER"
echo "💡 Для выхода введите 'exit' или нажмите Ctrl+D"
echo ""

# Входим в контейнер
docker exec -it "$CONTAINER" /bin/bash 
