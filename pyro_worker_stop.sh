#!/bin/bash

# Скрипт для остановки Pyrogram воркера в tmux-сессии

# Имя сессии tmux
SESSION_NAME="pyro_worker"

# Проверяем, существует ли сессия
if tmux has-session -t $SESSION_NAME 2>/dev/null; then
    echo "Останавливаем сессию $SESSION_NAME..."
    
    # Отправляем сигнал Ctrl+C для корректной остановки воркера
    tmux send-keys -t $SESSION_NAME C-c
    sleep 2
    
    # Убиваем сессию
    tmux kill-session -t $SESSION_NAME
    
    echo "✅ Pyro воркер успешно остановлен"
else
    echo "❌ Сессия $SESSION_NAME не найдена. Воркер уже остановлен или не был запущен."
fi 