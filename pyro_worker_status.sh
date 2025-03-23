#!/bin/bash

# Скрипт для проверки статуса Pyro воркера и просмотра логов

SESSION_NAME="pyro_worker"
LOG_FILE="pyro_worker.log"

# Проверяем, запущен ли воркер
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "✅ Pyro воркер запущен и работает."
    echo "------------------------"
    echo "Для подключения к сессии выполните: tmux attach -t $SESSION_NAME"
    echo "Для отключения от сессии без остановки сервиса нажмите: Ctrl+B, затем D"
    echo "------------------------"
else
    echo "❌ Pyro воркер не запущен."
    echo "Для запуска выполните: ./pyro_worker_start.sh"
fi

# Просмотр последних записей лога
if [ -f "$LOG_FILE" ]; then
    echo "Последние 10 записей лога:"
    echo "------------------------"
    tail -n 10 "$LOG_FILE"
    echo "------------------------"
    echo "Для просмотра полного лога выполните: cat $LOG_FILE | less"
else
    echo "❌ Файл лога $LOG_FILE не найден."
fi 