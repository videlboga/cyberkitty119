#!/bin/bash

# Скрипт для запуска модульной версии КиберКотика

# Остановка предыдущего экземпляра бота, если он запущен
echo "Остановка предыдущих экземпляров..."
pkill -f "cyberkitty_modular" || echo "Процессы не найдены"
sleep 2

# Запуск нового экземпляра в фоновом режиме 
echo "Запуск модульной версии бота..."
nohup python cyberkitty_modular.py > cyberkitty_modular.log 2>&1 &

# Сохраняем PID запущенного процесса
BOT_PID=$!
echo "PID запущенного процесса: $BOT_PID"

# Даем процессу время на запуск
sleep 2

# Проверяем, запустился ли процесс
if ps -p $BOT_PID > /dev/null; then
    echo "✅ Бот успешно запущен с PID: $BOT_PID"
    echo "Для просмотра логов используйте: tail -f cyberkitty_modular.log"
    echo "Для остановки бота используйте: ./cyberkitty_modular_stop.sh"
else
    echo "❌ Ошибка: Не удалось запустить бота"
    echo "Последние строки лога:"
    tail -n 5 cyberkitty_modular.log
    exit 1
fi 