# 🐳 Интерактивная работа с Docker

Поскольку есть проблемы с виртуальным окружением в системе (особенно через Cursor), можно использовать Docker для интерактивной разработки.

## 🚀 Быстрый старт

### 1. Авторизация Pyrogram в Docker
```bash
make docker-pyro-auth
# или
./scripts/docker-pyro-auth.sh
```

### 2. Интерактивная работа с контейнерами
```bash
# Войти в оболочку любого контейнера
make docker-shell
# Выбрать: 1) bot, 2) pyro-worker, 3) api

# Или напрямую:
./scripts/docker-shell.sh bot    # для бота
./scripts/docker-shell.sh pyro   # для Pyrogram воркера
./scripts/docker-shell.sh api    # для API сервера
```

### 3. Development режим (рекомендуется)
```bash
# Запустить интерактивный режим разработки
./scripts/docker-dev.sh start bot     # Запустить бот интерактивно
./scripts/docker-dev.sh start pyro    # Запустить Pyrogram воркер интерактивно
./scripts/docker-dev.sh start api     # Запустить API сервер интерактивно

# Войти в оболочку запущенного контейнера
./scripts/docker-dev.sh shell bot     # Войти в бот
./scripts/docker-dev.sh shell pyro    # Войти в Pyrogram воркер

# Остановить все dev сервисы
./scripts/docker-dev.sh stop
```

## 🔧 Полезные команды

### Выполнение команд в контейнерах
```bash
# Проверить версию Python
./scripts/docker-run-command.sh bot python --version

# Установить дополнительные пакеты
./scripts/docker-run-command.sh bot pip install requests

# Запустить тесты
./scripts/docker-run-command.sh bot python -m pytest

# Посмотреть логи
./scripts/docker-run-command.sh bot tail -f *.log
```

### Авторизация и настройка Pyrogram
```bash
# 1. Авторизация
make docker-pyro-auth

# 2. Проверка сессии
./scripts/docker-run-command.sh pyro ls -la *.session

# 3. Запуск воркера
./scripts/docker-dev.sh start pyro
```

## 🎯 Решение проблем с venv

### Проблема: venv не работает в системе
**Решение:** Используйте Docker контейнеры для разработки:

```bash
# Вместо активации venv
source venv/bin/activate

# Используйте:
./scripts/docker-dev.sh start bot
```

### Проблема: Нужно установить новые зависимости
**Решение:** Установите в контейнере:

```bash
# Войдите в контейнер
./scripts/docker-dev.sh shell bot

# Установите пакеты
pip install новый_пакет

# Обновите requirements.txt в хост-системе
pip freeze > requirements.txt

# Пересоберите образ
./scripts/docker-dev.sh build
```

### Проблема: Нужно отладить код
**Решение:** Используйте интерактивный режим:

```bash
# Запустите в интерактивном режиме
./scripts/docker-dev.sh start bot

# В контейнере:
python -c "import pdb; pdb.set_trace(); import your_module"
```

## 📁 Структура файлов

### Production режим
- `docker-compose.yml` - Продакшн конфигурация
- Автоматический запуск сервисов
- Логирование и мониторинг

### Development режим  
- `docker-compose.dev.yml` - Development конфигурация
- Интерактивные контейнеры
- Монтирование всего проекта
- Возможность изменения кода на лету

## 💡 Советы

1. **Всегда используйте development режим** для разработки
2. **Монтируется весь проект**, изменения в коде сразу видны в контейнере
3. **Сессии Pyrogram сохраняются** между перезапусками
4. **Используйте tmux/screen** внутри контейнера для длительных процессов
5. **Логи сохраняются** в хост-системе

## 🔄 Workflow разработки

1. Авторизация Pyrogram (один раз):
   ```bash
   make docker-pyro-auth
   ```

2. Разработка:
   ```bash
   ./scripts/docker-dev.sh start bot
   # Редактируйте код в IDE
   # Перезапускайте в контейнере
   ```

3. Тестирование:
   ```bash
   ./scripts/docker-dev.sh start pyro
   # Тестируйте Pyrogram функции
   ```

4. Production запуск:
   ```bash
   make start-docker
   ```

Теперь у вас есть полноценная интерактивная среда разработки в Docker! 🚀 