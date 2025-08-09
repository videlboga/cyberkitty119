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
OPENROUTER_MODEL=deepseek/deepseek-chat

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
- 🐳 [Docker тестирование](DOCKER_TESTING.md) - Тестирование в Docker

**Быстрый старт на сервере:**
```bash
git clone https://github.com/your-username/cyberkitty19-transkribator.git
cd cyberkitty19-transkribator
./deploy.sh production
```

## Возможности

- Транскрибация видео из Telegram с помощью Whisper
- Скачивание больших видео через Pyrogram или Telethon
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
   - При необходимости работы с большими видео:
     - `PYROGRAM_WORKER_ENABLED=true`
     - `PYROGRAM_WORKER_CHAT_ID` - ID чата для обмена сообщениями между ботом и воркером
      - `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` - ключи API Telegram, полученные на https://my.telegram.org/apps

## Быстрый запуск

### Локальный запуск
```bash
# Простой запуск бота
./scripts/start.sh

# Запуск API сервера
./scripts/start-api.sh
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

## Настройка воркера для больших видео

Если вы планируете работать с большими видео (>20 МБ), настройте Pyrogram воркер:

1. Запустите скрипт авторизации (только один раз):
   ```bash
   chmod +x pyro_auth_run.sh
   ./pyro_auth_run.sh
   ```

2. Запустите Pyrogram воркер в tmux:
   ```bash
   chmod +x pyro_worker_start.sh pyro_worker_stop.sh pyro_worker_status.sh
   ./pyro_worker_start.sh
   ```

3. Проверьте статус воркера:
   ```bash
   ./pyro_worker_status.sh
   ```

4. Для остановки воркера:
   ```bash
   ./pyro_worker_stop.sh
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
│   ├── workers/               # Воркеры для скачивания больших видео
│   │   ├── __init__.py
│   │   ├── pyro_auth.py       # Авторизация Pyrogram
│   │   └── pyro_worker.py     # Воркер Pyrogram
│   ├── audio/                 # Обработка аудио
│   │   ├── __init__.py
│   │   └── extractor.py       # Извлечение аудио из видео
│   ├── transcribe/            # Транскрибация аудио
│   │   ├── __init__.py
│   │   └── transcriber.py     # Функции транскрибации и форматирования
│   └── utils/                 # Вспомогательные функции
│       ├── __init__.py
│       └── processor.py       # Обработка видео
├── requirements/              # Зависимости проекта
│   ├── base.txt               # Базовые зависимости
│   ├── bot.txt                # Зависимости для бота
│   └── api.txt                # Зависимости для API
├── scripts/                   # Скрипты управления
│   ├── start.sh               # Запуск бота
│   ├── start-api.sh           # Запуск API сервера
│   └── docker-start.sh        # Запуск через Docker
├── archive/                   # Архив неиспользуемых файлов
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
├── pyro_auth_run.sh           # Авторизация Pyrogram
├── pyro_worker_start.sh       # Запуск воркера Pyrogram
├── pyro_worker_stop.sh        # Остановка воркера Pyrogram
└── pyro_worker_status.sh      # Статус воркера Pyrogram
```

### Детальное описание модулей

#### Основные файлы
- `cyberkitty_modular.py` - Точка входа, запускающая основной бот с модульной структурой
- `main.py` - Главная функция, инициализирует и запускает бот

#### Модуль `bot/`
- `commands.py` - Содержит обработчики команд бота:
  - `/start` - Начало работы с ботом
  - `/help` - Вывод справки
  - `/status` - Проверка статуса бота
  - `/rawtranscript` - Получение сырой транскрипции
- `handlers.py` - Обрабатывает входящие сообщения, включая видео файлы

#### Модуль `audio/`
- `extractor.py` - Содержит функцию `extract_audio_from_video()` для асинхронного извлечения аудио из видео с помощью ffmpeg

#### Модуль `transcribe/`
- `transcriber.py` - Содержит функции:
  - `transcribe_audio()` - Транскрибация аудио с помощью Whisper
  - `format_transcript_with_llm()` - Форматирование с помощью LLM
  - `format_transcript_with_openrouter()` - Форматирование через OpenRouter API с расширенными инструкциями

#### Модуль `utils/`
- `processor.py` - Содержит функции:
  - `process_video()` - Обработка видео, полученного напрямую от пользователя
  - `process_video_file()` - Обработка видео из файловой системы (после скачивания воркером)

#### Модуль `workers/`
- `pyro_auth.py` - Содержит функцию `main()` для аутентификации Pyrogram клиента
- `pyro_worker.py` - Содержит:
  - `download_and_save_video()` - Скачивание видео из сообщения
  - `from_our_bot()` - Фильтр для проверки, что сообщение от нашего бота
  - `handle_bot_messages()` - Обработка команд для скачивания видео

### Поток данных в системе

1. Пользователь отправляет видео боту
2. Бот проверяет размер видео:
   - Если видео маленькое - скачивает напрямую
   - Если большое - отправляет в чат с Pyro воркером для скачивания
3. После скачивания видео происходит:
   - Извлечение аудио с помощью модуля audio/extractor.py
   - Транскрибация аудио с помощью модуля transcribe/transcriber.py
   - Форматирование транскрипции с использованием улучшенных инструкций
   - Отправка пользователю форматированной транскрипции

## Требования

- Python 3.8+
- FFmpeg (для извлечения аудио из видео)
- tmux (для запуска воркера)

## Лицензия

MIT 
