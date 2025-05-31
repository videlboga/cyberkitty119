# Настройка и тестирование Telegram бота с Pyrogram воркером

## 🔧 Настройка конфигурации

### 1. Создание файла .env

Создайте файл `.env` в корневой директории проекта со следующими настройками:

```bash
# Основные настройки Telegram бота
TELEGRAM_BOT_TOKEN=ваш_токен_бота_здесь

# Настройки для Pyrogram воркера (для больших файлов)
PYROGRAM_WORKER_ENABLED=true
TELEGRAM_API_ID=21532963
TELEGRAM_API_HASH=66e38ebc131425924c2680e6c8fb6c09
PYROGRAM_WORKER_CHAT_ID=0

# Настройки для Telethon воркера (альтернативный)
TELETHON_WORKER_CHAT_ID=0

# API ключи для транскрибации
OPENAI_API_KEY=ваш_openai_ключ_здесь
OPENROUTER_API_KEY=ваш_openrouter_ключ_здесь
OPENROUTER_MODEL=anthropic/claude-3-opus:beta
DEEPINFRA_API_KEY=ваш_deepinfra_ключ_здесь

# Настройки для Replicate API (новая интеграция)
REPLICATE_API_TOKEN=ваш_replicate_токен_здесь
REPLICATE_WHISPER_MODEL=carnifexer/whisperx
REPLICATE_WHISPER_DIARIZATION_MODEL=thomasmol/whisper-diarization

# Настройки логирования
LOG_LEVEL=INFO
```

### 2. Получение токена Telegram бота

1. Найдите @BotFather в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен в переменную `TELEGRAM_BOT_TOKEN`

## 🚀 Запуск и тестирование

### Шаг 1: Установка зависимостей

```bash
# Установка всех зависимостей
make install

# Или вручную:
pip install -r requirements.txt
```

### Шаг 2: Аутентификация Pyrogram воркера

Перед первым запуском нужно аутентифицировать Pyrogram воркер:

```bash
# Запуск аутентификации
./pyro_auth_run.sh
```

Следуйте инструкциям:
1. Введите номер телефона
2. Введите код подтверждения из Telegram
3. При необходимости введите пароль двухфакторной аутентификации

### Шаг 3: Запуск Pyrogram воркера

```bash
# Запуск воркера в tmux-сессии
./pyro_worker_start.sh

# Проверка статуса
./pyro_worker_status.sh
```

### Шаг 4: Запуск основного бота

```bash
# Запуск бота
make start

# Или вручную:
python cyberkitty_modular.py
```

## 🧪 Тестирование функциональности

### Тест 1: Проверка базовой работы бота

1. Найдите вашего бота в Telegram
2. Отправьте команду `/start`
3. Убедитесь, что бот отвечает

### Тест 2: Тестирование транскрибации небольших видео

1. Отправьте боту небольшое видео (до 20 МБ)
2. Бот должен скачать и обработать его напрямую
3. Проверьте получение транскрипции

### Тест 3: Тестирование Pyrogram воркера с большими видео

1. Отправьте боту большое видео (более 20 МБ)
2. Бот должен переслать видео в рабочий чат для Pyrogram воркера
3. Pyrogram воркер должен скачать видео
4. Проверьте логи воркера: `tmux attach -t pyro_worker`

### Тест 4: Проверка логов

```bash
# Основные логи бота
tail -f cyberkitty119.log

# Логи Pyrogram воркера
tail -f pyro_worker.log

# Статус воркера
./pyro_worker_status.sh
```

## 🔍 Диагностика проблем

### Проблема: Pyrogram воркер не запускается

1. Проверьте файл `.env`:
   ```bash
   cat .env | grep -E "(API_ID|API_HASH)"
   ```

2. Проверьте аутентификацию:
   ```bash
   ls -la transkribator_modules/workers/pyro_worker.session*
   ```

3. Проверьте логи:
   ```bash
   tail -f pyro_worker.log
   ```

### Проблема: Бот не отвечает

1. Проверьте токен бота в `.env`
2. Проверьте логи: `tail -f cyberkitty119.log`
3. Убедитесь, что бот запущен: `ps aux | grep cyberkitty`

### Проблема: Транскрибация не работает

1. Проверьте API ключи в `.env`
2. Проверьте подключение к интернету
3. Проверьте логи транскрибации

## 📊 Мониторинг

### Полезные команды

```bash
# Статус всех компонентов
make status

# Просмотр логов в реальном времени
tail -f cyberkitty119.log pyro_worker.log

# Остановка воркера
./pyro_worker_stop.sh

# Перезапуск воркера
./pyro_worker_stop.sh && ./pyro_worker_start.sh
```

### Структура логов

- `cyberkitty119.log` - основные логи бота
- `pyro_worker.log` - логи Pyrogram воркера
- `videos/` - скачанные видео
- `audio/` - извлеченные аудио файлы
- `transcriptions/` - готовые транскрипции

## 🎯 Следующие шаги

После успешного тестирования:

1. Настройте автозапуск через systemd
2. Настройте мониторинг через `bot_watchdog.sh`
3. Настройте очистку медиафайлов через `cleanup_media.sh`
4. Рассмотрите развертывание через Docker

## 📞 Поддержка

При возникновении проблем:

1. Проверьте логи
2. Убедитесь в правильности настроек `.env`
3. Проверьте подключение к интернету
4. Перезапустите компоненты 