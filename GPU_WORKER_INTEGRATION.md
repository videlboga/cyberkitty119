# 🎯 ИНТЕГРАЦИЯ GPU В СУЩЕСТВУЮЩИЙ WORKER

## 🏗️ Архитектура Существующей Системы

### Текущий Flow

```
Media Job Queue
     ↓
worker.py (job_worker.py)
     ├─ Берет джоб из очереди
     ├─ Распределяет по типам (dispatch_job)
     ├─ Для media jobs: вызывает default_transcribe_media
     └─ default_transcribe_media:
         ├─ Пытается использовать transcribe_client
         └─ Если не работает → DeepInfra API (fallback)
     ↓
Результат сохраняется → БД + Файлы
     ↓
Бот показывает пользователю результат
```

### Ключевые Компоненты

| Компонент | Файл | Роль |
|-----------|------|------|
| **Job Queue** | `transkribator_modules/jobs/queue.py` | Хранилище задач |
| **Dispatcher** | `transkribator_modules/jobs/handlers.py` | Распределение по типам |
| **Transcribe** | `transkribator_modules/jobs/services.py` | Транскрибация (линия 97+) |
| **Worker** | `job_worker.py` | Главный loop обработки |

---

## 🔧 ГДЕ И КАК ВСТАВИТЬ GPU

### Option A: Заменить `default_transcribe_media` (РЕКОМЕНДУЕТСЯ)

**Файл для редактирования:** `transkribator_modules/jobs/services.py` (линия 97)

**Текущий код:**

```python
def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Transcribe media (default hook)"""
    
    # Пытается TranscribeClient (если включен)
    if use_transcribe_client:
        client = TranscribeClient(default_mode=mode)
        result = client.transcribe(media_path, mode=mode)
        return result["text"]
    
    # Fallback на OpenRouter API (DeepInfra)
    result = _invoke_transcribe_api(media_path)
    return result["text"]
```

**Что изменить:**

```python
def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Transcribe media - with GPU priority"""
    
    # 1️⃣ СНАЧАЛА ПРОБУЕМ GPU
    try:
        logger.info("Trying GPU transcription...")
        from pipeline_orchestrator import WhisperPipeline
        
        pipeline = WhisperPipeline()
        result = pipeline.process(Path(media_path))
        
        if result["status"] == "success":
            # Читаем результат из файла
            result_file = Path(result["result_file"])
            if result_file.exists():
                with open(result_file) as f:
                    data = json.load(f)
                    logger.info(f"✓ GPU transcription OK: {len(data.get('text', ''))} chars")
                    return data["text"]
    
    except Exception as exc:
        logger.warning(f"GPU transcription failed, falling back to API: {exc}")
    
    # 2️⃣ FALLBACK НА DEEPINFRA API
    logger.info("Using DeepInfra API (fallback)...")
    result = _invoke_transcribe_api(media_path)
    return result["text"]
```

**Преимущества:**
- ✅ Не нужно менять бота
- ✅ Не нужно менять очередь
- ✅ Прозрачное переключение GPU↔DeepInfra
- ✅ Автоматический fallback
- ✅ Экономия на API вызовах

**Недостатки:**
- GPU работает синхронно (блокирует worker)
- При GPU ошибке → долгая обработка

---

### Option B: Отдельный GPU Worker (СЛОЖНЕЕ, но лучше)

**Создать:** `transkribator_modules/jobs/gpu_handler.py`

**Логика:**
1. Добавить тип джоба: `"gpu_transcribe"`
2. В хендлере проверить GPU доступность
3. Если GPU занята → отправить обратно в обычную очередь

```python
@register_job_handler("gpu_transcribe")
async def handle_gpu_transcribe_job(context):
    """Handle media job with GPU priority"""
    
    # Проверить GPU
    gpu_available = check_gpu_available()
    
    if not gpu_available:
        # Переотправить в обычную очередь
        convert_to_regular_job(context)
        return
    
    # Использовать GPU
    result = pipeline.process(Path(media_path))
    save_result(context, result)
```

**Преимущества:**
- ✅ Асинхронная обработка
- ✅ Разделение очередей
- ✅ Лучший контроль

**Недостатки:**
- ⚠️ Нужно менять джоб тип
- ⚠️ Нужно добавлять джоб правильного типа
- ⚠️ Сложнее в отладке

---

## ✅ РЕКОМЕНДУЕМОЕ РЕШЕНИЕ: OPTION A

### Шаг 1: Посмотреть текущую функцию

```bash
# Открыть
nano transkribator_modules/jobs/services.py +97
```

### Шаг 2: Заменить `default_transcribe_media`

Найти функцию и добавить GPU попытку в начало:

```python
import json
from pathlib import Path
from pipeline_orchestrator import WhisperPipeline  # Новый импорт

def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Transcribe media with GPU priority"""
    
    # ===== GPU ПОПЫТКА =====
    try:
        logger.info(f"🔄 Trying GPU transcription for {media_path}...")
        
        pipeline = WhisperPipeline()
        result = pipeline.process(Path(media_path))
        
        if result["status"] == "success":
            # Читаем основной результат
            result_file = Path(result["result_file"])
            if result_file.exists():
                with open(result_file, "r") as f:
                    data = json.load(f)
                    transcript = data.get("text", "")
                    if transcript.strip():
                        logger.info(f"✅ GPU transcription success: {len(transcript)} chars in {result['transcription_time']:.1f}s")
                        # Логируем метрику
                        context.job.metadata = {
                            "transcription_method": "gpu",
                            "gpu_time": result["transcription_time"],
                            "segments": result["segments"]
                        }
                        return transcript
    
    except Exception as exc:
        logger.warning(f"⚠️  GPU transcription failed: {exc}")
        logger.debug("Falling back to DeepInfra API...", exc_info=True)
    
    # ===== FALLBACK НА DEEPINFRA =====
    logger.info("📡 Using DeepInfra API (fallback)...")
    
    # Существующий код - как было раньше
    if use_transcribe_client:
        client = TranscribeClient(default_mode=mode)
        result = client.transcribe(media_path, mode=mode)
        return result["text"]
    
    result = _invoke_transcribe_api(media_path)
    return result["text"]
```

