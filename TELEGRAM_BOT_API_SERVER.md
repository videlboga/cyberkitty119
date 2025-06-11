# 🚀 CyberKitty Transkribator - Telegram Bot API Server Edition

## 📖 Обзор

Эта версия проекта полностью переписана для работы с **Telegram Bot API Server** вместо Pyrogram. Это официальное решение от Telegram для обработки больших файлов (до 2 ГБ).

## 🏗️ Архитектура

### Компоненты системы:

1. **Telegram Bot API Server** - Официальный сервер Telegram для обработки больших файлов
2. **CyberKitty Bot** - Основной бот для обработки файлов
3. **API Server** - HTTP API для внешних интеграций (опционально)

## 🔧 Компоненты

### 1. Telegram Bot API Server
```yaml
telegram-bot-api:
  image: aiogram/telegram-bot-api:latest
  ports:
    - "8081:8081"
  environment:
    - TELEGRAM_API_ID=${TELEGRAM_API_ID}
    - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}
```

### 2. Bot Service
```yaml
bot:
  build: .
  environment:
    - USE_LOCAL_BOT_API=true
    - LOCAL_BOT_API_URL=http://telegram-bot-api:8081
```

## 💪 Преимущества

### ✅ По сравнению с Pyrogram подходом:
- **Официальная поддержка** - Используется официальный сервер Telegram
- **Стабильность** - Нет проблем с сессиями и аутентификацией
- **Простота** - Стандартный python-telegram-bot без дополнительных воркеров
- **Надежность** - Меньше точек отказа, проще диагностика
- **Масштабируемость** - Лучше подходит для продакшена

### 🎯 Ключевые возможности:
- Поддержка файлов до **2 ГБ**
- Автоматическое извлечение аудио из видео
- Поддержка множества форматов
- Интеграция с DeepInfra Whisper API
- LLM форматирование транскрипций

## 🚀 Запуск

### Быстрый старт:
```bash
# 1. Клонируем репозиторий
git clone <repo> && cd transkribator

# 2. Переключаемся на ветку Bot API Server
git checkout telegram_bot_api_server

# 3. Настраиваем переменные окружения
cp env.sample .env
# Редактируем .env файл

# 4. Запускаем систему
docker-compose up -d
```

### Необходимые переменные:
```env
BOT_TOKEN=your_bot_token_here
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
DEEPINFRA_API_KEY=your_deepinfra_key_here
```

## 📁 Структура проекта

```
transkribator/
├── docker-compose.yml          # Основная конфигурация
├── Dockerfile                  # Образ для бота
├── requirements.txt            # Python зависимости
├── transkribator_modules/
│   ├── config.py              # Конфигурация
│   ├── main.py                # Точка входа бота
│   ├── audio/
│   │   └── extractor.py       # Извлечение аудио
│   ├── bot/
│   │   └── handlers.py        # Обработчики сообщений
│   └── transcribe/
│       └── transcriber.py     # Транскрипция
└── telegram-bot-api-data/     # Данные Bot API Server
```

## 🔄 Workflow обработки файлов

1. **Получение файла** → Bot получает файл через Telegram Bot API Server
2. **Валидация** → Проверка размера и формата файла
3. **Скачивание** → Файл скачивается локально (до 2 ГБ)
4. **Извлечение аудио** → Если видео, извлекается аудио (ffmpeg)
5. **Сжатие** → Аудио сжимается для API (MP3, 64kbps)
6. **Транскрипция** → Отправка в DeepInfra Whisper API
7. **Форматирование** → LLM обработка (опционально)
8. **Отправка результата** → Транскрипция отправляется пользователю

## 📊 Поддерживаемые форматы

### 🎥 Видео:
- MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V, 3GP

### 🎵 Аудио:
- MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS

## ⚙️ Конфигурация

### Основные параметры:
```env
# Ограничения файлов
MAX_FILE_SIZE_MB=2000
MAX_AUDIO_DURATION_MINUTES=240

# Обработка
ENABLE_LLM_FORMATTING=true
ENABLE_SEGMENTATION=true
SEGMENT_DURATION_SECONDS=30
```

## 🔍 Мониторинг

### Команды бота:
- `/start` - Приветствие и инструкции
- `/help` - Подробная справка
- `/status` - Статус системы

### Логи:
```bash
# Логи бота
docker logs cyberkitty19-transkribator-bot

# Логи Bot API Server
docker logs cyberkitty19-telegram-bot-api

# Логи API сервера
docker logs cyberkitty19-transkribator-api
```

## 🛠️ Разработка

### Локальная разработка:
```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск в режиме разработки
python -m transkribator_modules.main
```

### Структура обработчиков:
- `start_command()` - Команда /start
- `handle_document()` - Обработка документов
- `handle_video()` - Обработка видео
- `handle_audio()` - Обработка аудио
- `process_video_file()` - Обработка видео файлов
- `process_audio_file()` - Обработка аудио файлов

## 🆚 Сравнение с Pyrogram версией

| Аспект | Pyrogram версия | Bot API Server версия |
|--------|----------------|---------------------|
| Максимальный размер файла | 2 ГБ | 2 ГБ |
| Сложность развертывания | Высокая (сессии, воркеры) | Низкая |
| Стабильность | Средняя | Высокая |
| Официальная поддержка | Нет | Да |
| Количество компонентов | 3 (бот + воркер + api) | 2 (бот + api server) |
| Зависимости | Pyrogram + python-telegram-bot | Только python-telegram-bot |

## 🎯 Рекомендации

### Для продакшена:
- ✅ Используйте Bot API Server версию
- ✅ Простота развертывания и поддержки
- ✅ Официальная поддержка от Telegram
- ✅ Меньше точек отказа

### Для разработки:
- ✅ Легче отладка и тестирование
- ✅ Стандартные паттерны python-telegram-bot
- ✅ Лучшая документация и сообщество

## 📚 Дополнительные ресурсы

- [Telegram Bot API Server](https://core.telegram.org/bots/api#using-a-local-bot-api-server)
- [python-telegram-bot документация](https://docs.python-telegram-bot.org/)
- [DeepInfra Whisper API](https://deepinfra.com/openai/whisper-large-v3-turbo)

---

**CyberKitty Team** 🐱 