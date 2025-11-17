#!/bin/bash

# 🏥 Скрипт проверки здоровья Cyberkitty19 Transkribator
# Использование: ./health-check.sh [--verbose] [--telegram]

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Флаги
VERBOSE=false
TELEGRAM_NOTIFY=false

# Обработка аргументов
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --telegram|-t)
            TELEGRAM_NOTIFY=true
            shift
            ;;
        *)
            echo "Использование: $0 [--verbose] [--telegram]"
            exit 1
            ;;
    esac
done

# Функции для вывода
log() {
    echo -e "${GREEN}[✓]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[⚠]${NC} $1"
}

error() {
    echo -e "${RED}[✗]${NC} $1"
}

info() {
    echo -e "${BLUE}[ℹ]${NC} $1"
}

# Функция для отправки уведомлений в Telegram (если настроено)
send_telegram_alert() {
    if [[ "$TELEGRAM_NOTIFY" == "true" && -f .env ]]; then
        source .env
        if [[ -n "$HEALTH_CHECK_CHAT_ID" && -n "$TELEGRAM_BOT_TOKEN" ]]; then
            curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
                -d chat_id="$HEALTH_CHECK_CHAT_ID" \
                -d text="🚨 Cyberkitty19 Transkribator Alert: $1" \
                -d parse_mode="HTML" > /dev/null
        fi
    fi
}

# Начало проверки
echo "🏥 Проверка здоровья Cyberkitty19 Transkribator"
echo "=============================================="
echo "Время: $(date)"
echo ""

ISSUES=0

# 1. Проверка Docker
info "Проверка Docker..."
if command -v docker &> /dev/null; then
    if docker info &> /dev/null; then
        log "Docker работает"
    else
        error "Docker не отвечает"
        ISSUES=$((ISSUES + 1))
    fi
else
    error "Docker не установлен"
    ISSUES=$((ISSUES + 1))
fi

# 2. Проверка Docker Compose
info "Проверка Docker Compose..."
if command -v docker-compose &> /dev/null; then
    log "Docker Compose установлен"
else
    error "Docker Compose не установлен"
    ISSUES=$((ISSUES + 1))
fi

# 3. Проверка контейнеров
info "Проверка контейнеров..."
if docker-compose ps &> /dev/null; then
    RUNNING_CONTAINERS=$(docker-compose ps --services --filter "status=running" | wc -l)
    TOTAL_CONTAINERS=$(docker-compose ps --services | wc -l)
    
    if [[ $RUNNING_CONTAINERS -eq $TOTAL_CONTAINERS ]]; then
        log "Все контейнеры запущены ($RUNNING_CONTAINERS/$TOTAL_CONTAINERS)"
    else
        warn "Не все контейнеры запущены ($RUNNING_CONTAINERS/$TOTAL_CONTAINERS)"
        ISSUES=$((ISSUES + 1))
        
        if [[ "$VERBOSE" == "true" ]]; then
            echo "Статус контейнеров:"
            docker-compose ps
        fi
    fi
else
    error "Не удается получить статус контейнеров"
    ISSUES=$((ISSUES + 1))
fi

# 4. Проверка API сервера
info "Проверка API сервера..."
if curl -f -s http://localhost:8000/health &> /dev/null; then
    log "API сервер отвечает"
else
    warn "API сервер недоступен"
    ISSUES=$((ISSUES + 1))
fi

# 5. Проверка использования диска
info "Проверка использования диска..."
DISK_USAGE=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
if [[ $DISK_USAGE -lt 80 ]]; then
    log "Использование диска: ${DISK_USAGE}%"
elif [[ $DISK_USAGE -lt 90 ]]; then
    warn "Использование диска: ${DISK_USAGE}% (предупреждение)"
    ISSUES=$((ISSUES + 1))
else
    error "Использование диска: ${DISK_USAGE}% (критично!)"
    ISSUES=$((ISSUES + 1))
    send_telegram_alert "Критическое использование диска: ${DISK_USAGE}%"
fi

