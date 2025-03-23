#!/bin/bash

# Скрипт для запуска Pyrogram воркера в tmux-сессии

# Проверяем, установлен ли tmux
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux не установлен. Устанавливаем... (потребуются права sudo)"
    sudo apt-get update && sudo apt-get install -y tmux
fi

# Имя сессии tmux
SESSION_NAME="pyro_worker"

# Остановка предыдущей сессии, если существует
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Останавливаем предыдущую сессию $SESSION_NAME..."
    tmux send-keys -t $SESSION_NAME C-c
    sleep 1
    tmux kill-session -t $SESSION_NAME
fi

# Создаем новую сессию tmux и запускаем в ней воркер
echo "Создаем новую сессию $SESSION_NAME и запускаем Pyro воркер..."
tmux new-session -d -s $SESSION_NAME "python -m transkribator_modules.workers.pyro_worker"

# Проверяем, что сессия создана
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "✅ Pyro воркер успешно запущен в tmux-сессии '$SESSION_NAME'"
    echo ""
    echo "Для подключения к сессии используйте: tmux attach -t $SESSION_NAME"
    echo "Для отключения от сессии нажмите: Ctrl+b, затем d"
    echo "Для остановки воркера используйте: ./pyro_worker_stop.sh"
else
    echo "❌ Ошибка: Не удалось создать tmux-сессию"
    exit 1
fi 