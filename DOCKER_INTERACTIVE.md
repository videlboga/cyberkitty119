# 🐳 Интерактивная работа с Docker

Проблемы с локальным виртуальным окружением можно обойти, разворачивая все сервисы проекта в Docker-контейнерах. Ниже — быстрый сценарий для разработки и отладки.

## 🚀 Быстрый старт

### 1. Интерактивные оболочки
```bash
# Войти в оболочку любого контейнера
make docker-shell
# Выберите: 1) bot, 2) api

# Или напрямую:
./scripts/docker-shell.sh bot  # Telegram бот
./scripts/docker-shell.sh api  # FastAPI сервер
```

### 2. Development-режим (рекомендуется)
```bash
# Запустить сервис в интерактивном режиме
./scripts/docker-dev.sh start bot  # Бот
./scripts/docker-dev.sh start api  # API

# Войти в уже запущенный контейнер
./scripts/docker-dev.sh shell bot
./scripts/docker-dev.sh shell api

# Остановить все dev-контейнеры
./scripts/docker-dev.sh stop
```

## 🔧 Полезные команды

```bash
# Проверить версию Python в контейнере
./scripts/docker-run-command.sh bot python --version

# Установить пакет прямо в контейнере
./scripts/docker-run-command.sh bot pip install requests

# Запустить тесты
./scripts/docker-run-command.sh bot python -m pytest

# Смотреть логи бота
./scripts/docker-run-command.sh bot tail -f *.log
```

## 🎯 Решение проблем с venv

Если `venv` недоступен на сервере/локально:

```bash
# Вместо активации виртуального окружения
source venv/bin/activate

# Используйте интерактивный контейнер
./scripts/docker-dev.sh start bot
```

Чтобы добавить новые зависимости:

```bash
./scripts/docker-dev.sh shell bot
pip install название_пакета
pip freeze > requirements.txt
./scripts/docker-dev.sh build
```

## 📁 Где править код

- `docker-compose.dev.yml` — конфигурация для разработки
- `docker-compose.yml` — продакшн конфигурация
- В dev-режиме проект монтируется как volume, поэтому изменения из IDE мгновенно попадают в контейнеры.

## 🔄 Базовый workflow

1. Запустите нужный сервис в development-режиме:
   ```bash
   ./scripts/docker-dev.sh start bot
   ```
2. Внесите изменения в код и проверяйте их сразу в контейнере.
3. Для проверки API используйте:
   ```bash
   ./scripts/docker-dev.sh start api
   ```
4. Для продакшн-запуска — `make start-docker`.

Так вы получите повторяемую среду разработки без танцев с локальными зависимостями. 🚀
