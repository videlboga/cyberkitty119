#!/bin/bash
set -e

# Алиас сервера
SERVER="proxy"
PROJECT_DIR="/root/cyberkitty119"

echo "Копируем .env на сервер $SERVER..."
scp .env "$SERVER:$PROJECT_DIR/"

echo "Деплой на сервер $SERVER..."

ssh -t "$SERVER" << SCRIPT
    set -e
    
    if [ ! -d "$PROJECT_DIR" ]; then
        echo "Клонируем репозиторий (HTTPS)..."
        git clone https://github.com/videlboga/cyberkitty119.git "$PROJECT_DIR"
        cd "$PROJECT_DIR"
    else
        echo "Обновляем репозиторий..."
        cd "$PROJECT_DIR"
        git fetch origin
        git reset --hard origin/main
        git pull origin main
    fi
    
    echo "Создаем необходимые директории (если отсутствуют)..."
    mkdir -p media data core_api telegram-bot-api-data transkribator_modules transcribe_client audio videos workers postgres_data_transkribator

    echo "Настраиваем права..."
    chmod 777 -R telegram-bot-api-data || true
    chown -R 101:101 telegram-bot-api-data || true
    
    echo "Останавливаем и удаляем старые контейнеры, если нужно..."
    # Очищаем все orphan контейнеры
    docker compose -f docker-compose.bot-v2.yml down --remove-orphans || true
    
    echo "Пересобираем и запускаем контейнеры..."
    docker compose -f docker-compose.bot-v2.yml up -d --build
    
    echo "Список запущенных контейнеров:"
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    
    echo "Деплой завершен."
SCRIPT
