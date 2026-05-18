# 📊 Анализ Соответствия Архитектуры GPU Требованиям

## Текущее Состояние Архитектуры

Вот детальный разбор того, как текущая система работает и на сколько она соответствует идеальным требованиям изоляции GPU.

---

## 1️⃣ Текущие Контейнеры и Их Роли

### **Контейнер 1: `cyberkitty19-transkribator-bot` (Telegram Bot)**
- **Язык**: Python (FastAPI + python-telegram-bot)
- **Роль**: Получает сообщения от пользователей, скачивает файлы, создает задачи
- **Логика обработки**:
  1. Пользователь отправляет видео/аудио
  2. Bot вызывает `transkribator_modules/bot/handlers.py:handle_message()`
  3. Проверяет размер файла, скачивает в `/app/videos/` или `/app/audio/`
  4. Вызывает `enqueue_media_job()` → создает `ProcessingJob` в БД со статусом "queued"
  5. Отправляет пользователю "обработка началась"
- **НЕ делает**: Не обрабатывает видео, не вызывает Whisper, не знает про GPU

### **Контейнер 2: `cyberkitty19-transkribator-worker` (Job Worker)**
- **Язык**: Python
- **Роль**: Асинхронно обрабатывает задачи из БД
- **Логика**:
  1. Запускается с параметрами (`--worker-id`, `--poll-interval`)
  2. Бесконечный loop в `job_worker.py:JobWorker.start()`:
     - `acquire_job()` → берет первую задачу со статусом "queued" из БД
     - Вызывает `dispatch_job(job)` → ищет handler в registry
     - Для `job.job_type == "media_processing"` → вызывает `process_media_job()`
  3. `process_media_job()` → запускает `run_media_pipeline(context)` (воркер, не bot!)
- **Stages Pipeline**:
  ```
  1. PrepareEnvironment      → создает tmpdir workspace
  2. DownloadMedia           → скачивает файл (уже скачан, используется pre-downloaded path)
  3. TranscribeMedia         → ЗДЕСЬ ВЫЗЫВАЕТСЯ TranscribeClient!!!
  4. FinalizeNote            → создает Note в БД
  5. DeliverResults          → отправляет результат в Telegram
  6. Cleanup                 → удаляет tmpfiles
  ```

### **Контейнер 3: `cyberkitty19-transkribator-api` (FastAPI API)**
- **Роль**: HTTP endpoint доступа к системе
- **Используется**: Опционально для запроса статуса, создания задач
- **НЕ обрабатывает**: Видео, транскрибацию

### **Контейнер 4: `cyberkitty19-postgres` (PostgreSQL)**
- **Роль**: Хранилище состояния (ProcessingJob, User, Note, etc.)
- **Ключевая таблица**: `processing_job` с полями (id, job_type, payload, status, user_id)

### **Контейнер 5: `cyberkitty19-di-worker` (DeepInfra Worker)**
- **Роль**: Опционально, для API интеграции с DeepInfra
- **Статус**: Редко используется

---

## 2️⃣ Где Происходит Транскрибация и GPU

### **TranscribeClient** (в `services.py:default_transcribe_media()`)

```python
def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    # ...
    if use_client:
        from transcribe_client import TranscribeClient
        mode = os.environ.get("TRANSCRIBE_DEFAULT_MODE", "stub")
        client = TranscribeClient(default_mode=mode)
        result = client.transcribe(media_path, mode=mode)  # ← ЗДЕСЬ!
        # ...
```

**Критический момент**: `TranscribeClient` — это абстракция, которая может использовать разные backends:
- `"stub"` → placeholder text
- `"local"` → локальная Whisper модель (если установлена)
- `"deepinfra"` → API запрос к DeepInfra
- `"openai"` → OpenAI API

**Текущий режим**: Определяется переменной окружения `TRANSCRIBE_DEFAULT_MODE`

---

## 3️⃣ Текущее Соответствие Требованиям

