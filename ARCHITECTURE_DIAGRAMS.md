# 🗺️ Визуальная Архитектура - Диаграммы

## 1️⃣ Полный Пайплайн Обработки

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            TELEGRAM USER                                    │
│                        (Sends video file)                                   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│            TELEGRAM BOT API SERVER (cyberkitty19-telegram-bot-api)          │
│                          Port: 9081                                         │
│                     • Telegram Protocol Handler                             │
│                     • File Download Manager                                 │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                        ┌──────────┴──────────┐
                        │   HTTP Polling      │
                        ▼                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    BOT CONTAINER (cyberkitty19-transkribator-bot)            │
│                                                                               │
│  handle_message() Router:                                                   │
│  ├─ Video?    → process_video_file()    (async background task)            │
│  ├─ Audio?    → process_audio_file()    (async background task)            │
│  ├─ Voice?    → process_audio_file()    (async background task)            │
│  ├─ Document? → detect_format() → process_xxx_file()                       │
│  ├─ YouTube?  → download() → process_video_file()                          │
│  ├─ Command?  → Command Handler (別プロセス)                               │
│  ├─ Button?   → Callback Handler (別プロセス)                              │
│  └─ Text?     → QA or Menu handler                                          │
│                                                                               │
│  After each file handler:                                                   │
│  1. Download from Telegram                                                  │
│  2. Extract audio (FFmpeg)                                                  │
│  3. Create ProcessingJob in DB                                              │
│  4. Set job_type = "transcribe_deepinfra" OR "transcribe_gpu"              │
│  5. Return immediately (async!)                                             │
│  6. Send "⏳ Processing..." to user                                         │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
                          │ Creates jobs
                          │ (DB INSERT)
                          ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│              PostgreSQL Database (cyberkitty19-postgres)                      │
│                    Port: 5432                                                │
│                                                                               │
│  ProcessingJob Table:                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ ID │ USER_ID │ JOB_TYPE             │ STATUS    │ RESULT │ MEDIA_PATH  │
│  ├────┼─────────┼──────────────────────┼───────────┼────────┼──────────────┤
│  │ 1  │ 123456  │ transcribe_deepinfra │ pending   │ NULL   │ /path/to/mp3 │
│  │ 2  │ 789012  │ transcribe_gpu       │ processing│ NULL   │ /path/to/mp3 │
│  │ 3  │ 345678  │ format_transcript    │ pending   │ NULL   │ NULL         │
│  │ 4  │ 123456  │ transcribe_deepinfra │ completed │ {...}  │ /path/to/mp3 │
│  └──────────────────────────────────────────────────────────────────┘      │
│                                                                               │
│  User Table:                                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │ ID     │ USERNAME  │ PLAN   │ MONTHLY_QUOTA │ GPU_ENABLED      │      │
│  ├────────┼───────────┼────────┼───────────────┼──────────────────┤      │
│  │ 123456 │ john_doe  │ pro    │ unlimited     │ true             │      │
│  │ 789012 │ jane_smith│ free   │ 3             │ false            │      │
│  └──────────────────────────────────────────────────────────────────┘      │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │   Polling every 5s    │
              ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│             WORKER CONTAINER (cyberkitty19-transkribator-worker)             │
│                                                                               │
│  Main Loop (job_worker.py):                                                 │
│  while True:                                                                │
│    1. SELECT * FROM jobs WHERE status='pending' LIMIT 1                    │
│    2. UPDATE job SET acquired_by='worker-1', status='processing'           │
│    3. Call dispatch_job(job)                                                │
│                                                                               │
│  dispatch_job() Router:                                                     │
│  ├─ job_type == "transcribe_deepinfra"  → handle_transcribe_deepinfra()    │
│  │  └─ Call DeepInfra API                                                   │
│  │  └─ Get transcript + segments                                            │
│  │  └─ Save to job.result                                                   │
│  │  └─ If needs format: create job_type='format_transcript'                │
│  │                                                                            │
│  ├─ job_type == "transcribe_gpu"        → handle_transcribe_gpu()          │
│  │  └─ Call WhisperPipeline.process()                                      │
│  │  └─ GPU processing (48s for 21min audio)                                │
│  │  └─ Save to job.result                                                   │
│  │  └─ If needs format: create job_type='format_transcript'                │
│  │                                                                            │
│  ├─ job_type == "format_transcript"     → handle_format_transcript()       │
│  │  └─ Parse transcript from payload                                        │
│  │  └─ Call LLM for formatting (OpenAI/OpenRouter)                         │
│  │  └─ Save formatted text                                                  │
│  │                                                                            │
│  └─ job_type == other_type              → ... other handlers               │
│                                                                               │
│  After processing:                                                          │
│  UPDATE job SET status='completed', result={...}                           │
│  OR                                                                          │
│  UPDATE job SET status='failed', error='{error message}'                   │
└─────────────────────────┬──────────────────────────────────────────────────┘
                          │
                          │ Updates jobs
                          │ (DB UPDATE)
                          ▼
                    PostgreSQL DB
                    (Job result saved)
                          │
                          │
              ┌───────────┴───────────┐
              │   Polling every 5s    │
              ▼                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│              BOT CONTAINER (again) - Result Delivery                          │
