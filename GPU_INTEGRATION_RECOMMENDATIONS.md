# 🚀 GPU Integration - Рекомендации по Архитектуре

## 📌 Текущее Состояние

Ты уже создал:
- ✅ `pipeline_orchestrator.py` - GPU орхестратор (работает, протестирован)
- ✅ API эндпоинты в `api_server.py` (POST /api/v1/transcribe-gpu)
- ✅ Хендлер для бота в `handlers_gpu.py` (готов к интеграции)

Но мы НЕ добавили GPU в основной пайплайн обработки!

---

## 🎯 Проблема

Текущая система обработки медиа:

```
User sends video
        ↓
Bot: handle_message()
        ↓
Bot: process_video_file()
    ├─ Скачивает видео
    ├─ Извлекает аудио FFmpeg
    ├─ Создает job в БД тип "transcribe_deepinfra"
    └─ ЗАКАНЧИВАЕТ РАБОТУ
        ↓
Worker: опрашивает БД
        ↓
Worker: handle_transcribe_deepinfra()
    ├─ Вызывает DeepInfra API
    ├─ Получает результат
    └─ Сохраняет в БД
        ↓
Bot: опрашивает БД (polling)
        ↓
Bot: находит completed job
        ↓
Bot: отправляет результат пользователю
```

**Твой GPU pipeline сейчас вне этого потока!**

Когда ты делаешь `handle_gpu_transcription`, ты создал ПАРАЛЛЕЛЬНЫЙ обработчик, но не интегрировал с основным пайплайном.

---

## 🛠️ Два Варианта Интеграции

### **Вариант А: GPU КАК НОВЫЙ ТИП JOB (Рекомендуется)**

**Преимущества:**
- ✅ Интегрируется в существующую архитектуру
- ✅ Job queueing и rate limiting работают автоматически
- ✅ БОТ не блокируется
- ✅ Можно обрабатывать параллельно с DeepInfra
- ✅ Все логируется в БД
- ✅ Можно мониторить прогресс

**Процесс:**

```
1. МОДИФИЦИРУЕМ handle_message():

   if update.message.video:
       # Скачиваем файл как обычно
       audio_path = await download_and_extract_audio()
       
       # НОВОЕ: Проверяем, нужен ли GPU?
       # Вариант 1: По размеру файла
       if file_size_mb > 50:
           job_type = "transcribe_gpu"
       else:
           job_type = "transcribe_deepinfra"
       
       # Вариант 2: По команде /gpu_transcribe (пользователь выбирает)
       # if context.user_data.get("use_gpu"):
       #     job_type = "transcribe_gpu"
       
       # Создаем job как обычно
       job = ProcessingJob(
           user_id=user_id,
           job_type=job_type,  ← "transcribe_gpu" или "transcribe_deepinfra"
           media_path=audio_path,
           status="pending"
       )


2. ДОБАВЛЯЕМ ОБРАБОТЧИК В WORKER:

   # В transkribator_modules/jobs/handlers.py
   
   def handle_transcribe_gpu(job):
       from pipeline_orchestrator import WhisperPipeline
       
       pipeline = WhisperPipeline()
       result = pipeline.process(Path(job.media_path))
       
       job.result = {
           "transcript": result["transcription_text"],
           "segments": result["segments"],
           "job_id": result["job_id"]
       }
       job.status = "completed"
       return result


3. РЕГИСТРИРУЕМ ОБРАБОТЧИК:

   # В transkribator_modules/jobs/handlers.py (registry)
   
   registry["transcribe_gpu"] = handle_transcribe_gpu
```

**Плюсы:**
- Минимальные изменения
- Работает через существующий job queue
- Rate limiting работает (максимум 5 параллельных задач GPU)
- БОТ не блокируется
- Можно легко переключаться между GPU и DeepInfra

---

### **Вариант Б: КОМАНДА /transcribe_gpu (Для продвинутых пользователей)**

**Преимущества:**
- ✅ Явный выбор пользователя
- ✅ Не нужно модифицировать основной handler
- ✅ Может быть быстрее (если GPU в той же машине)

**Процесс:**

```
1. ДОБАВЛЯЕМ КОМАНДУ:

   # В transkribator_modules/bot/commands.py
   
   async def transcribe_gpu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
       """User explicitly selects GPU transcription"""
       if not update.message.reply_to_message:
           await update.message.reply_text(
               "📎 Ответь этой командой на видео/аудио файл:\n"
               "/transcribe_gpu"
           )
           return
       
       media_msg = update.message.reply_to_message
       media = media_msg.video or media_msg.audio or media_msg.document
       
       if not media:
           await update.message.reply_text("❌ Это не видео/аудио")
           return
       
       # Создаем job с типом GPU
       job = ProcessingJob(
           user_id=update.effective_user.id,
           job_type="transcribe_gpu",
           media_path=...,
           status="pending"
       )
       db.add(job)
       db.commit()
       
       await update.message.reply_text("⏳ Начинаю GPU транскрибацию...")


2. РЕГИСТРИРУЕМ КОМАНДУ В main.py:

   from transkribator_modules.bot.commands import transcribe_gpu_command
   
   application.add_handler(CommandHandler("transcribe_gpu", transcribe_gpu_command))
```

**Минусы:**
- Более явно (не все пользователи найдут)
- Требует дополнительных команд

---

## 🏆 Рекомендуемое Решение

**Вариант А + элементы Варианта Б:**

