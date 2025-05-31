#!/bin/bash

# Скрипт для остановки модульной версии КиберКотика в tmux-сессии

# Имя сессии tmux
SESSION_NAME="cyberkitty_bot"

# Проверяем, существует ли сессия
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Останавливаем сессию $SESSION_NAME..."
    
    # Отправляем сигнал Ctrl+C для корректной остановки бота
    tmux send-keys -t $SESSION_NAME C-c
    sleep 2
    
    # Убиваем сессию
    tmux kill-session -t $SESSION_NAME
    
    echo "✅ Бот успешно остановлен"
else
    echo "❌ Сессия $SESSION_NAME не найдена. Бот уже остановлен или не был запущен."
fi 