# 🔄 Диаграмма Потока Данных Бота

## Высокоуровневая Архитектура

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM CLOUD                                   │
│                        (telegram.org)                                   │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                    ◄──── UPDATES (видео, текст)
                    
┌──────────────────────────────────────────────────────────────────────────┐
│  DOCKER CONTAINER: cyberkitty19-transkribator-bot                        │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ main.py                                                            │  │
│  │ ├─ ApplicationBuilder() - создание Telegram client                │  │
│  │ ├─ _acquire_singleton_lock() - только одна копия слушает        │  │
│  │ └─ application.run_polling() - слушаем апдейты                  │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                               │                                           │
│                               ▼                                           │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ handle_message() - main message handler (2269 строк!)            │  │
│  │                                                                    │  │
│  │ 🎬 VIDEO? ────┐                                                  │  │
│  │ 🎵 AUDIO? ────┼─► process_video_file() / process_audio_file()  │  │
│  │🎤 VOICE?  ────┤                                                  │  │
│  │ 📄 DOCUMENT?──┤   ├─ Download from Telegram (with progress bar) │  │
│  │ 🔗 LINK?  ────┤   ├─ Extract audio (FFmpeg for video)          │  │
│  │ 📝 TEXT?  ────┘   ├─ Compress audio                             │  │
│  │                   ├─ Check user quota                            │  │
│  │                   └─ Enqueue media job                           │  │
│  │                      (non-blocking!)                             │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                               │                                           │
│                               ▼                                           │
│                  enqueue_media_job(user_id, payload)                     │
│                               │                                           │
│                   ┌───────────┴────────────┐                             │
│                   │ Status Message to User │                             │
│                   │ "Файл принят!"        │                             │
│                   └───────────┬────────────┘                             │
│                               │                                           │
│                ──────────────►RETURN◄──────────────                      │
│                   Бот готов к следующему сообщению                      │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               │
                      ┌────────▼────────┐
                      │   PostgreSQL    │
                      │  (Database)     │
                      └────────┬────────┘
                               │
                               │ ProcessingJob создана
                               │ status = PENDING
                               │
┌──────────────────────────────────────────────────────────────────────────┐
│  DOCKER CONTAINER: cyberkitty19-transkribator-worker                     │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ job_worker.py - слушает очередь в БД                              │  │
│  │                                                                    │  │
│  │ process_media_job(job) ◄── получает job из очереди              │  │
│  │                                                                    │  │
│  │ ┌─────────────────────────────────────────────────────────────┐  │  │
│  │ │ STAGE 1: Prepare Environment                                │  │  │
│  │ │ └─ mkdir media/incoming/, media/processing/, media/results/ │  │  │
│  │ └─────────────────────────────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │ ┌─────────────────────────▼────────────────────────────────────┐  │  │
│  │ │ STAGE 2: Download Media                                     │  │  │
│  │ │ └─ artifact['media_path'] = context.services.download()    │  │  │
│  │ │    (в нашем случае - просто ссылка на уже скачанный файл) │  │  │
│  │ └─────────────────────────┬────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │ ┌─────────────────────────▼────────────────────────────────────┐  │  │
│  │ │ STAGE 3: Transcribe Media                                   │  │  │
│  │ │ └─ context.services.transcribe()                            │  │  │
│  │ │    ├─ requests.post(DeepInfra API)                          │  │  │
│  │ │    │  или вызов GPU pipeline                                │  │  │
│  │ │    └─ artifact['transcript'] = text                         │  │  │
│  │ └─────────────────────────┬────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │ ┌─────────────────────────▼────────────────────────────────────┐  │  │
│  │ │ STAGE 4: Finalize Note                                      │  │  │
│  │ │ └─ context.services.finalize()                              │  │  │
│  │ │    ├─ Format transcript (LLM)                               │  │  │
│  │ │    ├─ Generate summary                                      │  │  │
│  │ │    ├─ Create Note in Note System                            │  │  │
│  │ │    └─ artifact['note'] = note                               │  │  │
│  │ └─────────────────────────┬────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │ ┌─────────────────────────▼────────────────────────────────────┐  │  │
│  │ │ STAGE 5: Deliver Results                                    │  │  │
│  │ │ └─ context.services.deliver()                               │  │  │
│  │ │    └─ Send message to Telegram:                             │  │  │
│  │ │       ├─ ✅ Обработка завершена!                             │  │  │
│  │ │       ├─ 📝 [Summary text]                                   │  │  │
│  │ │       └─ [Inline Keyboard]:                                 │  │  │
│  │ │          ├─ 📄 Скачать текст                                │  │  │
│  │ │          ├─ 🔎 Задать вопросы                               │  │  │
│  │ │          └─ 🏠 Главное меню                                 │  │  │
│  │ └─────────────────────────┬────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │ ┌─────────────────────────▼────────────────────────────────────┐  │  │
│  │ │ STAGE 6: Cleanup                                            │  │  │
│  │ │ └─ context.services.cleanup()                               │  │  │
│  │ │    ├─ rm audio/telegram_audio_*.wav                         │  │  │
│  │ │    ├─ rm video/telegram_video_*.mp4                         │  │  │
│  │ │    └─ Clear memory                                          │  │  │
│  │ └─────────────────────────┬────────────────────────────────────┘  │  │
│  │                            │                                       │  │
│  │                            ▼                                       │  │
│  │               RETURN (обработка завершена)                         │  │
│  │                                                                    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                               │                                           │
│                      ┌────────▼────────┐                                │
│                      │   PostgreSQL    │                                │
│                      │  job.status =   │                                │
│                      │  COMPLETED      │                                │
│                      └─────────────────┘                                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                               │
                               │
                      ┌────────▼────────┐
                      │   TELEGRAM API   │
                      │  (send message)  │
                      │    с текстом     │
                      └──────────────────┘
                               │
                               ▼
                   ┌──────────────────────────┐
                   │  TELEGRAM CLOUD          │
                   │  (пользователь получает │
                   │   результат)             │
                   └──────────────────────────┘
