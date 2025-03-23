# Transkribator 🐱

Телеграм-бот для транскрибации видео с помощью Whisper и форматирования текста с помощью LLM.

## Возможности

- Транскрибация видео из Telegram с помощью Whisper
- Скачивание больших видео через Pyrogram или Telethon
- Форматирование транскрипции с помощью OpenAI GPT или OpenRouter (Claude, Gemini и др.)
- Удобный интерфейс с кнопками для получения сырой транскрипции
- Работа с видео любого размера

## Установка

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/your-username/transkribator.git
   cd transkribator
   ```

2. Создать виртуальное окружение и установить зависимости:
   ```bash
   python -m venv venv
   source venv/bin/activate   # На Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Скопировать файл `.env.sample` в `.env` и заполнить необходимые параметры:
   ```bash
   cp .env.sample .env
   ```

4. Редактировать файл `.env`, указав:
   - `TELEGRAM_BOT_TOKEN` - токен бота, полученный от @BotFather
   - `OPENAI_API_KEY` или `OPENROUTER_API_KEY` - API ключ для форматирования транскрипции
   - При необходимости работы с большими видео:
     - `PYROGRAM_WORKER_ENABLED=true`
     - `PYROGRAM_WORKER_CHAT_ID` - ID чата для обмена сообщениями между ботом и воркером
     - `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` - ключи API Telegram, полученные на https://my.telegram.org/apps

## Запуск бота

```bash
python -m transkribator_modules.bot
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
transkribator/
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
├── videos/                    # Директория для скачанных видео
├── audio/                     # Директория для извлеченного аудио
├── transcriptions/            # Директория для транскрипций
├── requirements.txt           # Зависимости проекта
├── .env.sample                # Пример файла с переменными окружения
├── .env                       # Файл с переменными окружения (создается пользователем)
├── cyberkitty_modular.py      # Точка входа, запуск основного бота
├── cyberkitty_modular_start.sh # Запуск бота в фоновом режиме
├── cyberkitty_modular_stop.sh  # Остановка бота
├── pyro_auth_run.sh           # Скрипт для авторизации Pyrogram
├── pyro_worker_start.sh       # Запуск воркера Pyrogram
├── pyro_worker_stop.sh        # Остановка воркера Pyrogram
└── pyro_worker_status.sh      # Проверка статуса воркера Pyrogram
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