### ✅ **ЧТО УЖЕ ПРАВИЛЬНО** (соответствует требованиям)

1. **Изоляция Bot от GPU**
   - ✅ Bot контейнер НЕ знает про GPU, Whisper, CUDA
   - ✅ Bot только создает job в очереди (DB), не вызывает API напрямую
   - ✅ Bot не имеет зависимостей на torch/whisper

2. **Queue-based система**
   - ✅ Используется PostgreSQL для очереди (таблица `processing_job`)
   - ✅ Worker слушает очередь через `acquire_job()` с полингом
   - ✅ Job имеет уникальный `job_id` и статус tracking

3. **Shared Storage**
   - ✅ Shared volumes: `/app/videos`, `/app/audio`, `/app/transcriptions`, `/app/data`
   - ✅ Файлы сохраняются на общем хранилище, доступны всем контейнерам

4. **Асинхронная обработка**
   - ✅ Worker работает асинхронно, независимо от Bot
   - ✅ Bot не ждет результата транскрибации (non-blocking)

5. **Pipeline-based обработка**
   - ✅ Используется стадийный подход (stages)
   - ✅ Каждая стадия изолирована и может быть заменена

### ❌ **ЧТО НЕ СООТВЕТСТВУЕТ требованиям**

1. **GPU работает в одном контейнере с остальной логикой**
   - ❌ `cyberkitty19-transkribator-worker` обрабатывает ВСЕ типы работ
   - ❌ Если запустить worker с GPU — он будет обрабатывать все job_type, не только GPU-задачи
   - ❌ Нет отдельного GPU-worker контейнера с CUDA
   - ❌ Нет изоляции GPU доступа (нет ограничения доступа только GPU-воркеру)

2. **TranscribeClient вызывается из обычного Worker'а**
   - ❌ Worker контейнер не имеет GPU (нет CUDA 12.1 образа)
   - ❌ TranscribeClient работает в режиме stub (заглушка)
   - ❌ Нет реального вызова локального Whisper на GPU

3. **Нет отдельного GPU Worker контейнера**
   - ❌ Не существует `Dockerfile.gpu-worker` с CUDA поддержкой
   - ❌ Нет отдельного контейнера для `whisper_gpu_worker.py` (или аналога)

4. **Нет динамической маршрутизации по типам задач**
   - ❌ Worker получает `JOB_TYPES` env переменную, но это statically настроенный список
   - ❌ Нет механизма "если job_type=transcribe_gpu, отправить на GPU worker"
   - ❌ Используется простой полинг, не pub/sub (нет Redis/RabbitMQ)

5. **Нет ограничения параллелизма для GPU**
   - ❌ Нет семафора или max_concurrency на GPU-задачи
   - ❌ Нет мониторинга памяти GPU в runtime

6. **Нет разделения предварительной обработки**
   - ⚠️ Все stages выполняются в одном контексте (DownloadMedia + Transcribe + Finalize + Deliver)
   - ⚠️ Ideally: Prep в отдельном контейнере (FFmpeg), Transcribe в GPU контейнере

---

## 4️⃣ Как Должна Быть Архитектура

### **Идеальная Топология** (как вы описали)