│                                                                               │
│  Background Polling Loop:                                                    │
│  1. SELECT * FROM jobs WHERE status='completed' AND user_id=? LIMIT 1       │
│  2. Read job.result                                                          │
│  3. Parse transcript, segments, summary                                      │
│  4. Format response with buttons                                             │
│  5. Send to Telegram user                                                    │
│  6. Update job.status='delivered'                                            │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
                           │ Send via Telegram API
                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│              TELEGRAM BOT API SERVER (again)                                  │
│                                                                               │
│  Forward message to Telegram                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
                           │
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      TELEGRAM USER                                            │
│              ✅ Receives transcription result!                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2️⃣ Job States и Transitions

```
                    ┌──────────────────┐
                    │    START         │
                    │  (User sends file)
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │    PENDING       │
                    │  (In queue)      │
                    │  (Waiting for    │
                    │   worker pickup) │
                    └────────┬─────────┘
                             │
                    ┌────────▼──────────┐
                    │   PROCESSING      │
                    │ (Worker acquired) │
                    │ (Running handler) │
                    └────────┬─────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
                ▼            ▼            ▼
         ┌─────────┐  ┌──────────────┐ ┌─────────┐
         │ SUCCESS │  │ NEEDS FORMAT │ │ FAILED  │
         │         │  │              │ │ (Error) │
         └────┬────┘  └────┬─────────┘ └─────────┘
              │             │
              │      ┌──────▼───────┐
              │      │ PENDING_     │
              │      │ FORMAT       │
              │      │ (Waiting for │
              │      │ format job)  │
              │      └──────┬───────┘
              │             │
              │      ┌──────▼──────────┐
              │      │  PROCESSING     │
              │      │  (Formatting)   │
              │      └──────┬──────────┘
              │             │
              └─────┬───────┘
                    │
            ┌───────▼────────┐
            │  COMPLETED     │
            │ (Result ready) │
            └───────┬────────┘
                    │
            ┌───────▼────────────┐
            │    DELIVERED       │
            │ (Sent to user)     │
            └────────────────────┘
```

---

## 3️⃣ Message Router Logic

```
                    Telegram Update
                         │
                         ▼
            ┌─────────────────────────┐
            │   Update.message?       │ NO → Skip
            │ Update.effective_chat?  │ ──────┐
            │ Update.effective_user?  │       │
            └───────┬─────────────────┘       │
                    │ YES                     │
                    ▼                         │
            ┌─────────────────────────┐       │
            │  Is it MEDIA?           │ ──┐  │
            │  (video/audio/voice/    │   │  │
            │   document/photo)       │   │  │
            └─────────────────────────┘   │  │
                    │ YES             NO  │  │
                    │                 │   │  │
        ┌───────────┴──────────────┐  │   │  │
        │                          │  │   │  │
        ▼                          ▼  │   │  │
    ┌─────────┐             ┌──────────────────┐
    │  GROUP  │ YES → Skip  │  Is COMMAND?     │ ──┐
    │  CHAT?  │             │  (starts with /)│   │
    │         │             │                  │   │
    └─────────┘             └──────────────────┘   │
        │                       │ YES           NO │
        │ NO                    │                  │
        │                       ▼                  │
        │                   ┌──────────┐           │
        │                   │COMMAND   │           │
        │                   │HANDLER   │           │
        │                   │(別process)           │
        │                   └──────────┘           │
        │                                          │
        ▼                                          ▼
    ┌─────────────────────┐        ┌──────────────────────┐
    │ process_video_file()│        │  Is CALLBACK?        │
    │ process_audio_file()│        │  (Button press)      │
    │ process_voice_msg() │        │                      │
    │ etc...              │        └──────────────────────┘
    │                     │                 │ YES
    │ Background Task:    │                 ▼
    │ 1. Download file    │            ┌──────────────┐
    │ 2. Extract audio    │            │ CALLBACK     │
    │ 3. Create job       │            │ HANDLER      │
    │ 4. Return immed.    │            │ (別process)  │
    │                     │            └──────────────┘
    └─────────────────────┘
         │
         ▼
    Send "⏳ Processing..."
```

---

## 4️⃣ Контейнеры и Их Ответственность

