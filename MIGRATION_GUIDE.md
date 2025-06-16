# 🚀 Руководство по миграции CyberKitty Transkribator

## Переход с Pyrogram на локальный Bot API Server

### 📋 Обзор изменений

Новая архитектура заменяет Pyrogram worker на локальный Telegram Bot API Server для обработки больших файлов (до 2 ГБ).

#### ✅ Преимущества новой архитектуры:
- **Простота**: Нет необходимости в отдельном Pyrogram worker
- **Надежность**: Прямое копирование файлов вместо HTTP скачивания
- **Производительность**: Быстрее обработка больших файлов
- **Стабильность**: Меньше точек отказа

#### ❌ Что удаляется:
- Pyrogram worker контейнер
- Сложная логика переключения между API
- Зависимости от Telethon/Pyrogram для больших файлов

---

## 🔄 Процесс миграции

### 1. Автоматическая миграция (рекомендуется)

```bash
# Сделать скрипт исполняемым
chmod +x deploy_to_server.sh

# Запустить миграцию
./deploy_to_server.sh
```

### 2. Ручная миграция

#### Шаг 1: Подготовка
```bash
# Подключиться к серверу
ssh root@got_is_tod

# Создать резервную копию
cp -r /opt/cyberkitty-transkribator /opt/cyberkitty-transkribator-backup-$(date +%Y%m%d)

# Остановить старые сервисы
cd /opt/cyberkitty-transkribator
docker-compose down
```

#### Шаг 2: Обновление файлов
```bash
# Загрузить новые файлы (с локальной машины)
scp -r . root@got_is_tod:/opt/cyberkitty-transkribator/
```

#### Шаг 3: Настройка переменных окружения
```bash
# Создать .env файл на сервере
cat > .env << EOF
# CyberKitty Transkribator Configuration
BOT_TOKEN=ваш_токен_бота
DEEPINFRA_API_KEY=ваш_ключ_deepinfra

# Telegram Bot API Server
USE_LOCAL_BOT_API=true
LOCAL_BOT_API_URL=http://telegram-bot-api:8081
TELEGRAM_API_ID=29612572
TELEGRAM_API_HASH=fa4d9922f76dea00803d072510ced924

# Database
DATABASE_URL=sqlite:///./data/cyberkitty-transkribator.db

# Optional APIs
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/whisper-large-v3
EOF
```

#### Шаг 4: Запуск новых сервисов
```bash
# Сборка образов
docker-compose build

# Запуск сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

#### Шаг 5: Авторизация Bot API Server
```bash
# Интерактивная авторизация для больших файлов
python3 authorize_bot_api_server.py
```

---

## 🏗️ Архитектура

### Старая архитектура (Pyrogram)
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │ Pyrogram Worker │    │  DeepInfra API  │
│                 │◄──►│                 │    │                 │
│  (до 50 МБ)     │    │ (большие файлы) │◄──►│  (транскрипция) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Новая архитектура (Bot API Server)
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │ Bot API Server  │    │  DeepInfra API  │
│                 │◄──►│                 │    │                 │
│  (до 2 ГБ)      │    │ (локальные файлы)│◄──►│  (транскрипция) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## 🐳 Docker Compose изменения

### Удаленные сервисы:
- `pyro-worker` - Pyrogram worker контейнер

### Новые сервисы:
- `telegram-bot-api` - Локальный Bot API Server

### Обновленные сервисы:
- `bot` - Теперь использует локальный Bot API Server
- `api` - Без изменений

---

## 📁 Структура файлов

### Удаленные файлы:
```
transkribator_modules/workers/
├── pyro_auth.py
├── pyro_worker.py
└── pyro_worker.session*

scripts/
├── pyro_worker_start.sh
├── pyro_worker_stop.sh
└── pyro_worker_status.sh

