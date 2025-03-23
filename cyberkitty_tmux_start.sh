#!/bin/bash

# Скрипт для запуска модульной версии КиберКотика в tmux-сессии

# Проверяем, установлен ли tmux
if ! command -v tmux &> /dev/null; then
    echo "❌ tmux не установлен. Устанавливаем... (потребуются права sudo)"
    sudo apt-get update && sudo apt-get install -y tmux
fi

# Имя сессии tmux
SESSION_NAME="cyberkitty_bot"

# Остановка предыдущей сессии, если существует
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Останавливаем предыдущую сессию $SESSION_NAME..."
    tmux send-keys -t $SESSION_NAME C-c
    sleep 1
    tmux kill-session -t $SESSION_NAME
fi

# Создаем новую сессию tmux и запускаем в ней бота
echo "Создаем новую сессию $SESSION_NAME и запускаем бота..."
tmux new-session -d -s $SESSION_NAME "python cyberkitty_modular.py"

# Проверяем, что сессия создана
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "✅ Бот успешно запущен в tmux-сессии '$SESSION_NAME'"
    echo ""
    echo "Для подключения к сессии используйте: tmux attach -t $SESSION_NAME"
    echo "Для отключения от сессии нажмите: Ctrl+b, затем d"
    echo "Для остановки бота используйте: ./cyberkitty_tmux_stop.sh"
else
    echo "❌ Ошибка: Не удалось создать tmux-сессию"
    exit 1
fi 