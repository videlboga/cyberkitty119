.PHONY: docs-validate test smoke place-sample dev-setup

docs-validate:
	@echo "Running docs metadata validator (Docker)"
	@./.github/scripts/run_metadata_validator_docker.sh

test:
	@echo "Running pytest in Docker"
	docker run --rm -v "$(PWD)":/work -w /work python:3.11-slim bash -lc "python -m pip install --upgrade pip >/dev/null && pip install pytest >/dev/null && pytest -q"

smoke:
	@echo "Run smoke test helper (requires compose running)"
	@./scripts/smoke_test_pipeline.sh

place-sample:
	@./scripts/place_test_file.sh

dev-setup:
	@echo "Enable local hooks: git config core.hooksPath .githooks"
	@echo "Run docs validator: make docs-validate"
# Makefile для Cyberkitty19 Transkribator

.PHONY: help install setup start start-api start-docker stop-docker logs clean clean-all test docker-test docker-shell docker-run docker-dev migrate revision backup-postgres

POSTGRES_USER ?= $(shell sed -n 's/^POSTGRES_USER=//p' .env | tail -1)
POSTGRES_DB ?= $(shell sed -n 's/^POSTGRES_DB=//p' .env | tail -1)

# Показать справку
help:
	@echo "🐱 Cyberkitty19 Transkribator - Команды управления проектом"
	@echo ""
	@echo "📦 Установка и настройка:"
	@echo "  make install     - Установить зависимости"
	@echo "  make setup       - Настроить окружение (.env файл)"
	@echo ""
	@echo "🚀 Запуск:"
	@echo "  make start       - Запустить Telegram бота"
	@echo "  make start-api   - Запустить API сервер"
	@echo "  make start-docker - Запустить через Docker"
	@echo ""
	@echo "🗂️ База данных:"
	@echo "  make migrate     - Применить миграции Alembic (upgrade head)"
	@echo "  make revision NAME=msg - Создать новую миграцию"
	@echo ""
	@echo "🐳 Docker интерактивность:"
	@echo "  make docker-shell     - Войти в оболочку Docker контейнера"
	@echo "  make docker-run       - Выполнить команду в контейнере"
	@echo "  make docker-dev       - Режим разработки Docker"
	@echo ""
	@echo "🧪 Тестирование:"
	@echo "  make docker-test - Тестирование в Docker"
	@echo "  make test        - Запустить pytest"
	@echo ""
	@echo "🛑 Остановка:"
	@echo "  make stop-docker - Остановить Docker сервисы"
	@echo ""
	@echo "📊 Мониторинг:"
	@echo "  make logs        - Показать логи Docker"
	@echo "  make status      - Статус сервисов"
	@echo ""
	@echo "🧹 Очистка:"
	@echo "  make clean       - Очистить временные файлы"
	@echo "  make clean-all   - Полная очистка (включая venv)"

# Установка зависимостей
install:
	@echo "📦 Установка зависимостей..."
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt
	@echo "✅ Зависимости установлены!"

# Настройка окружения
setup:
	@if [ ! -f .env ]; then \
		echo "📝 Создание .env файла..."; \
		cp env.sample .env; \
		echo "⚠️  Отредактируйте .env файл и добавьте ваши API ключи!"; \
	else \
		echo "✅ .env файл уже существует"; \
	fi
	@mkdir -p videos audio transcriptions

# Запуск Telegram бота
start:
	@echo "🤖 Запуск Telegram бота..."
	./scripts/start.sh

# Запуск API сервера
start-api:
	@echo "🌐 Запуск API сервера..."
	./scripts/start-api.sh

# Запуск через Docker
start-docker:
	@echo "🐳 Запуск через Docker..."
	./scripts/docker-start.sh

# Остановка Docker сервисов
stop-docker:
	@echo "🛑 Остановка Docker сервисов..."
	docker-compose down

# Показать логи
logs:
	@echo "📊 Логи сервисов:"
	docker-compose logs -f

# Статус сервисов
status:
	@echo "📈 Статус Docker сервисов:"
	docker-compose ps

# Очистка временных файлов
clean:
	@echo "🧹 Очистка временных файлов..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.log" -delete
	@echo "✅ Временные файлы очищены!"

# Полная очистка
clean-all: clean
	@echo "🧹 Полная очистка..."
	rm -rf venv/
	docker-compose down --rmi all --volumes --remove-orphans 2>/dev/null || true
	@echo "✅ Полная очистка завершена!"

# Тестирование в Docker
docker-test:
	@echo "🐳 Запуск тестирования в Docker..."
	./scripts/docker-test.sh

# Вход в интерактивную оболочку Docker
docker-shell:
	@echo "🐳 Вход в Docker оболочку..."
	@chmod +x scripts/docker-shell.sh
	./scripts/docker-shell.sh

# Выполнение команды в Docker контейнере
docker-run:
	@echo "🐳 Выполнение команды в Docker..."
	@chmod +x scripts/docker-run-command.sh
	@echo "Использование: make docker-run CONTAINER=<bot|api> CMD='<команда>'"
	@echo "Пример: make docker-run CONTAINER=bot CMD='python --version'"

# Docker development режим
docker-dev:
	@echo "🐳 Docker Development Mode..."
	@chmod +x scripts/docker-dev.sh
	@echo "Использование: ./scripts/docker-dev.sh <команда> [сервис]"
	@echo "Команды: start, shell, stop, build, logs"
	@echo "Сервисы: bot, api"
	@echo ""
	@echo "Примеры:"
	@echo "  ./scripts/docker-dev.sh start bot   - Запустить бот интерактивно"
	@echo "  ./scripts/docker-dev.sh shell api   - Войти в оболочку API"
	@echo "  ./scripts/docker-dev.sh stop        - Остановить все dev сервисы"

# Тестирование (заготовка)
test:
	@echo "🧪 Запуск pytest..."
	pytest -q

# Миграции базы данных
migrate:
	@echo "🗂️ Применяем миграции Alembic..."
	alembic upgrade head

revision:
	@if [ -z "$(NAME)" ]; then \
		echo "⚠️  Укажите имя миграции: make revision NAME=add_table"; \
		exit 1; \
	fi
	@echo "🗂️ Создаём миграцию '$(NAME)'..."
	alembic revision --autogenerate -m "$(NAME)"

backup-postgres:
	@mkdir -p backups
	@file="backups/postgres-backup-$$(date +%Y%m%d_%H%M%S).sql"; \
		echo "📦 Создание бекапа Postgres → $$file"; \
		docker compose exec -T postgres pg_dump -U $(POSTGRES_USER) $(POSTGRES_DB) > $$file; \
		echo "✅ Бекап сохранён: $$file"
