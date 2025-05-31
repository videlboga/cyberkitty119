#!/bin/bash

# Скрипт для выполнения команд в Docker контейнерах

set -e

# Проверяем аргументы
if [ $# -lt 2 ]; then
    echo "🐳 Выполнение команд в Docker контейнерах"
    echo "========================================="
    echo ""
    echo "Использование: $0 <контейнер> <команда>"
    echo ""
    echo "Доступные контейнеры:"
    echo "  bot     - cyberkitty19-transkribator-bot"
    echo "  pyro    - cyberkitty19-transkribator-pyro-worker" 
    echo "  api     - cyberkitty19-transkribator-api"
    echo ""
    echo "Примеры:"
    echo "  $0 bot python -c 'print(\"Hello\")'"
    echo "  $0 pyro ls -la"
    echo "  $0 api pip list"
    exit 1
fi

CONTAINER_TYPE="$1"
shift
COMMAND="$*"

# Определяем имя контейнера
case "$CONTAINER_TYPE" in
    "bot")
        CONTAINER="cyberkitty19-transkribator-bot"
        ;;
    "pyro"|"worker")
        CONTAINER="cyberkitty19-transkribator-pyro-worker"
        ;;
    "api")
        CONTAINER="cyberkitty19-transkribator-api"
        ;;
    *)
        echo "❌ Неизвестный тип контейнера: $CONTAINER_TYPE"
        exit 1
        ;;
esac

echo "�� Выполнение команды в контейнере: $CONTAINER"
echo "📝 Команда: $COMMAND"
echo ""

# Проверяем, запущен ли контейнер
if docker ps | grep -q "$CONTAINER"; then
    # Контейнер запущен, выполняем команду
    docker exec -it "$CONTAINER" $COMMAND
else
    # Контейнер не запущен, используем docker-compose run
    echo "⚠️  Контейнер не запущен, используем временный контейнер..."
    
    # Определяем сервис для docker-compose
    case "$CONTAINER_TYPE" in
        "bot")
            SERVICE="bot"
            ;;
        "pyro"|"worker")
            SERVICE="pyro-worker"
            ;;
        "api")
            SERVICE="api"
            ;;
    esac
    
    docker-compose run --rm "$SERVICE" $COMMAND
fi 