Dockerfile.pyro
```

### Новые файлы:
```
Dockerfile.telegram-bot-api
entrypoint.sh
authorize_bot_api_server.py
transkribator_modules/utils/large_file_downloader.py
deploy_to_server.sh
MIGRATION_GUIDE.md
```

---

## 🔧 Конфигурация

### Переменные окружения

#### Обязательные:
```bash
BOT_TOKEN=7907324843:AAEJMec9IeP89y0Taka4k7hbvpjd7F1Frl4
DEEPINFRA_API_KEY=ваш_ключ
USE_LOCAL_BOT_API=true
LOCAL_BOT_API_URL=http://telegram-bot-api:8081
```

#### Для Bot API Server:
```bash
TELEGRAM_API_ID=29612572
TELEGRAM_API_HASH=fa4d9922f76dea00803d072510ced924
```

#### Удаленные переменные:
```bash
PYROGRAM_WORKER_ENABLED=true
PYROGRAM_WORKER_CHAT_ID=0
TELETHON_WORKER_CHAT_ID=0
```

---

## 🧪 Тестирование

### 1. Проверка базовой функциональности
```bash
# Отправить команду /start боту
# Ожидаемый результат: Приветственное сообщение
```

### 2. Проверка малых файлов (< 50 МБ)
```bash
# Отправить аудио/видео файл < 50 МБ
# Ожидаемый результат: Успешная транскрипция
```

### 3. Проверка больших файлов (> 50 МБ)
```bash
# Отправить аудио/видео файл > 50 МБ
# Ожидаемый результат: Успешная транскрипция через Bot API Server
```

### 4. Проверка логов
```bash
# Проверить логи на ошибки
docker-compose logs -f bot
```

---

## 🚨 Устранение неполадок

### Проблема: Bot API Server не запускается
```bash
# Проверить логи
docker-compose logs telegram-bot-api

# Проверить переменные окружения
docker-compose exec telegram-bot-api env | grep TELEGRAM

# Перезапустить сервис
docker-compose restart telegram-bot-api
```

### Проблема: Ошибка 404 при скачивании файлов
```bash
# Проверить авторизацию Bot API Server
python3 authorize_bot_api_server.py

# Проверить права доступа к файлам
docker-compose exec telegram-bot-api ls -la /var/lib/telegram-bot-api/
```

### Проблема: Ошибка 401 от DeepInfra
```bash
# Проверить API ключ
echo $DEEPINFRA_API_KEY

# Обновить ключ в .env файле
```

### Проблема: Конфликт портов
```bash
# Проверить занятые порты
netstat -tlnp | grep :9081

# Изменить порты в docker-compose.yml при необходимости
```

---

## 📊 Мониторинг

### Полезные команды:
```bash
# Статус всех сервисов
docker-compose ps

# Логи в реальном времени
docker-compose logs -f

# Использование ресурсов
docker stats --no-stream

# Проверка здоровья Bot API Server
curl -s http://localhost:9081/bot$BOT_TOKEN/getMe

# Проверка API сервера
curl -s http://localhost:9000/health
```

### Метрики для отслеживания:
- Время отклика Bot API Server
- Размер обрабатываемых файлов
- Количество успешных транскрипций
- Использование дискового пространства

---

## 🔄 Откат изменений

В случае проблем можно быстро откатиться к старой версии:

```bash
# Остановить новые сервисы
docker-compose down

# Восстановить из резервной копии
cp -r /opt/cyberkitty-transkribator-backup-YYYYMMDD/* /opt/cyberkitty-transkribator/

# Запустить старую версию
cd /opt/cyberkitty-transkribator
docker-compose up -d
```

---

## ✅ Чек-лист миграции

- [ ] Создана резервная копия
- [ ] Остановлены старые сервисы
- [ ] Загружены новые файлы
- [ ] Настроены переменные окружения
- [ ] Собраны Docker образы
- [ ] Запущены новые сервисы
- [ ] Выполнена авторизация Bot API Server
- [ ] Протестирована работа с малыми файлами
- [ ] Протестирована работа с большими файлами
- [ ] Проверены логи на ошибки
- [ ] Настроен мониторинг

---

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи: `docker-compose logs -f`
2. Убедитесь в правильности переменных окружения
3. Проверьте доступность Bot API Server
4. При необходимости выполните откат к резервной копии

**CyberKitty Team** 🐱‍💻 