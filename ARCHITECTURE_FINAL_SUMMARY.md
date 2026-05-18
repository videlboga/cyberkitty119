# 📚 Полный Разбор Архитектуры - Финальная Сводка

## 🎯 Что Ты Теперь Знаешь

### **1. Архитектура контейнеров:**

```
🐳 Telegram Bot API Server (9081)
   ↓ updates
🐳 Telegram Bot Container
   ├─ Получает обновления
   ├─ Определяет тип (медиа/команда/текст)
   ├─ Создает background tasks и jobs
   └─ Отправляет результаты
   
🐳 PostgreSQL Database
   └─ Хранит jobs, users, результаты
   
🐳 Worker Container
   ├─ Опрашивает БД
   ├─ Обрабатывает jobs
   ├─ Вызывает external APIs
   └─ Сохраняет результаты
   
🐳 API Container (REST)
   └─ REST endpoints для внешних сервисов
```

### **2. Пайплайн обработки медиа:**

```
1. БОТ получает видео
   └─ handle_message() → process_video_file()
   
2. БОТ подготавливает:
   └─ Скачивает видео
   └─ Извлекает аудио FFmpeg
   └─ Создает job в БД
   └─ ЗАКАНЧИВАЕТ (асинхронно!)
   
3. WORKER обрабатывает:
   └─ Берет job из БД
   └─ Вызывает API (DeepInfra/OpenAI)
   └─ Сохраняет результат
   
4. БОТ доставляет результат:
   └─ Опрашивает БД (polling)
   └─ Форматирует результат
   └─ Отправляет пользователю
```

### **3. Job Queue система:**

```
Job имеет статусы:
├─ pending         → В ожидании обработки
├─ processing      → Сейчас обрабатывается
├─ completed       → Готово
├─ pending_format  → Готово к форматированию
└─ failed          → Ошибка

Job имеет типы:
├─ transcribe_deepinfra   → API DeepInfra
├─ transcribe_openai      → API OpenAI
├─ format_transcript      → LLM форматирование
└─ transcribe_gpu         → ← ЭТО ТЫ ДОБАВИШЬ!

Worker опрашивает каждые N секунд:
SELECT * FROM jobs WHERE status='pending' AND acquired_by IS NULL
```

### **4. Фильтрация сообщений:**

```
Telegram Update
    ↓
MessageHandler (group 0) → медиа?
    ├─ video      → handle_message()
    ├─ audio      → handle_message()
    ├─ voice      → handle_message()
    ├─ document   → handle_message()
    └─ photo      → handle_message()
    
CommandHandler (group 1) → команда?
    ├─ /start     → start_command()
    ├─ /help      → help_command()
    ├─ /plans     → plans_command()
    └─ ...
    
CallbackQueryHandler → кнопка?
    └─ handle_callback_query()
    
MessageHandler (group 2) → текст?
    └─ handle_message() снова (но уже для текста)
```

### **5. Где находятся файлы:**

```
./videos/          ← Скачанные видео
./audio/           ← Извлеченное аудио
./transcriptions/  ← Готовые транскрипции (тексты)
./data/            ← Прочие данные worker'а
./media/           ← ТУТ БУДЕТ GPU РЕЗУЛЬТАТЫ
  ├─ incoming/    ← Загруженные файлы для GPU
  ├─ processing/  ← Временные файлы
  └─ results/     ← Результаты GPU
```

### **6. Дублирования нет:**

```
БОТ делает:                WORKER делает:
├─ Получает обновления   └─ Обрабатывает медиа
├─ Скачивает файлы       └─ Вызывает APIs
├─ Создает jobs          └─ Форматирует результаты
├─ Отправляет юзеру      └─ Сохраняет в БД
└─ Управляет UI          └─ Обрабатывает ошибки

API делает:
└─ Предоставляет REST endpoints для данных
```

---

## 🚀 Как Интегрировать GPU

### **Вариант 1: Через Job Queue (Рекомендуется)**

```
Преимущества:
✅ Работает как все остальное
✅ Автоматический rate limiting (макс 5 параллельных)
✅ БОТ не блокируется
✅ Все логируется в БД
✅ Можно легко переключаться между GPU и DeepInfra

Что нужно:

1. Добавить обработчик в worker:
   def handle_transcribe_gpu(job):
       result = WhisperPipeline().process(job.media_path)
       job.result = result
       job.status = "completed"

2. Регистрировать:
   registry["transcribe_gpu"] = handle_transcribe_gpu

3. Изменить bot/handlers.py:
   if user.gpu_transcription_enabled:
       job_type = "transcribe_gpu"
   else:
       job_type = "transcribe_deepinfra"

4. Добавить команду /gpu для включения/отключения

Время реализации: 30-45 минут
```

### **Вариант 2: Отдельная команда (Быстрее)**

```
Преимущества:
✅ Работает параллельно
✅ Не нужно менять основную логику
❌ Пользователи должны знать команду
❌ Нет rate limiting

Что нужно:

1. Добавить /transcribe_gpu команду
2. В ней вызывать WhisperPipeline напрямую
3. Отправить результат пользователю

Время реализации: 15-20 минут
```