```

---

## Детальный Поток: Видео → Транскрипция

```
USER ────► TELEGRAM ────► BOT Container ────┐
  (отправляет          (polling updates)    │
   видео.mp4)                               │
                                            │
                                            ▼
                        ┌─────────────────────────────────────────────┐
                        │ handle_message()                            │
                        │ ├─ Check: is_video? YES                     │
                        │ ├─ log_telegram_event("message_video")     │
                        │ ├─ _prepare_new_media(context)              │
                        │ ├─ status_msg = "Готовлю обработку…"       │
                        │ └─ process_video_file()                     │
                        └─────────────────────────────────────────────┘
                                            │
                                            ▼
                        ┌─────────────────────────────────────────────┐
                        │ process_video_file()                        │
                        ├─ guard() ← Check: не обрабатывается?       │
                        ├─ file_size = 244 MB                         │
                        ├─ DOWNLOAD VIDEO:                            │
                        │  ├─ progress_callback каждые 1.5s          │
                        │  ├─ status: "🎬 Загружаю видео… 50%"       │
                        │  └─ saved to: videos/telegram_video_*.mp4  │
                        │                                             │
                        ├─ EXTRACT AUDIO:                             │
                        │  ├─ status: "🎵 Извлекаю аудио…"           │
                        │  ├─ FFmpeg: mp4 → wav                      │
                        │  └─ saved to: audio/telegram_audio_*.wav   │
                        │                                             │
                        ├─ COMPRESS AUDIO:                            │
                        │  ├─ status: "🗜️ Подготавливаю аудио…"     │
                        │  ├─ compress_audio_for_api()                │
                        │  └─ result: 6 MB (vs 244 MB video)          │
                        │                                             │
                        ├─ CHECK QUOTA:                               │
                        │  ├─ get_or_create_user()                    │
                        │  ├─ duration = 21.5 минут                   │
                        │  ├─ check_usage_limit() → OK (free: 3 video)│
                        │  └─ add_usage(user, 21.5)                   │
                        │                                             │
                        └─ ENQUEUE JOB:                               │
                           ├─ MediaJobPayload created                 │
                           ├─ enqueue_media_job()                     │
                           ├─ Database: INSERT INTO processing_jobs  │
                           ├─ status: "✅ Файл принят!"               │
                           └─ RETURN (非blocking!)                    │
                                            │
                                            ▼
                        BOT ready for next message!
                        
                                            │
                        ┌───────────────────┴───────────────────┐
                        │                                       │
                        ▼                                       ▼
    USER continues chatting              WORKER process picks up job
    (BOT ignores, busy with              (from queue)
     next user messages)
                                            │
                                            ▼
                        ┌─────────────────────────────────────────────┐
                        │ process_media_job() in Worker Container    │
                        │                                             │
                        │ STAGE 1: Prepare                            │
                        │ └─ mkdir /app/media/{incoming,processing}  │
                        │                                             │
                        │ STAGE 2: Download                           │
                        │ └─ media_path = /app/audio/telegram_*.wav  │
                        │                                             │
                        │ STAGE 3: Transcribe ◄── KEY STAGE          │
                        │ ├─ requests.post(DeepInfra API)            │
                        │ ├─ Headers: Authorization                  │
                        │ ├─ Payload: audio file (6 MB)              │
                        │ ├─ Response: JSON                          │
                        │ │  {                                       │
                        │ │    "output": [                           │
                        │ │      {                                   │
                        │ │        "text": "Возврат бракованного…"  │
                        │ │      }                                   │
                        │ │    ]                                     │
                        │ │  }                                       │
                        │ └─ transcript = extract text               │
                        │                                             │
                        │ STAGE 4: Finalize                           │
                        │ ├─ format_transcript(text)                  │
                        │ ├─ generate_summary(text) via LLM          │
                        │ ├─ Create Note in database                 │
                        │ └─ Save Transcription record               │
                        │                                             │
                        │ STAGE 5: Deliver                            │
                        │ ├─ Send to Telegram:                        │
                        │ │  "✅ Обработка завершена!"               │
                        │ │  [Summary text]                          │
                        │ │  [Inline Keyboard]                       │
                        │ └─ notifier.notify("Отправляю результат") │
                        │                                             │
                        │ STAGE 6: Cleanup                            │
                        │ ├─ rm /app/audio/telegram_audio_*.wav      │
                        │ ├─ rm /app/video/telegram_video_*.mp4      │
                        │ └─ Clear memory                             │
                        │                                             │
                        └─ Return to queue                            │
                                            │
                                            ▼
                        Database update:
                        processing_job.status = COMPLETED
                                            │
                                            ▼
    USER TELEGRAM ◄───── Message sent with results
    (получает
     результат!)