# 6. Проверка использования памяти
info "Проверка использования памяти..."
if command -v free &> /dev/null; then
    MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
    if [[ $MEMORY_USAGE -lt 80 ]]; then
        log "Использование памяти: ${MEMORY_USAGE}%"
    elif [[ $MEMORY_USAGE -lt 90 ]]; then
        warn "Использование памяти: ${MEMORY_USAGE}% (предупреждение)"
        ISSUES=$((ISSUES + 1))
    else
        error "Использование памяти: ${MEMORY_USAGE}% (критично!)"
        ISSUES=$((ISSUES + 1))
        send_telegram_alert "Критическое использование памяти: ${MEMORY_USAGE}%"
    fi
fi

# 7. Проверка размера логов
info "Проверка размера логов..."
if [[ -d logs ]]; then
    LOG_SIZE=$(du -sm logs 2>/dev/null | cut -f1)
    if [[ $LOG_SIZE -lt 100 ]]; then
        log "Размер логов: ${LOG_SIZE}MB"
    elif [[ $LOG_SIZE -lt 500 ]]; then
        warn "Размер логов: ${LOG_SIZE}MB (рекомендуется очистка)"
    else
        warn "Размер логов: ${LOG_SIZE}MB (требуется очистка!)"
        ISSUES=$((ISSUES + 1))
    fi
fi

# 8. Проверка размера медиа файлов
info "Проверка размера медиа файлов..."
MEDIA_DIRS=("videos" "audio" "transcriptions")
TOTAL_MEDIA_SIZE=0

for dir in "${MEDIA_DIRS[@]}"; do
    if [[ -d "$dir" ]]; then
        DIR_SIZE=$(du -sm "$dir" 2>/dev/null | cut -f1)
        TOTAL_MEDIA_SIZE=$((TOTAL_MEDIA_SIZE + DIR_SIZE))
        
        if [[ "$VERBOSE" == "true" ]]; then
            echo "  $dir: ${DIR_SIZE}MB"
        fi
    fi
done

if [[ $TOTAL_MEDIA_SIZE -lt 1000 ]]; then
    log "Размер медиа файлов: ${TOTAL_MEDIA_SIZE}MB"
elif [[ $TOTAL_MEDIA_SIZE -lt 5000 ]]; then
    warn "Размер медиа файлов: ${TOTAL_MEDIA_SIZE}MB (рекомендуется очистка)"
else
    warn "Размер медиа файлов: ${TOTAL_MEDIA_SIZE}MB (требуется очистка!)"
    ISSUES=$((ISSUES + 1))
fi

# 9. Проверка базы данных
info "Проверка базы данных..."
if [[ -f "cyberkitty19-transkribator.db" ]]; then
    DB_SIZE=$(du -sm "cyberkitty19-transkribator.db" | cut -f1)
    log "База данных: ${DB_SIZE}MB"
    
    # Проверка доступности базы данных через контейнер
    if docker-compose exec -T cyberkitty19-transkribator-bot python -c "
from transkribator_modules.db.database import SessionLocal
try:
    db = SessionLocal()
    db.execute('SELECT 1')
    db.close()
    print('OK')
except Exception as e:
    print(f'ERROR: {e}')
    exit(1)
" 2>/dev/null | grep -q "OK"; then
        log "База данных доступна"
    else
        error "База данных недоступна"
        ISSUES=$((ISSUES + 1))
    fi
else
    warn "Файл базы данных не найден"
    ISSUES=$((ISSUES + 1))
fi

# 10. Проверка последних ошибок в логах
info "Проверка последних ошибок..."
if docker-compose logs --tail=100 2>/dev/null | grep -i "error\|exception\|failed" | tail -5 | grep -q .; then
    warn "Обнаружены недавние ошибки в логах"
    ISSUES=$((ISSUES + 1))
    
    if [[ "$VERBOSE" == "true" ]]; then
        echo "Последние ошибки:"
        docker-compose logs --tail=100 2>/dev/null | grep -i "error\|exception\|failed" | tail -5
    fi
else
    log "Критических ошибок в логах не обнаружено"
fi

# Итоговый отчет
echo ""
echo "=============================================="
if [[ $ISSUES -eq 0 ]]; then
    log "Все проверки пройдены успешно! Система работает нормально."
    exit 0
elif [[ $ISSUES -le 2 ]]; then
    warn "Обнаружено $ISSUES проблем(ы). Рекомендуется проверка."
    exit 1
else
    error "Обнаружено $ISSUES проблем! Требуется немедленное вмешательство."
    send_telegram_alert "Обнаружено $ISSUES проблем в системе!"
    exit 2
fi 