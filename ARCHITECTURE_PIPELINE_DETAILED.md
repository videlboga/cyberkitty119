# 🏗️ Архитектура Пайплайна Бота - Полный Разбор

## 📊 Общая Архитектура

Система состоит из **5 контейнеров Docker**, каждый с специальной роль. Вот как они взаимодействуют:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TELEGRAM USER INTERACTION                         │
│         (File uploads, commands, messages)                          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│    TELEGRAM BOT API SERVER (Port 9081)                              │
│    Container: cyberkitty19-telegram-bot-api                         │
│    • Handles Telegram protocol                                       │
│    • Receives/sends messages                                         │
│    • Manages file downloads                                          │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│    BOT CONTAINER (Main Logic) (Port 9000 for polling)               │
│    Container: cyberkitty19-transkribator-bot                        │
│    • Receives updates from Telegram Bot API                         │
│    • Processes messages (handles_message)                           │
│    • Detects media/links/commands                                   │
│    • Creates background tasks                                       │
│    • Sends results back to user                                     │
└────────────────────────┬────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────────┐  ┌───────────┐  ┌─────────────┐
    │POSTGRES DB │  │QUEUE JOBS │  │API REQUESTS │
    │Container:  │  │ (in DB)   │  │to services  │
    │postgres    │  │           │  │             │
    └────────────┘  └─────┬─────┘  └─────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│    WORKER CONTAINER (Job Processor)                                 │
│    Container: cyberkitty19-transkribator-worker                     │
│    • Pulls jobs from queue (job_worker.py)                          │
│    • Processes media (transcription, formatting)                    │
│    • Calls external APIs (DeepInfra, OpenRouter, etc)              │
│    • Saves results to DB                                            │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│    API CONTAINER (REST API) (Port 9000)                             │
│    Container: cyberkitty19-transkribator-api                        │
│    • Provides REST endpoints                                        │
│    • Handles searches, data management                              │
│    • Can be used by external services                               │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Детальный Пайплайн Обработки Медиа

### **Стадия 1: БОТ ПОЛУЧАЕТ СООБЩЕНИЕ**

```python
# В: cyberkitty19-transkribator-bot
# Функция: main() → handle_message()

1. Telegram Bot API Server отправляет update
2. Bot polling loop получает update
3. Router (telegram.ext) определяет тип сообщения
4. MessageHandler вызывает handle_message()
```

**Логика в `handle_message()`:**

```
┌─ Определяем тип контента ─┐
│
├─ Текстовое сообщение?
│  └─ Проверяем: команда ли? → Если команда, пропускаем (CommandHandler обработает)
│  └─ Проверяем: QA сессия? → Если есть, ответ на вопрос
│  └─ Проверяем: промокод? → Обработка промокода
│  └─ Проверяем: ссылка? → Переход на обработку ссылки
│
├─ Видео?
│  └─ Логируем → Создаем фоновую задачу → process_video_file()
│
├─ Аудио?
│  └─ Логируем → Создаем фоновую задачу → process_audio_file()
│
├─ Голос?
│  └─ Логируем → Создаем фоновую задачу → process_audio_file()
│
├─ Документ?
│  └─ Проверяем расширение файла
│  └─ Если видео (.mp4, .webm, .mkv) → process_video_file()
│  └─ Если аудио (.mp3, .wav, .flac) → process_audio_file()
│
└─ Ссылка? (YouTube, VK, Google Drive, Dropbox, Mega, Yandex Disk)
   └─ Определяем тип сервиса
   └─ Создаем фоновую задачу → _handle_xxx_link()
```

**Важно:** Все тяжелые операции запускаются **асинхронно в фоновых задачах** через `_schedule_background_task()`

---

### **Стадия 2: ФОНОВАЯ ЗАДАЧА - СКАЧИВАНИЕ И ПОДГОТОВКА**

```python
# В: cyberkitty19-transkribator-bot (фоновая задача)
# Функция: process_video_file() или process_audio_file()

1. Скачиваем файл из Telegram
2. Сохраняем в ./videos/ или ./audio/
3. Извлекаем аудио (FFmpeg) → сохраняем .mp3
4. Получаем длительность файла
5. Создаем запись в БД (ProcessingJob)
6. ВСЁ ОСТАЛЬНОЕ передается WORKER-у через очередь!
```

**Код:**
```python
async def process_video_file(update, context, video, status_message):
    # 1. Скачиваем
    file_path = await download_file_from_telegram(video.file_id)
    
    # 2. Извлекаем аудио
    audio_path = await extract_audio_from_video(file_path)
    
    # 3. Получаем метаданные
    duration = get_media_duration(audio_path)
    file_size = os.path.getsize(file_path)
    
    # 4. Создаем job в БД
    job = ProcessingJob(
        user_id=update.effective_user.id,
        status="pending",
        media_path=str(audio_path),
        job_type="transcribe_deepinfra",  # ← Тип джоба!
    )
    db.add(job)
    db.commit()
    
    # БОТ НА ЭТОМ ЗАКАНЧИВАЕТ свою работу!
    # Отправляет пользователю "⏳ Обработка..."
```

