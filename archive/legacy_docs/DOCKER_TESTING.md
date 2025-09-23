# 🐳 Тестирование Cyberkitty19 Transkribator в Docker с Pyrogram воркером

## 📋 Предварительные требования

1. **Docker и Docker Compose** установлены
2. **Файл .env** настроен с вашими данными
3. **Токен Telegram бота** получен от @BotFather

## 🔧 Настройка .env файла

Убедитесь, что ваш `.env` файл содержит:

```bash
# Основные настройки Telegram бота
TELEGRAM_BOT_TOKEN=ваш_реальный_токен_бота

# Настройки для Pyrogram воркера
PYROGRAM_WORKER_ENABLED=true
TELEGRAM_API_ID=21532963
TELEGRAM_API_HASH=66e38ebc131425924c2680e6c8fb6c09
PYROGRAM_WORKER_CHAT_ID=0

# API ключи для транскрибации (хотя бы один)
OPENAI_API_KEY=ваш_openai_ключ
OPENROUTER_API_KEY=ваш_openrouter_ключ
DEEPINFRA_API_KEY=ваш_deepinfra_ключ
REPLICATE_API_TOKEN=ваш_replicate_токен
```

## 🚀 Быстрый запуск тестирования

### Вариант 1: Автоматическое тестирование

```bash
# Запуск полного тестирования
make docker-test
```

### Вариант 2: Ручной запуск

```bash
# Сборка и запуск
make start-docker

# Просмотр логов
make logs

# Статус сервисов
make status
```

## 🏗️ Архитектура Docker

Проект запускает 3 контейнера:

1. **cyberkitty19-transkribator-bot** - основной Telegram бот
2. **cyberkitty19-transkribator-pyro-worker** - Pyrogram воркер для больших файлов
3. **cyberkitty19-transkribator-api** - веб API сервер (опционально)

## 🧪 Сценарии тестирования

### Тест 1: Проверка запуска сервисов

```bash
# Запуск
make start-docker

# Проверка статуса
docker-compose ps

# Ожидаемый результат: все контейнеры в статусе "Up"
```

### Тест 2: Проверка логов

```bash
# Логи основного бота
docker-compose logs bot

# Логи Pyrogram воркера
docker-compose logs pyro-worker

# Логи в реальном времени
docker-compose logs -f
```

### Тест 3: Тестирование бота в Telegram

1. Найдите вашего бота в Telegram
2. Отправьте `/start`
3. Отправьте небольшое видео (до 20 МБ)
4. Отправьте большое видео (более 20 МБ) для тестирования Pyrogram воркера

### Тест 4: Проверка API сервера

```bash
# API должен быть доступен на порту 8000
curl http://localhost:8000/health

# Или откройте в браузере
# http://localhost:8000
```

## 🔍 Диагностика проблем

### Проблема: Контейнеры не запускаются

```bash
# Проверка логов сборки
docker-compose build --no-cache

# Проверка логов запуска
docker-compose up --no-deps
```

### Проблема: Pyrogram воркер не аутентифицирован

```bash
# Подключение к контейнеру воркера
docker-compose exec pyro-worker bash

# Запуск аутентификации внутри контейнера
python -m transkribator_modules.workers.pyro_auth
```

### Проблема: Бот не отвечает

1. Проверьте токен в `.env`
2. Проверьте логи: `docker-compose logs bot`
3. Убедитесь, что контейнер запущен: `docker-compose ps`

### Проблема: Нет транскрибации

1. Проверьте API ключи в `.env`
2. Проверьте логи транскрибации: `docker-compose logs bot | grep -i transcrib`
3. Проверьте подключение к интернету из контейнера

## 📊 Мониторинг

### Полезные команды

```bash
# Статус всех контейнеров
make status

# Логи в реальном времени
make logs

# Перезапуск сервисов
docker-compose restart

# Остановка сервисов
make stop-docker

# Полная очистка
make clean-all
```

### Структура томов

- `./videos:/app/videos` - скачанные видео
- `./audio:/app/audio` - извлеченные аудио
- `./transcriptions:/app/transcriptions` - готовые транскрипции
- `./.env:/app/.env` - конфигурация

## 🐛 Отладка

### Подключение к контейнерам

```bash
# Основной бот
docker-compose exec bot bash

# Pyrogram воркер
docker-compose exec pyro-worker bash

# API сервер
docker-compose exec api bash
```

### Просмотр файлов внутри контейнера

```bash
# Структура проекта
docker-compose exec bot ls -la /app/

# Логи внутри контейнера
docker-compose exec bot tail -f /app/cyberkitty119.log

# Проверка переменных окружения
docker-compose exec bot env | grep TELEGRAM
```

### Ручной запуск компонентов

```bash
# Запуск только бота
docker-compose up bot

# Запуск только воркера
docker-compose up pyro-worker

# Запуск только API
docker-compose up api
```

## 🎯 Ожидаемые результаты

После успешного запуска:

1. ✅ Все 3 контейнера в статусе "Up"
2. ✅ Бот отвечает на команду `/start`
3. ✅ Небольшие видео обрабатываются напрямую
4. ✅ Большие видео передаются Pyrogram воркеру
5. ✅ API сервер доступен на порту 8000
6. ✅ Логи показывают успешную работу

## 🔄 Следующие шаги

После успешного тестирования:

1. Настройте production окружение
2. Добавьте мониторинг и алерты
3. Настройте автоматические бэкапы
4. Рассмотрите использование Docker Swarm или Kubernetes

## 📞 Поддержка

При проблемах:

1. Проверьте логи: `make logs`
2. Проверьте статус: `make status`
3. Перезапустите: `docker-compose restart`
4. Полная переустановка: `make clean-all && make docker-test` 