# 🐱 Transkribator Bot (КиберКотёнок)

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
python bot.py
```

## 🔑 Получение API ключей

- **Telegram Bot Token**: Создайте бота у [@BotFather](https://t.me/BotFather) в Telegram
- **DeepInfra API Key**: Зарегистрируйтесь на [DeepInfra](https://deepinfra.com/dashboard)
- **OpenRouter API Key**: Зарегистрируйтесь на [OpenRouter](https://openrouter.ai/)
- **Telegram API ID и Hash**: Получите на [my.telegram.org](https://my.telegram.org/)

## 🐾 Автор

КиберКотёнок Transkribator

## 📜 Лицензия

MIT 