**Ключевой момент:** БОТ не обрабатывает медиа сам! Он только:
1. ✅ Скачивает файл
2. ✅ Создает job в БД
3. ✅ Отправляет пользователю "обработка..."
4. ❌ НЕ ждет транскрибации

---

### **Стадия 3: WORKER ОБРАБАТЫВАЕТ ЗАДАЧУ**

```python
# В: cyberkitty19-transkribator-worker
# Главная функция: job_worker.py

while True:
    1. Опрашиваем БД каждые N секунд (JOB_POLL_INTERVAL)
    2. Берем job со статусом "pending"
    3. Вызываем dispatch_job(job) → определяем тип обработки
    4. В зависимости от типа вызываем нужный обработчик
```

**Типы jobs:**
- `transcribe_deepinfra` - Транскрибация через DeepInfra API
- `transcribe_openai` - Транскрибация через OpenAI
- `transcribe_openrouter` - Транскрибация через OpenRouter
- `format_transcript` - Форматирование текста через LLM
- Другие типы...

**Обработка конкретного job:**

```python
# В: transkribator_modules/jobs/handlers.py

def dispatch_job(job: ProcessingJob):
    if job.job_type == "transcribe_deepinfra":
        return handle_transcribe_deepinfra(job)
    elif job.job_type == "format_transcript":
        return handle_format_transcript(job)
    # ... другие типы
```

**Содержимое `handle_transcribe_deepinfra()`:**

```python
def handle_transcribe_deepinfra(job):
    # 1. Читаем аудио файл
    audio_path = job.media_path
    
    # 2. Вызываем DeepInfra API с файлом
    response = requests.post(
        "https://api.deepinfra.com/v1/audio/transcription",
        files={"audio": open(audio_path, "rb")},
        data={"model": "openai/whisper-large-v3"},
        headers={"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}
    )
    
    # 3. Получаем результат
    transcript = response.json()["text"]
    segments = response.json()["segments"]
    
    # 4. Если нужна обработка - создаем новый job "format_transcript"
    if needs_formatting:
        create_job(
            user_id=job.user_id,
            job_type="format_transcript",
            media_path=audio_path,
            payload={"transcript": transcript}
        )
        job.status = "pending_format"  # ← ПРОМЕЖУТОЧНЫЙ СТАТУС!
    
    # 5. Если обработка завершена - сохраняем результат в БД
    job.status = "completed"
    job.result = {
        "transcript": transcript,
        "segments": segments
    }
    db.commit()
```

**Важная деталь:** Job может порождать другие jobs! Это называется **job chaining**.

---

### **Стадия 4: БОТ ДОСТАВЛЯЕТ РЕЗУЛЬТАТ**

```
Есть ДВА варианта:

Вариант А: POLLING (бот опрашивает БД)
├─ БОТ периодически проверяет: есть ли завершенные jobs?
├─ Если job.status == "completed"
├─ Читает результаты
├─ Форматирует для пользователя
└─ Отправляет пользователю

Вариант Б: WEBHOOK (результат push'ится в бот)
├─ WORKER завершает job
├─ WORKER отправляет HTTP запрос в БОТ
├─ БОТ получает результат через webhook
└─ Отправляет пользователю

Текущая реализация: Вариант А (периодический polling)
```

**Как работает результат:**

```python
# После завершения job, БОТ:

1. Находит user_id и chat_id из job
2. Читает result из БД
3. Парсит transcript и segments
4. Форматирует текст (если нужно)
5. Генерирует краткое содержание (summary)
6. Сохраняет файлы транскрипции в ./transcriptions/
7. Создает inline keyboard с кнопками
8. Отправляет пользователю:
   ✅ Текст транскрибации
   📝 Краткое содержание
   🎯 Кнопки (Скачать, Вопросы, Меню)
9. Очищает временные файлы
```

---

## 🗄️ База Данных - Ключевые Таблицы

### **ProcessingJob (Главная таблица очередей)**

```sql
id              INTEGER PRIMARY KEY
user_id         BIGINT (Telegram user ID)
status          VARCHAR ('pending', 'processing', 'completed', 'failed', 'pending_format')
job_type        VARCHAR ('transcribe_deepinfra', 'format_transcript', etc)
media_path      TEXT (Путь к файлу)
result          JSON (Результаты обработки)
error           TEXT (Сообщение об ошибке если failed)
created_at      TIMESTAMP
updated_at      TIMESTAMP
acquired_by     VARCHAR (ID worker'а который это обрабатывает)
```

### **User (Информация пользователя)**

```sql
id              BIGINT PRIMARY KEY (Telegram user ID)
username        VARCHAR
first_name      VARCHAR
last_name       VARCHAR
plan            VARCHAR ('free', 'pro', 'unlimited')
monthly_quota   INTEGER (сколько видео в месяц)
monthly_usage   INTEGER (сколько уже использовал)
created_at      TIMESTAMP
```

### **Transcription (История транскрибаций)**