```
┌──────────────────────────────────────────────────────────────────┐
│                TELEGRAM BOT API SERVER                           │
├──────────────────────────────────────────────────────────────────┤
│ Ответственность:                                                 │
│ • Реализует Telegram Bot API протокол                            │
│ • Получает updates из сети Telegram                              │
│ • Отправляет сообщения обратно                                  │
│ • Управляет скачиванием файлов                                  │
│                                                                   │
│ НЕ ответственен за:                                             │
│ • Обработку медиа                                               │
│ • Логику бизнеса                                                │
│ • Хранение данных                                               │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                BOT CONTAINER                                     │
├──────────────────────────────────────────────────────────────────┤
│ Ответственность:                                                 │
│ • Получать updates из Telegram Bot API                          │
│ • Маршрутизировать сообщения (определить тип)                 │
│ • Запускать асинхронные задачи                                  │
│ • Скачивать файлы из Telegram                                   │
│ • Подготавливать файлы (FFmpeg)                                │
│ • Создавать jobs в БД                                           │
│ • Отправлять результаты пользователю                            │
│ • Управлять UI (кнопки, меню)                                   │
│                                                                   │
│ НЕ ответственен за:                                             │
│ • Тяжелую обработку медиа (видео/аудио кодирование)            │
│ • Вызовы внешних APIs (DeepInfra, OpenAI)                       │
│ • Форматирование результатов через LLM                          │
│ • Длительные операции (> 5-10 сек)                             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                WORKER CONTAINER                                  │
├──────────────────────────────────────────────────────────────────┤
│ Ответственность:                                                 │
│ • Опрашивать БД на наличие новых jobs                           │
│ • Обработка jobs:                                               │
│   - Вызывать внешние APIs                                       │
│   - Запускать GPU обработку                                     │
│   - Форматировать результаты                                    │
│   - Обрабатывать ошибки                                         │
│ • Сохранять результаты в БД                                     │
│                                                                   │
│ НЕ ответственен за:                                             │
│ • Общение с пользователем                                       │
│ • Управление Telegram API                                       │
│ • Маршрутизацию сообщений                                       │
│ • UI                                                             │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                API CONTAINER                                     │
├──────────────────────────────────────────────────────────────────┤
│ Ответственность:                                                 │
│ • Предоставлять REST endpoints                                  │
│ • Отвечать на запросы от внешних сервисов                       │
│ • Читать/писать данные в БД                                     │
│                                                                   │
│ НЕ ответственен за:                                             │
│ • Обработку медиа                                               │
│ • Получение updates                                             │
│ • Отправку сообщений                                            │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                PostgreSQL DATABASE                               │
├──────────────────────────────────────────────────────────────────┤
│ Ответственность:                                                 │
│ • Хранить jobs и их статусы                                     │
│ • Хранить пользователей и их параметры                          │
│ • Хранить результаты обработки                                  │
│ • Обеспечивать консистентность данных                           │
│ • Предоставлять querying interface                              │
│                                                                   │
│ НЕ ответственен за:                                             │
│ • Хранение медиа-файлов (на диске)                             │
│ • Кэширование                                                    │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5️⃣ GPU Integration Points

```
Вариант А: Через Job Queue (РЕКОМЕНДУЕТСЯ)

┌─────────────────────────────────────────┐
│ БОТ: handle_message()                  │
│                                         │
│ if user.gpu_enabled:                   │
│   job_type = "transcribe_gpu"    ◄──── НОВОЕ
│ else:                                  │
│   job_type = "transcribe_deepinfra"   │
│                                         │
│ job = ProcessingJob(job_type=...) ────┐
│ db.add(job)                           │
│ db.commit()                           │
└─────────────────────────────────────────┘
                │
                ▼
        PostgreSQL DB
        (job.status='pending')
                │
                ▼
┌─────────────────────────────────────────┐
│ WORKER: dispatch_job()                  │
│                                         │
│ if job.job_type == "transcribe_gpu":   │
│   handle_transcribe_gpu(job) ◄────НОВОЕ│
│ elif job.job_type == "transcribe_deepinfra":
│   handle_transcribe_deepinfra(job)    │
│                                         │
│ def handle_transcribe_gpu(job):        │
│   result = WhisperPipeline()          │
│           .process(job.media_path)    │
│   job.result = result                 │
│   job.status = 'completed'            │
│   db.commit()                         │
└─────────────────────────────────────────┘
                │
                ▼
        PostgreSQL DB
        (job.status='completed')
                │
                ▼
┌─────────────────────────────────────────┐
│ БОТ: Polling                            │
│                                         │
│ SELECT * FROM jobs                    │
│ WHERE status='completed'              │
│                                         │
│ Format result                         │
│ Send to user                          │
│ ✅ READY!                              │
└─────────────────────────────────────────┘
```

---

## ✅ Ключевые Выводы

1. **Разделение ответственности четкое** - нет дублирования
2. **Job Queue архитектура** позволяет масштабировать
3. **БОТ остается свободным** - не ждет обработки
4. **WORKER может быть множественным** - несколько workers обрабатывают параллельно
5. **GPU integrация простая** - просто новый job type