```
┌─────────────────────────────────────────────────────────────────┐
│ Telegram Bot (cyberkitty19-transkribator-bot)                   │
├─────────────────────────────────────────────────────────────────┤
│ - Получает файл от пользователя                                 │
│ - Сохраняет в Shared Storage (media/incoming/)                  │
│ - Публикует job в очередь: {job_id, input_path, user_id}       │
│ → очередь "jobs.preparation"                                    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Preparation Worker (NEW: prep-worker)                           │
├─────────────────────────────────────────────────────────────────┤
│ - Слушает очередь "jobs.preparation"                            │
│ - FFmpeg: сжимает аудио, готовит к Whisper                     │
│ - Сохраняет в Shared Storage (media/processing/)               │
│ - Обновляет job: prepared_path, status="ready_for_gpu"         │
│ → очередь "jobs.gpu_transcription"                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ GPU Whisper Worker (NEW: gpu-worker, с CUDA 12.1)               │
├─────────────────────────────────────────────────────────────────┤
│ - Слушает очередь "jobs.gpu_transcription"                      │
│ - Загружает модель Whisper на GPU (один раз, persistent)       │
│ - Читает prepared_path из Shared Storage                        │
│ - Выполняет транскрибацию на GPU                                │
│ - Сохраняет result.json в Shared Storage (media/results/)      │
│ - Обновляет job: result_path, status="succeeded" | "failed"    │
│ → очередь "jobs.finalization" или webhook                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Finalization Worker (optional, существующий worker)             │
├─────────────────────────────────────────────────────────────────┤
│ - Слушает очередь "jobs.finalization"                           │
│ - Читает результаты из Shared Storage                           │
│ - Создает Note в БД                                             │
│ - Отправляет результат пользователю в Telegram                  │
│ - Очищает tmpfiles                                              │
└─────────────────────────────────────────────────────────────────┘
```

### **Key Differences от Текущей Архитектуры**

| Аспект | Текущее | Идеальное |
|--------|---------|-----------|
| **Транскрибация** | Worker контейнер (нет GPU) | Отдельный GPU-Worker контейнер |
| **Prep (FFmpeg)** | В Worker pipeline | Отдельный Prep-Worker контейнер |
| **Очередь** | PostgreSQL полинг | Redis/RabbitMQ pub/sub или DB-based |
| **GPU Concurrency** | Не ограничена | MAX_CONCURRENCY=5 с семафором |
| **Изоляция GPU** | Нет (Worker знает все) | Да (только GPU-Worker имеет CUDA) |
| **Масштабирование** | Сложно (добавить GPU worker) | Просто (scale GPU-Worker независимо) |

---

## 5️⃣ Текущая Реализация: Детали

### **Job Flow в Текущей Системе**

```python
# 1. Bot получает файл
handle_message()
  ├─ скачивает файл → /app/videos/message_123.mp4
  ├─ вызывает enqueue_media_job(
  │    user_id=user_id,
  │    payload=MediaJobPayload(file_id=..., extra={audio_path: ...})
  │  )
  ├─ создает ProcessingJob в DB (status="queued")
  └─ отправляет пользователю "обработка началась"

# 2. Worker слушает очередь
job_worker.py:JobWorker.start()
  ├─ acquire_job() → SELECT * FROM processing_job WHERE status='queued' LIMIT 1
  ├─ dispatch_job(job) → registry.dispatch(job)
  ├─ registry._handlers["media_processing"] → process_media_job()
  └─ process_media_job(job) → run_media_pipeline(context)

# 3. Pipeline выполняется в Worker'е
run_media_pipeline()
  ├─ Stage 1: PrepareEnvironment → создает tmpdir
  ├─ Stage 2: DownloadMedia → ищет pre-downloaded audio_path в extra
  ├─ Stage 3: TranscribeMedia → client.transcribe(media_path)
  │   (текущий режим: stub, не GPU!)
  ├─ Stage 4: FinalizeNote → создает Note в DB
  ├─ Stage 5: DeliverResults → отправляет в Telegram HTTP
  └─ Stage 6: Cleanup → удаляет tmpfiles

# 4. Telegram получает результат
User видит сообщение с результатом
```

### **Где Находится GPU?**

**Текущее состояние**: `pipeline_orchestrator.py` (который вы создали) — это STANDALONE скрипт, не интегрирован в worker pipeline!

```
❌ pipeline_orchestrator.py         ← работает standalone, не в pipeline
│
├─ WhisperPipeline class
│  ├─ prepare_audio() → FFmpeg
│  ├─ transcribe_audio() → Docker контейнер whisper-gpu
│  └─ generate_report()
│
└─ Нет связи с Job Worker или stages!
```