```sql
id              INTEGER PRIMARY KEY
user_id         BIGINT
filename        VARCHAR
raw_transcript  TEXT
formatted_transcript TEXT
processing_time FLOAT
transcription_service VARCHAR ('deepinfra', 'openai')
created_at      TIMESTAMP
```

---

## 🔀 Фильтрация и Маршрутизация Сообщений

### **Как БОТ Определяет Тип Сообщения**

```python
# В: transkribator_modules/main.py (основной бот loop)

# Регистрируем обработчики в порядке приоритета:

# 1. Специальный фильтр для МЕДИА (высший приоритет)
media_filters = (
    filters.PHOTO |
    filters.VOICE |
    filters.AUDIO |
    filters.VIDEO |
    filters.Document.ALL
)
application.add_handler(MessageHandler(media_filters, handle_message), group=0)

# 2. Обработчики команд (slash commands)
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("plans", plans_command))
application.add_handler(CommandHandler("wai", wai_menu_command))
# ... другие команды

# 3. Callback queries (нажатия на кнопки)
application.add_handler(CallbackQueryHandler(handle_callback_query))

# 4. Платежи
application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))

# 5. Все остальное (текст, стикеры, etc)
general_filters = (filters.ALL & ~filters.COMMAND) & ~media_filters
application.add_handler(MessageHandler(general_filters, handle_message))
```

**Порядок обработки:**
1. Если МЕДИА → handle_message()
2. Если КОМАНДА (/) → соответствующий CommandHandler
3. Если КНОПКА → handle_callback_query()
4. Если ПЛАТЕЖ → handle_successful_payment()
5. Если ТЕКСТ → handle_message()

---

## 📍 Где Запускается GPU Pipeline?

### **Текущее Место Обработки**

```
┌─────────────────────┐
│  БОТ (Telegram)     │  ← Здесь мы УЖЕ создали хендлеры_gpu!
│  handle_message()   │
└─────────────────────┘
          │
          ├─ Видео → process_video_file() ← ТЕКУЩАЯ ОБРАБОТКА
          │           (скачиваем, создаем job в БД)
          │
          ├─ Аудио → process_audio_file() ← ТЕКУЩАЯ ОБРАБОТКА
          │           (скачиваем, создаем job в БД)
          │
          └─ GPU транск? → [НОВОЕ]
              (мы должны добавить хендлер сюда)
```

### **Как Интегрировать GPU?**

**Вариант 1: ПРЯМО В БОТ (синхронно)**
```python
if update.message.video:
    # Скачиваем файл
    audio_path = await download_and_extract_audio()
    
    # ПРЯМО ВЫЗЫВАЕМ GPU PIPELINE
    result = WhisperPipeline().process(audio_path)
    
    # Отправляем результат пользователю
    await send_result_to_user(result)
```

**Проблема:** БОТ будет заморожен на 57 секунд! Пользователь не сможет отправить еще файл.

**Вариант 2: ЧЕРЕЗ WORKER (рекомендуется)**
```python
if update.message.video:
    # Скачиваем файл
    audio_path = await download_and_extract_audio()
    
    # Создаем job тип "transcribe_gpu"
    job = ProcessingJob(
        user_id=user_id,
        job_type="transcribe_gpu",  ← НОВЫЙ ТИП!
        media_path=audio_path,
        status="pending"
    )
    
    # WORKER'ы обработают в фоне
    # БОТ остается свободен!
```

**Потом в WORKER:**
```python
def handle_transcribe_gpu(job):
    audio_path = job.media_path
    result = WhisperPipeline().process(audio_path)
    job.result = result
    job.status = "completed"
```

---

## ✅ Контрольный Список Компонентов

| Компонент | Контейнер | Роль | Порт |
|-----------|-----------|------|------|
| Telegram Bot API | `telegram-bot-api` | Протокол Telegram | 9081 |
| БОТ (Логика) | `transkribator-bot` | Получает сообщения, создает jobs | Polling |
| WORKER | `transkribator-worker` | Обрабатывает jobs, вызывает APIs | - |
| API (REST) | `transkribator-api` | REST endpoints для внешних сервисов | 9000 |
| Postgres DB | `postgres` | Хранилище jobs, пользователей, результатов | 5432 |

---

## 🎯 Выводы

1. **БОТ - это просто роутер:**
   - Получает обновление от Telegram
   - Определяет тип (медиа, команда, текст)
   - Создает background task или job
   - Отправляет "обрабатываю..." пользователю
   - НЕ ждет результатов!

2. **WORKER - это мозг обработки:**
   - Берет jobs из БД
   - Вызывает внешние APIs (DeepInfra, OpenAI, OpenRouter)
   - Может порождать новые jobs (job chaining)
   - Сохраняет результаты

3. **Дублирования нет:**
   - БОТ не обрабатывает медиа
   - WORKER не общается с Telegram
   - API - это просто REST wrapper для БД
   - Каждый контейнер имеет четкую роль

4. **Для GPU интеграции:**
   - Добавить новый тип job: `transcribe_gpu`
   - Добавить обработчик в WORKER: `handle_transcribe_gpu()`
   - Или вызывать GPU прямо в БОТ (если очень быстро)
   - БД подтвердит когда готово

