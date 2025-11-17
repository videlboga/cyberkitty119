#!/bin/bash

# Скрипт для мониторинга и перезапуска бота, если он не запущен
# Проверяет наличие процессов бота и при необходимости перезапускает их

# Установка переменных
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/bot_watchdog.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Пути к скриптам запуска
MAIN_BOT_SCRIPT="${SCRIPT_DIR}/cyberkitty_modular_start.sh"
PYRO_WORKER_SCRIPT="${SCRIPT_DIR}/pyro_worker_start.sh"

# Функция логирования
log_message() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
    echo "[$TIMESTAMP] $1"
}

# Проверка существования скриптов запуска
if [ ! -f "$MAIN_BOT_SCRIPT" ]; then
    log_message "ОШИБКА: Скрипт запуска основного бота не найден: $MAIN_BOT_SCRIPT"
    exit 1
fi

if [ ! -f "$PYRO_WORKER_SCRIPT" ]; then
    log_message "ОШИБКА: Скрипт запуска Pyrogram worker не найден: $PYRO_WORKER_SCRIPT"
    exit 1
fi

log_message "Начало проверки работы бота..."

# Проверка работы основного бота
if ! pgrep -f "cyberkitty_modular.py" > /dev/null; then
    log_message "ВНИМАНИЕ: Основной бот не запущен! Выполняю перезапуск..."
    bash "$MAIN_BOT_SCRIPT"
    sleep 3
    if pgrep -f "cyberkitty_modular.py" > /dev/null; then
        log_message "УСПЕХ: Основной бот успешно перезапущен!"
    else
        log_message "ОШИБКА: Не удалось перезапустить основной бот!"
    fi
else
    log_message "ОК: Основной бот работает нормально"
fi

# Проверка работы Pyrogram worker
if ! pgrep -f "transkribator_modules.workers.pyro_worker" > /dev/null; then
    log_message "ВНИМАНИЕ: Pyrogram worker не запущен! Выполняю перезапуск..."
    bash "$PYRO_WORKER_SCRIPT"
    sleep 3
    if pgrep -f "transkribator_modules.workers.pyro_worker" > /dev/null; then
        log_message "УСПЕХ: Pyrogram worker успешно перезапущен!"
    else
        log_message "ОШИБКА: Не удалось перезапустить Pyrogram worker!"
    fi
else
    log_message "ОК: Pyrogram worker работает нормально"
fi

log_message "Проверка завершена" 