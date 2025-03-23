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
│   ├── bot/                   # Модули бота
│   │   ├── __init__.py
│   │   ├── __main__.py        # Точка входа
│   │   ├── commands.py        # Команды бота
│   │   └── handlers.py        # Обработчики сообщений
│   ├── workers/               # Воркеры для скачивания больших видео
│   │   ├── __init__.py
│   │   ├── pyro_auth.py       # Авторизация Pyrogram
│   │   └── pyro_worker.py     # Воркер Pyrogram
│   ├── utils/                 # Вспомогательные функции
│   │   ├── __init__.py
│   │   └── processor.py       # Обработка видео
│   └── config.py              # Конфигурация проекта
├── videos/                    # Директория для скачанных видео
├── audio/                     # Директория для извлеченного аудио
├── transcriptions/            # Директория для транскрипций
├── requirements.txt           # Зависимости проекта
├── .env.sample                # Пример файла с переменными окружения
├── .env                       # Файл с переменными окружения (создается пользователем)
├── pyro_auth_run.sh           # Скрипт для авторизации Pyrogram
├── pyro_worker_start.sh       # Запуск воркера Pyrogram
├── pyro_worker_stop.sh        # Остановка воркера Pyrogram
└── pyro_worker_status.sh      # Проверка статуса воркера Pyrogram
```

## Требования

- Python 3.8+
- FFmpeg (для извлечения аудио из видео)
- tmux (для запуска воркера)

## Лицензия

MIT 
