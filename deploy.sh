#!/bin/bash

# 🚀 Скрипт автоматического развертывания Cyberkitty19 Transkribator
# Использование: ./deploy.sh [production|staging]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функции для вывода
log() {
    echo -e "${GREEN}[DEPLOY]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Проверка аргументов
ENVIRONMENT=${1:-production}
if [[ "$ENVIRONMENT" != "production" && "$ENVIRONMENT" != "staging" ]]; then
    error "Неверное окружение. Используйте: production или staging"
    exit 1
fi

log "Начинаю развертывание Cyberkitty19 Transkribator в окружении: $ENVIRONMENT"

# Проверка прав root
if [[ $EUID -eq 0 ]]; then
   error "Не запускайте этот скрипт от root!"
   exit 1
fi

# Проверка наличия Docker
if ! command -v docker &> /dev/null; then
    error "Docker не установлен!"
    info "Установите Docker: curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh"
    exit 1
fi

# Проверка наличия Docker Compose
if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose не установлен!"
    info "Установите Docker Compose: sudo curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose"
    exit 1
fi

# Проверка наличия .env файла
if [[ ! -f .env ]]; then
    warn "Файл .env не найден. Создаю из шаблона..."
    cp env.sample .env
    error "ВАЖНО: Отредактируйте файл .env и добавьте ваши API ключи!"
    info "nano .env"
    exit 1
fi

# Проверка обязательных переменных в .env
log "Проверяю конфигурацию..."
source .env

if [[ -z "$TELEGRAM_BOT_TOKEN" || "$TELEGRAM_BOT_TOKEN" == "your_bot_token_here" ]]; then
    error "TELEGRAM_BOT_TOKEN не настроен в .env файле!"
    exit 1
fi

if [[ -z "$OPENAI_API_KEY" && -z "$OPENROUTER_API_KEY" ]] || [[ "$OPENAI_API_KEY" == "your_openai_api_key_here" && "$OPENROUTER_API_KEY" == "your_openrouter_api_key_here" ]]; then
    error "Не настроен ни один API ключ для транскрибации в .env файле!"
    info "Настройте OPENAI_API_KEY или OPENROUTER_API_KEY"
    exit 1
fi

log "Конфигурация проверена ✓"

# Создание необходимых директорий
log "Создаю необходимые директории..."
mkdir -p videos audio transcriptions logs
chmod 755 videos audio transcriptions logs

# Остановка существующих контейнеров
log "Остановка существующих контейнеров..."
docker-compose down || true

# Очистка старых образов (опционально)
if [[ "$ENVIRONMENT" == "production" ]]; then
    log "Очистка старых Docker образов..."
    docker system prune -f || true
fi

# Сборка образов
log "Сборка Docker образов..."
docker-compose build --no-cache

# Запуск контейнеров
log "Запуск контейнеров..."
docker-compose up -d

# Ожидание запуска сервисов
log "Ожидание запуска сервисов..."
sleep 10

# Проверка статуса контейнеров
log "Проверка статуса контейнеров..."
if docker-compose ps | grep -q "Up"; then
    log "Контейнеры запущены успешно ✓"
else
    error "Проблемы с запуском контейнеров!"
    docker-compose logs
    exit 1
fi

# Проверка API сервера
log "Проверка API сервера..."
sleep 5
if curl -f http://localhost:8000/health &> /dev/null; then
    log "API сервер работает ✓"
else
    warn "API сервер недоступен. Проверьте логи: docker-compose logs cyberkitty19-transkribator-api"
fi

# Рекомендации по дальнейшим шагам
echo ""
info "=== СЛЕДУЮЩИЕ ШАГИ ==="
info "1. Проверьте логи:"
info "   docker-compose logs -f"
info ""
info "2. Проверьте статус:"
info "   docker-compose ps"
info ""
info "3. Протестируйте бота:"
info "   Отправьте /start вашему боту в Telegram"
info ""

# Создание скриптов управления
log "Создание скриптов управления..."

# Скрипт для просмотра логов
cat > view-logs.sh << 'EOF'
#!/bin/bash
echo "📊 Логи Cyberkitty19 Transkribator"
echo "=================================="
docker-compose logs -f --tail=100
EOF
chmod +x view-logs.sh

# Скрипт для перезапуска
cat > restart.sh << 'EOF'
#!/bin/bash
echo "🔄 Перезапуск Cyberkitty19 Transkribator"
echo "======================================="
docker-compose restart
echo "✅ Перезапуск завершен"
docker-compose ps
EOF
chmod +x restart.sh

# Скрипт для остановки
cat > stop.sh << 'EOF'
#!/bin/bash
echo "🛑 Остановка Cyberkitty19 Transkribator"
echo "======================================"
docker-compose down
echo "✅ Сервисы остановлены"
EOF
chmod +x stop.sh

# Скрипт для обновления
cat > update.sh << 'EOF'
#!/bin/bash
echo "🔄 Обновление Cyberkitty19 Transkribator"
echo "======================================="

# Остановка сервисов
docker-compose down

# Обновление кода
git pull

# Пересборка образов
docker-compose build

# Запуск сервисов
docker-compose up -d

echo "✅ Обновление завершено"
docker-compose ps
EOF
chmod +x update.sh

log "Скрипты управления созданы:"
log "  ./view-logs.sh  - Просмотр логов"
log "  ./restart.sh    - Перезапуск сервисов"
log "  ./stop.sh       - Остановка сервисов"
log "  ./update.sh     - Обновление проекта"

echo ""
log "🎉 Развертывание Cyberkitty19 Transkribator завершено!"
log "Проект запущен в окружении: $ENVIRONMENT"

# Показать статус
echo ""
info "=== ТЕКУЩИЙ СТАТУС ==="
docker-compose ps

echo ""
info "=== ПОЛЕЗНЫЕ КОМАНДЫ ==="
info "Просмотр логов:     docker-compose logs -f"
info "Статус контейнеров: docker-compose ps"
info "Перезапуск:         docker-compose restart"
info "Остановка:          docker-compose down"
info "Обновление:         git pull && docker-compose build && docker-compose up -d" 
