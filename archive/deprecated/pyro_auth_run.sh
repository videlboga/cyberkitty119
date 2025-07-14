#!/bin/bash

# Скрипт для запуска авторизации Pyrogram клиента

echo "Запуск авторизации Pyrogram клиента..."
python -m transkribator_modules.workers.pyro_auth

# Проверяем, был ли создан файл сессии
if [ -f "pyro_worker.session" ]; then
    echo "✅ Авторизация успешна. Файл сессии создан."
    echo "Теперь вы можете запустить Pyro воркер командой ./pyro_worker_start.sh"
else
    echo "❌ Авторизация не выполнена. Файл сессии не создан."
    echo "Проверьте наличие переменных TELEGRAM_API_ID и TELEGRAM_API_HASH в .env файле."
fi 