**Вывод**: Вы создали GPU pipeline, но он не интегрирован в существующий job-worker система!

---

## 6️⃣ Почему Другие Сервисы НЕ Должны Знать про GPU

### **Текущее Состояние: НЕ идеально**

В текущей системе:
- Bot скачивает файл → создает job
- Worker обрабатывает job → вызывает TranscribeClient (stub)
- Результаты хранятся в DB

**Проблема**: Если включить GPU в worker:
1. Worker контейнер должен иметь CUDA 12.1 (большой образ)
2. Это повредит масштабирование (нельзя просто добавить worker, нужны GPU)
3. Другие job_type (не транскрибация) будут конкурировать за GPU

### **Правильный Подход**

**Этап 1: Абстракция TranscribeClient**
- ✅ Уже сделано! TranscribeClient — это абстракция над разными backends
- Backends: stub, deepinfra, openai, local

**Этап 2: Добавить GPU Backend в TranscribeClient**
- Нужно: Создать `transcribe_client` backend для GPU
- Или: Создать отдельный GPU Worker, который слушает специальную очередь

**Правильно ли: Bot знает про GPU?**
- ❌ НЕТ. Bot только создает job, не думает о backend
- ✅ Правильно: Worker выбирает backend (stub vs deepinfra vs gpu) на основе конфига

**Правильно ли: Другие worker'ы знают про GPU?**
- ❌ НЕТ. GPU-специфичные job'ы обрабатываются GPU-worker'ом
- ✅ Правильно: Обычный worker обрабатывает обычные job'ы, GPU-worker обрабатывает GPU job'ы

---

## 7️⃣ Миграция: Пошаговый План к Идеальной Архитектуре

### **Фаза 1: Минимальная Интеграция (без рефакторинга)**

**Цель**: Использовать GPU pipeline внутри существующего worker

**Что делать**:
1. Создать новый `job_type = "media_gpu_transcription"`
2. Создать handler `process_media_gpu_job()` (похож на `process_media_job()`, но использует GPU)
3. Добавить stage `TranscribeMediaGPUStage` (вместо обычного `TranscribeMediaStage`)
4. В stage вызвать `pipeline_orchestrator.WhisperPipeline.process()`
5. Когда bot создает job, выбирать job_type based on file size:
   - Если > 50MB → `job_type = "media_gpu_transcription"`
   - Иначе → `job_type = "media_processing"` (DeepInfra)

**Плюсы**:
- Минимальный рефакторинг
- Работает с текущей DB системой
- Не нужны новые контейнеры

**Минусы**:
- Worker контейнер должен иметь torch+whisper (большой образ)
- Нет изоляции GPU (если масштабировать worker, все будут конкурировать за GPU)
- Нет мониторинга GPU memory

---

### **Фаза 2: Правильная Архитектура (рекомендуется)**

**Цель**: Отдельный GPU-Worker контейнер

**Что делать**:

1. **Создать новый Dockerfile.gpu-worker**
   ```dockerfile
   FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04
   RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   RUN pip install openai-whisper
   COPY . /app
   ENTRYPOINT ["python", "gpu_worker.py"]
   ```

2. **Создать gpu_worker.py** (аналог job_worker.py, но специализированный)
   ```python
   from transkribator_modules.jobs.handlers import dispatch_job
   
   class GPUJobWorker(JobWorker):
       def __init__(self, config):
           super().__init__(config)
           self.job_types = ["media_gpu_transcription"]  # только GPU jobs!
           self.pipeline = WhisperPipeline()  # load once
           self.model_loaded = False
   
       def start(self):
           # Load model once
           self.pipeline.model = whisper.load_model("base", device="cuda")
           self.model_loaded = True
           super().start()
   ```

