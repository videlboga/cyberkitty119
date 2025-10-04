# Cyberkitty19 Transkribator 🐱

Телеграм-бот для транскрибации видео и аудио, который говорит как игривый киберкотёнок.

## 🚀 Возможности

- Транскрибация видео из Telegram
- Обработка YouTube ссылок
- Обработка Google Drive ссылок
- Создание структурированных саммори транскрипций
- Поддержка длинных видео
- Всё с кошачьим стилем общения!

## 🛠️ Технологии

- Python
- Telegram Bot API
- Telethon
- OpenRouter API (для обработки транскрипций с помощью LLM)
- DeepInfra (для транскрибации)
- yt-dlp (для загрузки с YouTube)
- PyDub (для работы с аудио)

## 📋 Установка и настройка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/transkribator.git
cd transkribator
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # На Linux/Mac
# или
venv\Scripts\activate  # На Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` и заполните следующими данными:
```
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# DeepInfra API Key
DEEPINFRA_API_KEY=your_deepinfra_api_key

# OpenAI API Key - используем тот же ключ для DeepInfra
OPENAI_API_KEY=your_deepinfra_api_key  # Same as DEEPINFRA_API_KEY

# OpenRouter API Key для обработки транскрипций
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=google/gemini-2.5-flash-lite

# Telegram User API Credentials
TELEGRAM_API_ID=your_telegram_api_id
TELEGRAM_API_HASH=your_telegram_api_hash
TELEGRAM_PHONE_NUMBER=your_phone_number
```

5. Запустите бота:
```bash
python cyberkitty119
```

## 🔑 Получение API ключей

