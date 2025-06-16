#!/bin/bash

# Скрипт для развертывания CyberKitty Transkribator на сервер got_is_tod
# Переход с Pyrogram на локальный Bot API Server

set -e

echo "🚀 CyberKitty Transkribator - Развертывание на сервер"
echo "====================================================="

# Конфигурация сервера
SERVER_HOST="got_is_tod"
SERVER_USER="root"
PROJECT_DIR="/opt/cyberkitty-transkribator"
BACKUP_DIR="/opt/cyberkitty-transkribator-backup-$(date +%Y%m%d_%H%M%S)"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Проверка подключения к серверу
check_server_connection() {
    print_step "Проверяю подключение к серверу $SERVER_HOST..."
    
    if ssh -o ConnectTimeout=10 "$SERVER_USER@$SERVER_HOST" "echo 'Подключение успешно'" >/dev/null 2>&1; then
        print_success "Подключение к серверу установлено"
    else
        print_error "Не удается подключиться к серверу $SERVER_HOST"
        echo "Проверьте:"
        echo "  - SSH ключи настроены"
        echo "  - Сервер доступен"
        echo "  - Имя пользователя корректно"
        exit 1
    fi
}

# Создание резервной копии
create_backup() {
    print_step "Создаю резервную копию текущей версии..."
    
    ssh "$SERVER_USER@$SERVER_HOST" "
        if [ -d '$PROJECT_DIR' ]; then
            echo 'Создаю резервную копию...'
            cp -r '$PROJECT_DIR' '$BACKUP_DIR'
            echo 'Резервная копия создана: $BACKUP_DIR'
        else
            echo 'Проект не найден, резервная копия не нужна'
        fi
    "
    
    print_success "Резервная копия создана"
}

# Остановка старых сервисов
stop_old_services() {
    print_step "Останавливаю старые сервисы..."
    
    ssh "$SERVER_USER@$SERVER_HOST" "
        cd '$PROJECT_DIR' || exit 0
        
        echo 'Останавливаю Docker контейнеры...'
        docker-compose down || true
        
        echo 'Останавливаю процессы Python...'
        pkill -f 'transkribator' || true
        pkill -f 'pyrogram' || true
        
        echo 'Очищаю старые образы...'
        docker system prune -f || true
    "
    
    print_success "Старые сервисы остановлены"
}

# Загрузка новых файлов
upload_files() {
    print_step "Загружаю новые файлы на сервер..."
    
    # Создаем временный архив с нужными файлами
    TEMP_ARCHIVE="/tmp/cyberkitty-transkribator-$(date +%Y%m%d_%H%M%S).tar.gz"
    
    print_step "Создаю архив проекта..."
    tar -czf "$TEMP_ARCHIVE" \
        --exclude='.git' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='data/bot.log' \
        --exclude='telegram-bot-api-data*' \
        --exclude='downloads' \
        --exclude='videos' \
        --exclude='audio' \
        --exclude='transcriptions' \
        --exclude='archive' \
        .
    
    print_step "Загружаю архив на сервер..."
    scp "$TEMP_ARCHIVE" "$SERVER_USER@$SERVER_HOST:/tmp/"
    
    # Распаковываем на сервере
    ssh "$SERVER_USER@$SERVER_HOST" "
        echo 'Создаю директорию проекта...'
        mkdir -p '$PROJECT_DIR'
        
        echo 'Распаковываю архив...'
        cd '$PROJECT_DIR'
        tar -xzf '/tmp/$(basename $TEMP_ARCHIVE)' --strip-components=0
        
        echo 'Удаляю временный архив...'
        rm '/tmp/$(basename $TEMP_ARCHIVE)'
        
        echo 'Создаю необходимые директории...'
        mkdir -p videos audio transcriptions data telegram-bot-api-data
        chmod 755 videos audio transcriptions data telegram-bot-api-data
    "
    
    # Удаляем локальный архив
    rm "$TEMP_ARCHIVE"
    
    print_success "Файлы загружены на сервер"
}

# Настройка переменных окружения
setup_environment() {
    print_step "Настраиваю переменные окружения..."
    
    print_warning "Необходимо настроить .env файл на сервере"
    echo "Пожалуйста, укажите следующие данные:"
    
    read -p "BOT_TOKEN: " BOT_TOKEN
    read -p "DEEPINFRA_API_KEY: " DEEPINFRA_API_KEY
    read -s -p "TELEGRAM_API_ID (по умолчанию 29612572): " TELEGRAM_API_ID
    echo
    read -s -p "TELEGRAM_API_HASH (по умолчанию fa4d9922f76dea00803d072510ced924): " TELEGRAM_API_HASH
    echo
    
    # Устанавливаем значения по умолчанию
    TELEGRAM_API_ID=${TELEGRAM_API_ID:-29612572}
    TELEGRAM_API_HASH=${TELEGRAM_API_HASH:-fa4d9922f76dea00803d072510ced924}
    
    # Создаем .env файл на сервере
    ssh "$SERVER_USER@$SERVER_HOST" "
        cd '$PROJECT_DIR'
        
        cat > .env << EOF
# CyberKitty Transkribator Configuration
BOT_TOKEN=$BOT_TOKEN
DEEPINFRA_API_KEY=$DEEPINFRA_API_KEY

# Telegram Bot API Server
USE_LOCAL_BOT_API=true
LOCAL_BOT_API_URL=http://telegram-bot-api:8081
TELEGRAM_API_ID=$TELEGRAM_API_ID
TELEGRAM_API_HASH=$TELEGRAM_API_HASH

# Database
DATABASE_URL=sqlite:///./data/cyberkitty-transkribator.db

# Optional APIs
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/whisper-large-v3
EOF
        
        echo '.env файл создан'
    "
    
    print_success "Переменные окружения настроены"
}