```
1. По УМОЛЧАНИЮ: используем DeepInfra (как сейчас)

2. НОВОЕ: добавляем опцию для пользователя:
   - Команда: /settings → выбрать способ транскрибации
   - Или: автоматически GPU для файлов > 100MB
   
3. В БД User добавляем поле:
   preferred_transcription_method: "auto" | "gpu" | "deepinfra"
   
4. В handle_message() проверяем:
   if user.preferred_transcription_method == "gpu":
       job_type = "transcribe_gpu"
   elif user.preferred_transcription_method == "auto" and file_size_mb > 100:
       job_type = "transcribe_gpu"
   else:
       job_type = "transcribe_deepinfra"
```

---

## ⚡ Быстрая Реализация (15 минут)

Если хочешь быстро:

### **Шаг 1: Добавить обработчик в worker**

```python
# Добавить в transkribator_modules/jobs/handlers.py

from pipeline_orchestrator import WhisperPipeline
from pathlib import Path

def handle_transcribe_gpu(job):
    """Process job with GPU Whisper pipeline"""
    try:
        pipeline = WhisperPipeline()
        result = pipeline.process(Path(job.media_path))
        
        job.result = {
            "transcript": result.get("transcription_text"),
            "segments": result.get("segments"),
            "job_id": result.get("job_id"),
            "total_time": result.get("total_time"),
            "preparation_time": result.get("preparation_time"),
            "transcription_time": result.get("transcription_time"),
        }
        job.status = "completed"
        return result
    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        raise

# Регистрируем
registry["transcribe_gpu"] = handle_transcribe_gpu
```

### **Шаг 2: Добавить поле в User model**

```python
# В transkribator_modules/db/models.py

class User(Base):
    # ... существующие поля ...
    
    # НОВОЕ:
    gpu_transcription_enabled: bool = Column(Boolean, default=False)
```

### **Шаг 3: Модифицировать handle_message()**

```python
# В transkribator_modules/bot/handlers.py

async def process_video_file(update, context, video, status_message=None):
    # ... существующий код ...
    
    user = UserService(SessionLocal()).get_or_create_user(update.effective_user)
    
    # НОВОЕ: выбираем способ обработки
    if user.gpu_transcription_enabled:
        job_type = "transcribe_gpu"
    else:
        job_type = "transcribe_deepinfra"  # ← По умолчанию
    
    job = ProcessingJob(
        user_id=update.effective_user.id,
        job_type=job_type,  ← ВЫБРАННЫЙ ТИП
        media_path=str(audio_path),
        status="pending"
    )
    
    # ... остаток кода как обычно ...
```

### **Шаг 4: Добавить команду включения/отключения GPU**

```python
# В transkribator_modules/bot/commands.py

async def toggle_gpu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = UserService(SessionLocal()).get_or_create_user(update.effective_user)
    user.gpu_transcription_enabled = not user.gpu_transcription_enabled
    SessionLocal().commit()
    
    status = "включена ✅" if user.gpu_transcription_enabled else "отключена ❌"
    await update.message.reply_text(f"GPU транскрибация {status}")

# Регистрируем в main.py:
application.add_handler(CommandHandler("gpu", toggle_gpu_command))
```

---

## 📊 Сравнение Вариантов

| Критерий | Вариант А (через job) | Вариант Б (команда) | Рекомендуемый |
|----------|----------------------|---------------------|--------------|
| **Интеграция** | Родная для системы | Отдельный путь | ✅ А |
| **Параллелизм** | Через worker queue | Через job | ✅ А |
| **Удобство** | Автоматически | Явно | ✅ А |
| **Масштабируемость** | Хорошо | Хорошо | ✅ А |
| **Rate limiting** | Встроен | Нужно добавить | ✅ А |
| **Пользователю очевидно** | Нет (работает за сценой) | Да (команда) | Оба |

---

## 🚀 План Действий

### **Сегодня:**
1. Добавить обработчик `handle_transcribe_gpu` в worker
2. Добавить поле `gpu_transcription_enabled` в User model
3. Добавить проверку в `handle_message()`

### **Тестирование:**
1. Создать тестовый user с GPU включенным
2. Отправить видео
3. Проверить, что в БД создается job с типом `transcribe_gpu`
4. Проверить, что worker обрабатывает его

### **Развертывание:**
1. Запустить worker с поддержкой нового типа job
2. Добавить команду `/gpu` для включения/отключения
3. Документировать для пользователей

---

## 🎯 Результат

После интеграции через Вариант А система будет выглядеть так:

```
User sends video (large file, > 100MB)
        ↓
Bot: handle_message() определяет: нужен ли GPU?
        ↓
Bot: process_video_file()
    ├─ Скачивает видео
    ├─ Извлекает аудио FFmpeg
    ├─ Создает job тип "transcribe_gpu"  ← GPU!
    └─ ЗАКАНЧИВАЕТ РАБОТУ
        ↓
Worker: опрашивает БД, находит job тип "transcribe_gpu"
        ↓
Worker: handle_transcribe_gpu()
    ├─ Вызывает WhisperPipeline.process()
    ├─ Получает результат (57 секунд для 21 мин)
    └─ Сохраняет в БД
        ↓
Bot: опрашивает БД (polling)
        ↓
Bot: находит completed job
        ↓
Bot: отправляет результат пользователю ← RESULT!
```

**Преимущество:** БОТ всегда свободен, обработка параллельна, все логируется, rate limiting работает автоматически!

