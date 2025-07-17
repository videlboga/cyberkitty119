# 🐱 Локальный бот CyberKitty

Локальный бот для работы с API сервером вместо Telegram API. Позволяет обрабатывать большие файлы без ограничений Telegram.

## 🚀 Быстрый старт

### 1. Запуск через Docker Compose (рекомендуется)

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f local-bot

# Остановка
docker-compose down
```

### 2. Запуск вручную

```bash
# Запуск API сервера
python api_server.py

# В другом терминале - запуск локального бота
python local_bot.py
```

## 📁 Структура директорий

```
cyberkitty19-transkribator/
├── videos/              # Видео файлы для обработки
├── audio/               # Аудио файлы для обработки  
├── transcriptions/      # Результаты транскрибации
├── api_server.py        # API сервер
├── local_bot.py         # Скрипт запуска локального бота
└── transkribator_modules/
    ├── local_bot.py     # Модуль локального бота
    └── api_client.py    # Клиент для работы с API
```

## ⚙️ Настройка

### Переменные окружения

Создайте файл `.env`:

```bash
# API ключи для транскрибации
DEEPINFRA_API_KEY=ваш_ключ_deepinfra
OPENROUTER_API_KEY=ваш_ключ_openrouter
OPENROUTER_MODEL=anthropic/claude-3-opus:beta

# Настройки локального бота
LOCAL_API_URL=http://localhost:8000
LOCAL_API_KEY=опциональный_ключ_для_api

# Настройки для больших файлов
MAX_FILE_SIZE_MB=2048
```

## 🔄 Как это работает

### Архитектура

1. **API сервер** (`api_server.py`) - обрабатывает запросы на транскрибацию
2. **Локальный бот** (`local_bot.py`) - мониторит директории и отправляет файлы в API
3. **API клиент** (`api_client.py`) - обеспечивает связь между ботом и API

### Поток обработки

1. Пользователь помещает видео/аудио файл в директорию `videos/` или `audio/`
2. Локальный бот обнаруживает новый файл
3. Бот отправляет файл в API сервер через HTTP
4. API сервер обрабатывает файл (извлечение аудио + транскрибация)
5. Результат сохраняется в директорию `transcriptions/`

## 📊 Поддерживаемые форматы

### Видео
- MP4, AVI, MOV, MKV, WebM, FLV, M4V

### Аудио  
- MP3, WAV, FLAC, M4A, AAC, OGG

## 🔧 API Endpoints

### Основные
- `GET /health` - проверка состояния сервера
- `POST /transcribe` - транскрибация файла
- `GET /transcription/{task_id}/status` - статус транскрибации

### Планы и пользователи
- `GET /plans` - список тарифных планов
- `GET /user/info` - информация о пользователе

## 🐛 Отладка

### Логи

```bash
# Просмотр логов локального бота
docker-compose logs -f local-bot

# Просмотр логов API сервера  
docker-compose logs -f api
```

### Проверка состояния

```bash
# Проверка API сервера
curl http://localhost:8000/health

# Проверка DeepInfra
curl http://localhost:8000/check_deepinfra_connection
```

## 📈 Производительность

### Ограничения

- **Размер файла**: до 2GB (настраивается)
- **Длительность**: без ограничений
- **Параллельная обработка**: поддерживается

### Оптимизация

- Автоматическое сжатие аудио для API
- Сегментация больших файлов
- Кэширование результатов

## 🔒 Безопасность

- API ключи для аутентификации
- Проверка типов файлов
- Ограничение размера загружаемых файлов
- Изоляция в Docker контейнерах

## 🆘 Устранение неполадок

### Проблема: Бот не видит новые файлы
**Решение**: Проверьте права доступа к директориям `videos/` и `audio/`

### Проблема: Ошибка подключения к API
**Решение**: Убедитесь, что API сервер запущен на порту 8000

### Проблема: Файлы не обрабатываются
**Решение**: Проверьте логи и убедитесь, что API ключи настроены правильно

## 📝 Примеры использования

### Обработка видео файла

1. Скопируйте видео в `videos/`
2. Дождитесь появления файлов в `transcriptions/`
3. Результат будет в формате:
   ```
   filename_timestamp.txt          # Форматированная транскрипция
   filename_timestamp_raw.txt      # Сырая транскрипция
   ```

### Программное использование API

```python
import aiohttp

async def transcribe_file(file_path):
    async with aiohttp.ClientSession() as session:
        with open(file_path, 'rb') as f:
            data = aiohttp.FormData()
            data.add_field('file', f, filename=file_path.name)
            
            async with session.post('http://localhost:8000/transcribe', data=data) as resp:
                return await resp.json()
``` 