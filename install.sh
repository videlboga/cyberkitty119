#!/bin/bash

# Скрипт установки Transkribator (КиберКотик 119)
# Автоматизирует процесс настройки и установки всех зависимостей для бота

set -e  # Прерывать выполнение при ошибках

# Цвета для текста
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода сообщений с отступами
log() {
    echo -e "${GREEN}[УСТАНОВКА]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[ПРЕДУПРЕЖДЕНИЕ]${NC} $1"
}

error() {
    echo -e "${RED}[ОШИБКА]${NC} $1"
}

info() {
    echo -e "${BLUE}[ИНФО]${NC} $1"
}

# Проверка наличия необходимых команд
check_command() {
    command -v $1 >/dev/null 2>&1 || { error "Команда $1 не найдена! Установите её."; return 1; }
    return 0
}

# Баннер
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════╗"
echo "║                 УСТАНОВКА TRANSKRIBATOR             ║"
echo "║                    (КиберКотик 119)                 ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Проверка предварительных требований
log "Проверка необходимых программ..."

# Проверка наличия Python 3.8+
if ! check_command python3; then
    error "Python 3 не установлен! Установите Python 3.8 или выше."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d " " -f 2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MAJOR" -eq 3 -a "$PYTHON_MINOR" -lt 8 ]; then
    error "Требуется Python 3.8 или выше. У вас Python $PYTHON_VERSION"
    exit 1
fi
info "Python $PYTHON_VERSION ✓"

# Проверка и установка ffmpeg
if ! check_command ffmpeg; then
    warn "FFmpeg не установлен. Установка..."
    if check_command apt-get; then
        sudo apt-get update
        sudo apt-get install -y ffmpeg
    elif check_command yum; then
        sudo yum install -y ffmpeg
    elif check_command brew; then
        brew install ffmpeg
    else
        error "Не удалось определить пакетный менеджер. Установите ffmpeg вручную."
        exit 1
    fi
fi
info "FFmpeg ✓"

# Проверка tmux
if ! check_command tmux; then
    warn "tmux не установлен. Установка..."
    if check_command apt-get; then
        sudo apt-get update
        sudo apt-get install -y tmux
    elif check_command yum; then
        sudo yum install -y tmux
    elif check_command brew; then
        brew install tmux
    else
        error "Не удалось определить пакетный менеджер. Установите tmux вручную."
        exit 1
    fi
fi
info "tmux ✓"

# Создание виртуального окружения
log "Создание виртуального окружения Python..."
python3 -m venv venv
source venv/bin/activate
info "Виртуальное окружение активировано ✓"

# Установка зависимостей
log "Установка зависимостей Python..."
pip install --upgrade pip
pip install -r requirements.txt
info "Зависимости установлены ✓"

# Настройка .env файла
if [ ! -f .env ]; then
    log "Создание .env файла из шаблона..."
    if [ -f .env.sample ]; then
        cp .env.sample .env
        info "Файл .env создан ✓"
        echo -e "${YELLOW}"
        echo "╔════════════════════════════════════════════════════╗"
        echo "║  ВАЖНО: Отредактируйте файл .env и укажите в нём:  ║"
        echo "║  - TELEGRAM_BOT_TOKEN (от @BotFather)               ║"
        echo "║  - OPENAI_API_KEY или OPENROUTER_API_KEY            ║"
        echo "║  - Другие настройки при необходимости               ║"
        echo "╚════════════════════════════════════════════════════╝"
        echo -e "${NC}"
    else
        error ".env.sample не найден. Создайте .env файл вручную."
    fi
else
    info "Файл .env уже существует ✓"
fi

# Делаем скрипты исполняемыми
log "Настройка прав доступа для скриптов..."
chmod +x *.sh
info "Скрипты теперь исполняемые ✓"

# Создание необходимых директорий
log "Создание необходимых директорий..."
mkdir -p videos audio transcriptions
info "Директории созданы ✓"

# Инструкции по настройке Pyrogram Worker (опционально)
echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════╗"
echo "║               ДОПОЛНИТЕЛЬНАЯ НАСТРОЙКА             ║"
echo "║                                                    ║"
echo "║  Для работы с большими видео (>20 МБ) вам нужно    ║"
echo "║  настроить Pyrogram Worker:                        ║"
echo "║                                                    ║"
echo "║  1. Укажите в .env:                                ║"
echo "║     - PYROGRAM_WORKER_ENABLED=true                 ║"
echo "║     - PYROGRAM_WORKER_CHAT_ID                      ║"
echo "║     - TELEGRAM_API_ID и TELEGRAM_API_HASH          ║"
echo "║                                                    ║"
echo "║  2. Запустите скрипт авторизации (только раз):     ║"
echo "║     ./pyro_auth_run.sh                             ║"
echo "║                                                    ║"
echo "║  3. Запустите Pyrogram Worker:                     ║"
echo "║     ./pyro_worker_start.sh                         ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Инструкции по запуску бота
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════╗"
echo "║            УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!            ║"
echo "║                                                    ║"
echo "║  Для запуска бота используйте:                     ║"
echo "║    ./cyberkitty_modular_start.sh                   ║"
echo "║                                                    ║"
echo "║  Для остановки бота:                               ║"
echo "║    ./cyberkitty_modular_stop.sh                    ║"
echo "║                                                    ║"
echo "║  Для проверки логов:                               ║"
echo "║    tail -f cyberkitty_modular.log                  ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"

log "Для работы с ботом активируйте виртуальное окружение: source venv/bin/activate" 