3. **Обновить docker-compose.yml**
   ```yaml
   gpu-worker:
     build:
       dockerfile: Dockerfile.gpu-worker
     container_name: cyberkitty19-gpu-worker
     environment:
       - JOB_TYPES=media_gpu_transcription
       - JOB_POLL_INTERVAL=2
       - CUDA_VISIBLE_DEVICES=0
     volumes:
       - shared-storage:/app/media
     deploy:
       resources:
         reservations:
           devices:
             - driver: nvidia
               count: 1
               capabilities: [gpu]
   ```

4. **Обновить Bot логику**
   ```python
   def enqueue_media_job(...):
       file_size_mb = file.size / 1024**2
       if file_size_mb > 50:
           job_type = "media_gpu_transcription"
       else:
           job_type = "media_processing"
       enqueue_job(job_type=job_type, ...)
   ```

5. **Добавить Prep-Worker (опционально)**
   ```yaml
   prep-worker:
     build: .  # обычный Python
     container_name: cyberkitty19-prep-worker
     environment:
       - JOB_TYPES=media_prepare
     # FFmpeg подготовка
   ```

**Плюсы**:
- ✅ Полная изоляция GPU (только GPU-worker имеет CUDA)
- ✅ Независимое масштабирование (добавить GPU worker легко)
- ✅ Обычные worker'ы остаются легкими (без GPU)
- ✅ Мониторинг GPU памяти возможен
- ✅ Соответствует лучшим практикам microservices

**Минусы**:
- Нужны изменения в docker-compose
- Нужны изменения в bot логике для выбора job_type
- Нужен новый образ для GPU (nvidia/cuda base)

---

## 8️⃣ Рекомендация

### **Сейчас (текущее состояние)**

Текущая архитектура **в основном правильная**, но:
- ❌ GPU pipeline (`pipeline_orchestrator.py`) существует отдельно, не интегрирован
- ❌ Worker контейнер не имеет GPU поддержки
- ❌ Нет механизма для выбора GPU vs CPU backend

### **Что Делать**

**Вариант A: Быстрая Интеграция (1-2 часа)**
1. Добавить GPU backend в `TranscribeClient` или создать новый stage
2. Добавить env var для выбора backend
3. В worker: если backend=gpu, использовать GPU pipeline

**Вариант B: Правильная Архитектура (4-6 часов)**
1. Создать отдельный `gpu-worker.py` с isolated CUDA
2. Создать `Dockerfile.gpu-worker` с nvidia cuda base
3. Обновить docker-compose с gpu-worker сервисом
4. Bot выбирает job_type ("media_gpu_transcription" vs "media_processing")
5. GPU worker и обычный worker работают параллельно

### **Я Рекомендую: Вариант B** (Фаза 2)

Это правильная архитектура, и вы уже сделали большую часть работы:
- ✅ `pipeline_orchestrator.py` готов
- ✅ `Dockerfile.whisper-gpu` готов
- ✅ Job worker system уже есть
- Остается просто: отдельный gpu-worker контейнер + выбор job_type в bot

---

## Итоговая Таблица Соответствия

| Требование | Текущее | Фаза 1 | Фаза 2 |
|-----------|---------|--------|--------|
| Bot изолирован от GPU | ✅ | ✅ | ✅ |
| Queue-based обработка | ✅ | ✅ | ✅ |
| Shared storage | ✅ | ✅ | ✅ |
| Асинхронная обработка | ✅ | ✅ | ✅ |
| GPU worker изолирован | ❌ | ⚠️ | ✅ |
| Отдельный GPU контейнер | ❌ | ❌ | ✅ |
| Динамическая маршрутизация | ❌ | ✅ | ✅ |
| Ограничение concurrency | ❌ | ⚠️ | ✅ |
| Мониторинг GPU | ❌ | ❌ | ✅ |
| Легкое масштабирование | ❌ | ⚠️ | ✅ |

---

Это детальный анализ текущего состояния. Какой вариант вам нравится больше — Фаза 1 или Фаза 2?