---

## 🎯 Ответы на Твои Вопросы

**В: Зачем вызовы API в боте?**
О: Их нет! БОТ только создает jobs в БД. WORKER вызывает APIs.

**В: Зачем команды?**
О: Команды это просто способ пользователя взаимодействовать с ботом.
   Когда ты добавляешь /gpu - это просто команда для включения GPU.
   Реальная обработка все равно идет через job queue в worker.

**В: Командам не нужны команды?**
О: Правильно! Команды это просто фронтенд (UI в Telegram).
   /start, /help, /plans - это просто кнопки.
   Реальная обработка медиа идет ВСЕГДА через job queue.

**В: Где находится логика обработки видео?**
О: В двух местах:
   1. БОТ (handle_message) - скачивает файл, создает job
   2. WORKER (handle_transcribe_xxx) - обрабатывает медиа

**В: Почему GPU в отдельном контейнере?**
О: Это и есть job! WORKER обрабатывает GPU jobs.
   Если в WORKER есть GPU, он обработает.
   Если нет - job будет ждать или упадет с ошибкой.

---

## 📊 Таблица Сравнения

| Стадия | Контейнер | Функция | Асинхронно? |
|--------|-----------|---------|-----------|
| Получение | Telegram Bot API | Отправляет update | - |
| Маршрутизация | Bot | handle_message() | Да (async) |
| Загрузка файла | Bot | download_from_telegram() | Да (async) |
| Подготовка | Bot | extract_audio() | Да (async) |
| **Создание Job** | Bot | INSERT into jobs | Да (async) |
| **Обработка** | Worker | handle_transcribe_xxx() | Да (background) |
| **Форматирование** | Worker | format_transcript() | Да (background) |
| Доставка | Bot | Polling + send_message() | Да (async) |

---

## 🔄 Жизненный Цикл Видео

```
15:00 - Пользователь отправляет видео в Telegram
        └─ Telegram Bot API отправляет update

15:00:01 - БОТ получает update
           └─ handle_message() → process_video_file()
           
15:00:02 - БОТ скачивает видео (2-5 минут для больших файлов)
           
15:05 - БОТ извлекает аудио FFmpeg (8-10 секунд)
        
15:05:10 - БОТ создает job в БД
           └─ status: pending
           └─ job_type: transcribe_gpu или transcribe_deepinfra
           
15:05:11 - БОТ отправляет юзеру "⏳ Обработка..."
           └─ БОТ ЗАКАНЧИВАЕТ!
           
15:05:12 - WORKER опрашивает БД
           └─ Находит новый job
           
15:05:13 - WORKER обрабатывает job
           └─ Если GPU: WhisperPipeline (48 секунд)
           └─ Если DeepInfra: API call (1-3 минуты)
           
15:06:10 - WORKER сохраняет результат в БД
           └─ status: completed
           └─ result: полный JSON
           
15:06:15 - БОТ опрашивает БД (polling каждые 5 сек)
           └─ Находит completed job
           
15:06:16 - БОТ форматирует результат
           
15:06:20 - БОТ отправляет транскрипцию пользователю
           ✅ ГОТОВО!

Время от загрузки до результата: ~76 секунд
```

---

## ✅ Финальный Чек-лист

### **Что ты ЗНАЕШЬ:**
- ✅ Как боты получают сообщения от Telegram
- ✅ Как сообщения маршрутизируются
- ✅ Как работает job queue
- ✅ Как worker обрабатывает jobs
- ✅ Как результаты доставляются пользователю
- ✅ Где находится GPU pipeline
- ✅ Как можно интегрировать GPU

### **Что уже СДЕЛАНО:**
- ✅ GPU орхестратор (pipeline_orchestrator.py)
- ✅ API эндпоинты (/api/v1/transcribe-gpu)
- ✅ Хендлер для команды /transcribe_gpu
- ✅ Документация (вся)

### **Что нужно СДЕЛАТЬ:**
- ⏳ Добавить handle_transcribe_gpu обработчик в worker
- ⏳ Добавить поле gpu_transcription_enabled в User model
- ⏳ Изменить handle_message() для выбора типа job
- ⏳ Добавить команду /gpu для включения/отключения
- ⏳ Протестировать

---

## 🎉 Итог

Теперь ты понимаешь ПОЛНУЮ архитектуру системы:

1. **БОТ** - это маршрутизатор (роутер)
   - Получает сообщения
   - Определяет тип
   - Создает jobs
   - Отправляет результаты

2. **WORKER** - это обработчик
   - Берет jobs
   - Обрабатывает медиа
   - Вызывает APIs
   - Сохраняет результаты

3. **DATABASE** - это очередь и хранилище
   - Jobs с их статусами
   - Пользователи и их настройки
   - Результаты обработки

4. **API** - это REST wrapper
   - Предоставляет endpoints
   - Для внешних сервисов

5. **GPU PIPELINE** - это просто новый job type
   - Вместо transcribe_deepinfra
   - Вместо transcribe_openai
   - Использует WhisperPipeline

**Нет дублирования, все чистенько!**