```

---

## Команды Бота

```
USER COMMANDS:
├─ /start ────────────► start_command() - приветствие, создание user
├─ /help ─────────────► help_command() - справка
├─ /plans ────────────► plans_command() - тарифные планы
├─ /transcribe_gpu ───► handle_gpu_transcription() - GPU (НОВАЯ!)
├─ /status ───────────► status_command() - статус обработки
├─ /manual ───────────► manual_menu_command() - manual transcribe
├─ /wai ──────────────► wai_menu_command() - WAI mode
├─ /buy ──────────────► show_payment_plans() - покупка подписки
└─ /promo ────────────► promo_codes_command() - применить промокод

CALLBACK BUTTONS:
├─ result:download_text ────► Download transcription
├─ result:ask ───────────────► Start Q&A session
├─ main:menu ────────────────► Return to main menu
└─ ... (платежи, планы, etc.)
```

---

## Ключевые Сервисы (Services)

```
MediaPipelineServices (abstraction layer):
├─ prepare(context) ─────── Создание директорий
├─ download(context) ────── Получение файла
├─ transcribe(context, path) ── DeepInfra API или GPU
├─ finalize(context, transcript) ── Сохранение в БД
├─ deliver(context) ────── Отправка пользователю
└─ cleanup(context) ────── Удаление временных файлов
```

Это позволяет легко подменять реализацию (например, вместо DeepInfra использовать GPU).

---

## 🎯 Точки для Интеграции GPU

```
┌─────────────────────────────────────────────────┐
│ TranscribeMediaStage                            │
│                                                 │
│ context.services.transcribe()                   │
│     │                                           │
│     ├─► Текущая реализация: DeepInfra API     │
│     │                                           │
│     └─► НОВАЯ реализация: GPU Pipeline        │
│         (pipeline_orchestrator.py)              │
│         (POST /api/v1/transcribe-gpu)          │
└─────────────────────────────────────────────────┘
```

Это основная точка, где нужно подменять логику!