- **Telegram Bot Token**: Создайте бота у [@BotFather](https://t.me/BotFather) в Telegram
- **DeepInfra API Key**: Зарегистрируйтесь на [DeepInfra](https://deepinfra.com/dashboard)
- **OpenRouter API Key**: Зарегистрируйтесь на [OpenRouter](https://openrouter.ai/)
- **Telegram API ID и Hash**: Получите на [my.telegram.org](https://my.telegram.org/)

## 🐾 Автор

Videlboga (и Cursor)

## 📜 Лицензия

Телеграм-бот для транскрибации видео с помощью Whisper и форматирования текста с помощью LLM.

## 🚀 Быстрое развертывание на сервере

**Для продакшн сервера:**
- 📖 [Подробная инструкция](PRODUCTION_DEPLOY.md) - Полное руководство по развертыванию
- ⚡ [Быстрое развертывание](QUICK_DEPLOY.md) - Развертывание одной командой
- 🗃️ [Миграция на PostgreSQL](POSTGRES_MIGRATION.md) - Перенос данных и проверка

**Быстрый старт на сервере:**
```bash
git clone https://github.com/your-username/cyberkitty19-transkribator.git
cd cyberkitty19-transkribator
./deploy.sh production
```

## Возможности

- Транскрибация видео из Telegram с помощью Whisper
- Скачивание больших видео напрямую через Telegram Bot API
- Форматирование транскрипции с помощью OpenAI GPT или OpenRouter (Claude, Gemini и др.)
- Удобный интерфейс с кнопками для получения сырой транскрипции
- Работа с видео любого размера
- 💰 Система монетизации через Telegram Stars
- 🔑 API для интеграции с внешними сервисами

## Установка

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/your-username/cyberkitty19-transkribator.git
   cd cyberkitty19-transkribator
   ```

2. Создать виртуальное окружение и установить зависимости:
   ```bash
   python -m venv venv
   source venv/bin/activate   # На Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Скопировать файл `env.sample` в `.env` и заполнить необходимые параметры:
   ```bash
   cp env.sample .env
   ```

4. Редактировать файл `.env`, указав:
   - `TELEGRAM_BOT_TOKEN` - токен бота, полученный от @BotFather
   - `OPENAI_API_KEY` или `OPENROUTER_API_KEY` - API ключ для форматирования транскрипции
   - `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` — если используете локальный Bot API Server

## Быстрый запуск

### Локальный запуск
```bash
# Простой запуск бота
./scripts/start.sh

# Запуск API сервера
./scripts/start-api.sh
```

### Миграции базы данных
```bash
# Применить все миграции
make migrate

# Создать новую миграцию (пример)
make revision NAME=add_new_table
```

### Docker запуск
```bash
# Запуск всех сервисов через Docker
./scripts/docker-start.sh
```

### Ручной запуск
```bash
# Telegram бот
python cyberkitty_modular.py

# API сервер
python api_server.py
```

## Структура проекта

```
cyberkitty19-transkribator/
├── transkribator_modules/     # Основные модули проекта
│   ├── __init__.py
│   ├── main.py                # Главная функция для запуска бота
│   ├── config.py              # Глобальные настройки и логгер
│   ├── bot/                   # Модули бота
│   │   ├── __init__.py
│   │   ├── commands.py        # Команды бота
│   │   └── handlers.py        # Обработчики сообщений
│   ├── audio/                 # Обработка аудио
│   │   ├── __init__.py
│   │   └── extractor.py       # Извлечение аудио из видео
│   ├── transcribe/            # Транскрибация аудио
│   │   ├── __init__.py
│   │   └── transcriber_v4.py  # Функции транскрибации и форматирования
│   └── utils/                 # Вспомогательные функции
│       ├── __init__.py
│       └── large_file_downloader.py  # Загрузка больших файлов через Bot API
├── requirements/              # Зависимости проекта
│   ├── base.txt               # Базовые зависимости
│   ├── bot.txt                # Зависимости для бота
│   └── api.txt                # Зависимости для API
├── scripts/                   # Скрипты управления
│   ├── start.sh               # Запуск бота
│   ├── start-api.sh           # Запуск API сервера
│   └── docker-start.sh        # Запуск через Docker
├── videos/                    # Директория для скачанных видео
├── audio/                     # Директория для извлеченного аудио
├── transcriptions/            # Директория для транскрипций
├── requirements.txt           # Основные зависимости
├── docker-compose.yml         # Docker Compose конфигурация
├── Dockerfile                 # Docker образ для бота
├── Dockerfile.api             # Docker образ для API
├── api_server.py              # FastAPI сервер
├── cyberkitty_modular.py      # Точка входа бота
├── env.sample                # Пример переменных окружения
```

### Детальное описание модулей

#### Основные файлы
- `cyberkitty_modular.py` - Точка входа, запускающая основной бот с модульной структурой
- `main.py` - Главная функция, инициализирует и запускает бот

#### Модуль `bot/`
- `commands.py` - Обработчики команд бота (`/start`, `/help`, `/status`, `/plans`, `/api`, `/promo`)
- `handlers.py` - Обработка входящих сообщений и файлов пользователей

#### Модуль `audio/`
- `extractor.py` - Содержит функцию `extract_audio_from_video()` для асинхронного извлечения аудио из видео с помощью ffmpeg

#### Модуль `transcribe/`
- `transcriber_v4.py` - Содержит функции:
  - `transcribe_audio()` - Транскрибация аудио с помощью Whisper
  - `format_transcript_with_llm()` - Форматирование с помощью LLM
  - `format_transcript_with_openrouter()` - Форматирование через OpenRouter API с расширенными инструкциями

#### Модуль `utils/`
- `large_file_downloader.py` - Загрузка крупных файлов Telegram c поддержкой chunked API

### Поток данных в системе

1. Пользователь отправляет видео боту
2. Бот скачивает файл напрямую через Telegram Bot API (с поддержкой больших файлов)
3. После скачивания видео происходит:
   - Извлечение аудио с помощью модуля audio/extractor.py
   - Транскрибация аудио с помощью модуля transcribe/transcriber_v4.py
   - Форматирование транскрипции с использованием улучшенных инструкций
   - Отправка пользователю форматированной транскрипции

## Требования

- Python 3.8+
- FFmpeg (для извлечения аудио из видео)

## Лицензия

MIT 
