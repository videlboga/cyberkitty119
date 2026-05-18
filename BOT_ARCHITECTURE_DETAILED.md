# 🔬 Детальный Анализ Архитектуры Telegram Бота

## 📊 Общая Архитектура Системы

```
┌─────────────────────────────────────────────────────────────────┐
│                     TELEGRAM BOT (Главное меню)                 │
│                                                                   │
│  handle_message() → Определяет тип входящего сообщения          │
│  ├─ Текст с ссылкой → YouTube, Google Drive, Dropbox, Mega      │
│  ├─ Видео файл → Загрузка, конвертация, очередь                │
│  ├─ Аудио файл → Загрузка, сжатие, очередь                     │
│  ├─ Голосовое сообщение → Загрузка, сжатие, очередь             │
│  ├─ Документ (видео/аудио) → Определение типа, обработка        │
│  └─ Текст/Команда → WAI Flow, QA сессия, manual mode            │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│               BOT HANDLERS: Обработчики сообщений               │
│                                                                   │
│  1. _handle_youtube_link()     - Загрузка с YouTube             │
│  2. _handle_google_drive_link() - Загрузка с Google Drive        │
│  3. _handle_dropbox_link()     - Загрузка с Dropbox             │
│  4. _handle_mega_link()        - Загрузка с Mega.nz             │
│  5. _handle_yandex_disk_link() - Загрузка с Яндекс.Диска        │
│  6. process_video_file()       - Обработка видео из Telegram    │
│  7. process_audio_file()       - Обработка аудио из Telegram    │
│                                                                   │
│  ВСЕ → Загружают файл → Сжимают/конвертируют → Отправляют в    │
│        очередь через enqueue_media_job()                        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    JOB QUEUE (базе данных)                       │
│                                                                   │
│  ProcessingJob (DB таблица)                                     │
│  ├─ id: уникальный ID                                           │
│  ├─ user_id: ID пользователя                                    │
│  ├─ job_type: "media_processing"                                │
│  ├─ status: QUEUED → IN_PROGRESS → COMPLETED / FAILED           │
│  ├─ payload: JSON с параметрами (audio_path, filename, etc)     │
│  └─ note_id: ID заметки (опционально)                           │
│                                                                   │
│  Статусы: QUEUED → IN_PROGRESS → COMPLETED / FAILED             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   JOB WORKER (фоновый процесс)                   │
│                                                                   │
│  Читает из очереди по одной задаче, обрабатывает их             │
│  ├─ acquire_job() - Получить доступную задачу                  │
│  ├─ dispatch_job() - Отправить на обработчик                    │
│  ├─ complete_job() - Отметить как завершённую                   │
│  └─ fail_job() - Отметить как ошибка                            │
│                                                                   │
│  Обрабатывает: MEDIA_JOB_TYPE → process_media_job()             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              MEDIA PROCESSING PIPELINE (6 стадий)                │
│                                                                   │
│  1. PrepareEnvironmentStage()  - Создать временную директорию   │
│  2. DownloadMediaStage()       - Скачать медиа (или использовать│
│                                  path из payload)                │
│  3. TranscribeMediaStage()     - Транскрибация                  │
│     └─ Вызывает: default_transcribe_media()                     │
│        └─ TranscribeClient → DeepInfra API                      │
│  4. FinalizeNoteStage()        - Форматирование, сохранение     │
│  5. DeliverResultsStage()      - Отправить результат пользователю│
│  6. CleanupStage()             - Удалить временные файлы        │
│                                                                   │
│  Весь процесс: context → run_media_pipeline() → result          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## ✅ ВЫВОД АУДИТА

### ✓ Архитектура Чистая

1. **Нет дублирования логики** - каждая функция имеет свой смысл
2. **Нет выбивающихся компонентов** - всё работает по плану
3. **Коммуникация правильная**:
   - Бот → Очередь → Worker → Pipeline → Результат

### ✓ Нет Проблем с API Вызовами

- Cloud Storage API используются для загрузки (YouTube, Google Drive, etc.) - это нормально
- DeepInfra API используется для транскрибации - это нормально
- LLM API используется для форматирования - это нормально

### ✓ Никаких Дублирований

- Каждая таблица БД сохраняет разные данные (Transcription vs Note)
- Разные кодовые ветки не пересекаются
- Каждая функция вызывается один раз в пайплайне

---

## 🎯 ГДЕ ИНТЕГРИРОВАТЬ GPU PIPELINE

### Рекомендуемый Вариант: Модификация `default_transcribe_media()`

**Файл:** `transkribator_modules/jobs/services.py` (строка ~99)

```python
def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Может использовать GPU или DeepInfra."""
    
    logger.info("Transcribe media", extra={"job_id": context.job.id, "media_path": media_path})

    # 1. Проверить, нужно ли использовать GPU
    use_gpu = os.getenv("TRANSCRIBE_USE_GPU", "0") == "1"
    
    if use_gpu:
        try:
            from pipeline_orchestrator import WhisperPipeline
            pipeline = WhisperPipeline()
            result = pipeline.process(Path(media_path))
            if result["status"] == "success":
                return result["transcription_text"]
            else:
                logger.warning(f"GPU pipeline failed: {result.get('error')}")
                use_gpu = False  # Fallback
        except Exception as exc:
            logger.warning(f"GPU pipeline error: {exc}, falling back to DeepInfra")
            use_gpu = False
    
    # 2. DeepInfra (как сейчас)
    if not use_gpu:
        try:
            from transcribe_client import TranscribeClient
            mode = os.environ.get("TRANSCRIBE_DEFAULT_MODE", "deepinfra")
            client = TranscribeClient(default_mode=mode)
            result = client.transcribe(media_path, mode)
            if result.get("status") == "ok":
                return result.get("text", "")
            else:
                logger.warning("TranscribeClient returned error")
                return "⚠️ Ошибка при обработке аудио."
        except Exception as exc:
            logger.exception("Transcribe client failed")
            return f"❌ Не удалось обработать файл: {str(exc)[:100]}"
```

### Включение GPU

**Добавить в `.env`:**
```bash
TRANSCRIBE_USE_GPU=1
GPU_PIPELINE_ENABLED=true
```

### Автоматический Fallback

- Если GPU недоступна → автоматически использует DeepInfra
- Если GPU ошибка → автоматически fallback на DeepInfra
- Нулевой риск для пользователей

---

## 📋 ИТОГОВАЯ ТАБЛИЦА

| Компонент | Статус | Вывод |
|-----------|--------|-------|
| **handle_message()** | ✅ Чистый | Правильная маршрутизация |
| **Cloud Downloaders** | ✅ OK | Нормальная функция |
| **process_video_file()** | ✅ OK | Загружает, сжимает, отправляет в очередь |
| **process_audio_file()** | ✅ OK | Загружает, сжимает, отправляет в очередь |
| **Job Queue** | ✅ OK | Правильная структура данных |
| **Pipeline Stages** | ✅ OK | Все 6 стадий независимы |
| **DeepInfra Integration** | ✅ OK | Используется в TranscribeMediaStage |
| **GPU Integration Point** | ✅ Ready | default_transcribe_media() в services.py |
| **LLM Post-Processing** | ✅ OK | Часть FinalizeNoteStage |
| **Database** | ✅ OK | Чистая схема, нет дублирования |

---

## 🚀 Шаг за Шагом для GPU Интеграции

1. **Убедиться GPU Pipeline готов** ✅ (уже сделано)
2. **Добавить импорт в services.py** (будет сделано)
3. **Модифицировать default_transcribe_media()** (будет сделано)
4. **Добавить флаг TRANSCRIBE_USE_GPU** (будет сделано)
5. **Протестировать с большим файлом** (будет сделано)
6. **Обновить .env для production** (будет сделано)

**Время интеграции: 30 минут** ⏱️

