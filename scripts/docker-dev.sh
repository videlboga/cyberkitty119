#!/bin/bash

# Скрипт для работы с Docker в режиме разработки

set -e

echo "🐳 Docker Development Mode"
echo "=========================="

# Функция для показа доступных команд
show_help() {
    echo "Доступные команды:"
    echo "  start <service>  - Запустить сервис в интерактивном режиме"
    echo "  shell <service>  - Войти в оболочку сервиса"
    echo "  stop             - Остановить все dev сервисы"
    echo "  build            - Пересобрать образы"
    echo "  logs <service>   - Показать логи сервиса"
    echo ""
    echo "Доступные сервисы:"
    echo "  bot    - Telegram бот"
    echo "  api    - API сервер"
    echo ""
    echo "Примеры:"
    echo "  $0 start bot     - Запустить бот в интерактивном режиме"
    echo "  $0 shell api     - Войти в оболочку API сервиса"
    echo "  $0 stop          - Остановить все сервисы"
}

# Проверяем аргументы
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

COMMAND="$1"
SERVICE="$2"

# Определяем Docker Compose файл
COMPOSE_FILE="docker-compose.dev.yml"

# Функция для определения имени сервиса
get_service_name() {
    case "$1" in
        "bot")
            echo "bot-dev"
            ;;
        "api")
            echo "api-dev"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

case "$COMMAND" in
    "start")
        if [ -z "$SERVICE" ]; then
            echo "❌ Не указан сервис для запуска"
            show_help
            exit 1
        fi
        
        SERVICE_NAME=$(get_service_name "$SERVICE")
        if [ "$SERVICE_NAME" = "unknown" ]; then
            echo "❌ Неизвестный сервис: $SERVICE"
            show_help
            exit 1
        fi
        
        echo "🚀 Запуск сервиса $SERVICE в интерактивном режиме..."
        docker-compose -f "$COMPOSE_FILE" run --rm "$SERVICE_NAME"
        ;;
        
    "shell")
        if [ -z "$SERVICE" ]; then
            echo "❌ Не указан сервис для подключения"
            show_help
            exit 1
        fi
        
        SERVICE_NAME=$(get_service_name "$SERVICE")
        if [ "$SERVICE_NAME" = "unknown" ]; then
            echo "❌ Неизвестный сервис: $SERVICE"
            show_help
            exit 1
        fi
        
        # Получаем имя контейнера
        case "$SERVICE" in
            "bot")
                CONTAINER="cyberkitty19-transkribator-bot-dev"
                ;;
            "api")
                CONTAINER="cyberkitty19-transkribator-api-dev"
                ;;
        esac
        
        # Проверяем, запущен ли контейнер
        if docker ps | grep -q "$CONTAINER"; then
            echo "🔗 Подключение к контейнеру: $CONTAINER"
            docker exec -it "$CONTAINER" /bin/bash
        else
            echo "⚠️  Контейнер не запущен. Запускаем..."
            docker-compose -f "$COMPOSE_FILE" run --rm "$SERVICE_NAME"
        fi
        ;;
        
    "stop")
        echo "🛑 Остановка development сервисов..."
        docker-compose -f "$COMPOSE_FILE" down
        ;;
        
    "build")
        echo "🔨 Пересборка образов..."
        docker-compose -f "$COMPOSE_FILE" build
        ;;
        
    "logs")
        if [ -z "$SERVICE" ]; then
            echo "📊 Логи всех сервисов:"
            docker-compose -f "$COMPOSE_FILE" logs -f
        else
            SERVICE_NAME=$(get_service_name "$SERVICE")
            if [ "$SERVICE_NAME" = "unknown" ]; then
                echo "❌ Неизвестный сервис: $SERVICE"
                show_help
                exit 1
            fi
            
            echo "📊 Логи сервиса $SERVICE:"
            docker-compose -f "$COMPOSE_FILE" logs -f "$SERVICE_NAME"
        fi
        ;;
        
    "help"|"-h"|"--help")
        show_help
        ;;
        
    *)
        echo "❌ Неизвестная команда: $COMMAND"
        show_help
        exit 1
        ;;
esac 