---

## 🚀 ПРОЦЕСС ИНТЕГРАЦИИ (5 шагов)

### Шаг 1: Добавить импорты

**Файл:** `transkribator_modules/jobs/services.py` (в начало)

```python
import json
from pathlib import Path

try:
    from pipeline_orchestrator import WhisperPipeline
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False
    logger.info("GPU pipeline not available, will use DeepInfra only")
```

### Шаг 2: Обновить `default_transcribe_media` функцию

**Файл:** `transkribator_modules/jobs/services.py` (линия 97)

Заменить существующий код (см. выше)

### Шаг 3: Добавить конфигурацию в `.env`

```bash
# GPU Configuration
GPU_ENABLED=true
GPU_FALLBACK_ON_ERROR=true
GPU_TIMEOUT_SECONDS=600
```

### Шаг 4: Добавить условие отключения GPU

```python
def default_transcribe_media(context: "MediaPipelineContext", media_path: str) -> str:
    """Transcribe media with optional GPU"""
    
    # Проверить конфигурацию
    gpu_enabled = os.getenv("GPU_ENABLED", "false").lower() == "true"
    
    if not gpu_enabled or not GPU_AVAILABLE:
        logger.info("GPU disabled or unavailable, using DeepInfra")
        return _transcribe_with_api(media_path)
    
    # GPU попытка...
```

### Шаг 5: Тестирование

```bash
# 1. Запустить worker с нашей функцией
python3 job_worker.py

# 2. Отправить файл боту
# Скачать видео/аудио через бот

# 3. Проверить логи
tail -f cyberkitty119.log | grep "GPU\|transcription"

# 4. Убедиться что:
# ✅ GPU попытка выполнена
# ✅ Результат правильный
# ✅ Время обработки снизилось (57s vs 3+ минут на API)
```

---

## 📊 КАКИЕ УЛУЧШЕНИЯ ОЖИДАТЬ

| Метрика | DeepInfra (текущее) | GPU (новое) | Экономия |
|---------|---|---|---|
| **Время 21-мин файла** | 3-5 минут | 57 секунд | 3-5x быстрее |
| **Стоимость за файл** | $0.05-0.10 | $0 (локально) | 100% |
| **Параллелизм** | 1 файл в раз | 5 файлов одновременно | 5x больше |
| **Нагрузка на API** | Высокая | Низкая | Снижение ↓ |

---

## ⚙️ ГИБРИДНЫЙ РЕЖИМ (если GPU выходит из строя)

```python
def default_transcribe_media(context, media_path):
    gpu_enabled = os.getenv("GPU_ENABLED", "true").lower() == "true"
    fallback_on_error = os.getenv("GPU_FALLBACK_ON_ERROR", "true").lower() == "true"
    
    if gpu_enabled:
        try:
            result = gpu_transcribe(media_path)
            if result:
                return result
        except Exception as e:
            if not fallback_on_error:
                raise  # Пробросить ошибку дальше
            logger.warning(f"GPU failed, fallback to API: {e}")
    
    # Fallback на DeepInfra всегда
    return api_transcribe(media_path)
```

**Конфигурация:**
```bash
GPU_ENABLED=true              # Включить GPU
GPU_FALLBACK_ON_ERROR=true    # Fallback если GPU ошибка
```

---

## 🎯 ЧТО НЕ МЕНЯЕТСЯ

### Бот не меняется
- ✅ `handle_message` - как было
- ✅ `process_video_file` - как было
- ✅ `process_audio_file` - как было
- ✅ `enqueue_media_job` - как было

### Очередь не меняется
- ✅ `enqueue_media_job` - как было
- ✅ Job структура - как было
- ✅ Callback система - как было

### База данных не меняется
- ✅ Таблицы - как было
- ✅ Схема - как было
- ✅ Индексы - как было

### Только меняется
- ✅ `default_transcribe_media` функция в `services.py`
- ✅ Добавить GPU попытку в начало
- ✅ Fallback на API если GPU ошибка

---

## 📋 КОНЕЧНЫЙ RESULT

После интеграции:

```python
# job_worker.py получает медиа джоб
│
├─ dispatcher перенаправляет → default_transcribe_media
│
├─ default_transcribe_media:
│  ├─ 🟢 Если GPU доступна:
│  │  └─ GPU транскрибация (57s для 21-мин аудио)
│  │
│  └─ 🔴 Если GPU ошибка/занята:
│     └─ DeepInfra API (3-5 минут)
│
└─ Результат → БД и файлы
```

**Для пользователя:** Всё работает как раньше, но:
- ✅ Быстрее (57s vs 3+ мин)
- ✅ Дешевле (бесплатно вместо платных API вызовов)
- ✅ Надежнее (fallback автоматический)

---

## ✅ ИТОГО

**Что нужно сделать:**
1. ✅ Добавить импорты в `services.py`
2. ✅ Обновить `default_transcribe_media` функцию
3. ✅ Добавить конфигурацию в `.env`
4. ✅ Тестировать

**Время:** 30 минут

**Сложность:** Низкая

**Риск:** Минимальный (есть полный fallback)

**Результат:** 
- 3-5x быстрее
- Бесплатно для локального GPU
- Без изменений в боте и очереди

🚀 **Готово?**

