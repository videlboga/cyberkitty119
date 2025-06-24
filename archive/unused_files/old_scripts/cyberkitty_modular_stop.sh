#!/bin/bash

# Скрипт для остановки модульной версии КиберКотика

echo "Остановка модульной версии бота..."
pkill -9 -f "cyberkitty_modular" || echo "Бот не был запущен"

# Проверка успешности остановки
sleep 1
if pgrep -f "cyberkitty_modular" > /dev/null; then
    echo "❌ Ошибка: Не удалось остановить бота"
    echo "Запущенные процессы:"
    pgrep -af "cyberkitty_modular"
else
    echo "✅ Бот успешно остановлен"
fi 