# Сборка и запуск сервисов
build_and_start() {
    print_step "Собираю и запускаю сервисы..."
    
    ssh "$SERVER_USER@$SERVER_HOST" "
        cd '$PROJECT_DIR'
        
        echo 'Собираю Docker образы...'
        docker-compose build
        
        echo 'Запускаю сервисы...'
        docker-compose up -d
        
        echo 'Ожидаю запуска сервисов...'
        sleep 10
        
        echo 'Проверяю статус сервисов...'
        docker-compose ps
    "
    
    print_success "Сервисы запущены"
}

# Авторизация Bot API Server
authorize_bot_api() {
    print_step "Настройка авторизации Bot API Server..."
    
    print_warning "Для работы с большими файлами необходимо авторизовать пользователя в Bot API Server"
    echo "Это можно сделать двумя способами:"
    echo "1. Интерактивно на сервере (рекомендуется)"
    echo "2. Скопировать готовую сессию с локальной машины"
    echo
    
    read -p "Выберите способ (1/2): " AUTH_METHOD
    
    if [ "$AUTH_METHOD" = "1" ]; then
        print_step "Запускаю интерактивную авторизацию на сервере..."
        echo "Подключитесь к серверу и выполните:"
        echo "  ssh $SERVER_USER@$SERVER_HOST"
        echo "  cd $PROJECT_DIR"
        echo "  python3 authorize_bot_api_server.py"
        echo
        read -p "Нажмите Enter после завершения авторизации..."
        
    elif [ "$AUTH_METHOD" = "2" ]; then
        if [ -d "telegram-bot-api-data-native" ]; then
            print_step "Копирую готовую сессию на сервер..."
            scp -r telegram-bot-api-data-native/* "$SERVER_USER@$SERVER_HOST:$PROJECT_DIR/telegram-bot-api-data/"
            print_success "Сессия скопирована"
        else
            print_error "Локальная сессия не найдена в telegram-bot-api-data-native/"
            print_warning "Используйте способ 1 для интерактивной авторизации"
        fi
    else
        print_warning "Авторизация пропущена. Выполните её позже вручную."
    fi
}

# Проверка работоспособности
check_health() {
    print_step "Проверяю работоспособность сервисов..."
    
    ssh "$SERVER_USER@$SERVER_HOST" "
        cd '$PROJECT_DIR'
        
        echo 'Статус контейнеров:'
        docker-compose ps
        
        echo
        echo 'Проверка Bot API Server:'
        curl -s 'http://localhost:9081/bot$BOT_TOKEN/getMe' | head -100 || echo 'Bot API Server недоступен'
        
        echo
        echo 'Проверка API сервера:'
        curl -s 'http://localhost:9000/health' || echo 'API сервер недоступен'
        
        echo
        echo 'Последние логи бота:'
        docker-compose logs --tail=10 bot
    "
}

# Основная функция
main() {
    echo "Начинаю развертывание CyberKitty Transkribator..."
    echo
    
    check_server_connection
    create_backup
    stop_old_services
    upload_files
    setup_environment
    build_and_start
    authorize_bot_api
    check_health
    
    echo
    print_success "🎉 Развертывание завершено!"
    echo
    echo "📋 Что дальше:"
    echo "  1. Проверьте работу бота в Telegram"
    echo "  2. Протестируйте загрузку большого файла"
    echo "  3. Проверьте логи: docker-compose logs -f"
    echo
    echo "🔗 Полезные команды на сервере:"
    echo "  cd $PROJECT_DIR"
    echo "  docker-compose ps              # Статус сервисов"
    echo "  docker-compose logs -f         # Логи в реальном времени"
    echo "  docker-compose restart         # Перезапуск"
    echo "  docker-compose down && docker-compose up -d  # Полный перезапуск"
    echo
    echo "🆘 В случае проблем:"
    echo "  Резервная копия: $BACKUP_DIR"
    echo "  Восстановление: cp -r $BACKUP_DIR/* $PROJECT_DIR/"
}

# Проверка аргументов
if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Использование: $0 [опции]"
    echo
    echo "Опции:"
    echo "  --help, -h     Показать эту справку"
    echo "  --dry-run      Показать что будет сделано без выполнения"
    echo
    echo "Этот скрипт развертывает новую версию CyberKitty Transkribator"
    echo "с поддержкой локального Bot API Server вместо Pyrogram."
    exit 0
fi

if [ "$1" = "--dry-run" ]; then
    echo "🧪 РЕЖИМ ТЕСТИРОВАНИЯ - команды не будут выполнены"
    echo
    echo "Будет выполнено:"
    echo "  1. Проверка подключения к серверу $SERVER_HOST"
    echo "  2. Создание резервной копии в $BACKUP_DIR"
    echo "  3. Остановка старых сервисов"
    echo "  4. Загрузка новых файлов в $PROJECT_DIR"
    echo "  5. Настройка переменных окружения"
    echo "  6. Сборка и запуск Docker сервисов"
    echo "  7. Авторизация Bot API Server"
    echo "  8. Проверка работоспособности"
    exit 0
fi

# Запуск основной функции
main 