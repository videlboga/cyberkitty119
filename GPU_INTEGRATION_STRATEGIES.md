# 🔌 Стратегии Интеграции GPU в Bot Pipeline

После детального разбора контейнера бота, вот 3 возможных стратегии интеграции GPU.

---

## 📊 Сравнение Стратегий

| Стратегия | Время | Сложность | Риск | Прибыль |
|-----------|-------|-----------|------|---------|
| **1. Параллельное добавление** | 30 мин | Низкая | Минимальный | Высокая |
| **2. Условное переключение** | 1-2 часа | Средняя | Низкий | Средняя |
| **3. Полная замена DeepInfra** | 2-3 часа | Высокая | Средний | Максимальная |

---

## 🎯 Стратегия 1: Параллельное Добавление (РЕКОМЕНДУЕТСЯ)

### Принцип
**Добавить GPU как отдельный вариант, оставить DeepInfra базовым.**

- DeepInfra по умолчанию (текущее поведение)
- `/transcribe_gpu` команда для GPU транскрибации
- Оба метода работают параллельно
- Нулевой риск поломать существующее

### Реализация

**Шаг 1:** Добавить в `transkribator_modules/main.py` (строка ~145):

```python
from transkribator_modules.bot.handlers_gpu import handle_gpu_transcription, handle_gpu_status

# После других CommandHandler'ов:
application.add_handler(CommandHandler("transcribe_gpu", handle_gpu_transcription))
application.add_handler(CommandHandler("gpu_status", handle_gpu_status))
```

**Шаг 2:** Пользователи могут выбрать:

```
/start → меню → "⚡ Быстрая GPU транскрибация"
или
Просто отправить видео → стандартная DeepInfra обработка
```

### Преимущества
✅ Нулевой риск для существующих пользователей  
✅ Быстрая реализация (30 минут)  
✅ Можно тестировать GPU без влияния на основной сервис  
✅ Пользователи сами выбирают метод  

### Недостатки
❌ Требует активного выбора пользователя  
❌ Утроение нагрузки на поддержку (три варианта вместо одного)  

### Код (Уже готов!)

```python
# transkribator_modules/bot/handlers_gpu.py

async def handle_gpu_transcription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /transcribe_gpu command - GPU-accelerated transcription."""
    
    # 1. Check if command is a reply to media
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "📎 Используй команду как ответ на файл видео/аудио:\n\n"
            "1. Отправь видео/аудио файл\n"
            "2. Ответь на него: /transcribe_gpu"
        )
        return
    
    reply_msg = update.message.reply_to_message
    
    # 2. Extract media from message
    # 3. Download from Telegram
    # 4. Call GPU API
    # 5. Send results to user
    # (ВСЁ УЖЕ РЕАЛИЗОВАНО!)
```

---

## 🔀 Стратегия 2: Условное Переключение (РЕКОМЕНДУЕТСЯ)

### Принцип
**Автоматически выбирать GPU или DeepInfra в зависимости от условия.**

```python
if file_size_mb > 100:
    use_gpu()              # Большие файлы
else:
    use_deepinfra()        # Маленькие файлы
```

Или:

```python
if user.is_premium():
    use_gpu()              # Premium = GPU
else:
    use_deepinfra()        # Free = DeepInfra
```

### Реализация

**Шаг 1:** Модифицировать `transkribator_modules/jobs/services.py`:

```python
class MediaPipelineServices:
    def transcribe(self, context, media_path):
        """Choose transcription method based on conditions."""
        
        # Условие 1: по размеру файла
        file_size = Path(media_path).stat().st_size / (1024**2)  # MB
        if file_size > 100:
            return self._transcribe_gpu(media_path)
        
        # Условие 2: по плану пользователя
        # if context.payload.extra.get('user_plan') == 'premium':
        #     return self._transcribe_gpu(media_path)
        
        # Default: DeepInfra
        return self._transcribe_deepinfra(media_path)
    
    def _transcribe_gpu(self, media_path):
        """Call GPU pipeline."""
        import requests
        response = requests.post(
            "http://localhost:8000/api/v1/transcribe-gpu",
            json={"file_path": str(media_path), "language": "ru"},
            timeout=600
        )
        result = response.json()
        # Extract text from result files
        with open(result['result_file'], 'r') as f:
            return json.load(f)['transcription_text']
    
    def _transcribe_deepinfra(self, media_path):
        """Current implementation - call DeepInfra API."""
        # Существующая логика
        pass
```

### Преимущества
✅ Автоматический выбор, пользователь не выбирает  
✅ Интеллектуальное распределение нагрузки  
✅ GPU для «тяжелых» файлов, DeepInfra для быстрых  
✅ Экономия денег на API (GPU бесплатен)  

### Недостатки
❌ Сложнее в отладке (два пути выполнения)  
❌ Нужна координация между сервисами  

---

## 🔄 Стратегия 3: Полная Замена DeepInfra (ИНТЕРЕСНО)

### Принцип
**Заменить DeepInfra на GPU полностью. Использовать GPU как основной сервис.**

```
DeepInfra ──► GPU Pipeline
(вычелить)    (использовать вместо)
```

### Реализация

**Шаг 1:** Заменить вызов DeepInfra на GPU в `services.py`:

```python
class MediaPipelineServices:
    def transcribe(self, context, media_path):
        """Use GPU for all transcriptions."""
        
        import requests
        response = requests.post(
            "http://localhost:8000/api/v1/transcribe-gpu",
            json={"file_path": str(media_path), "language": "ru"},
            timeout=600
        )
        
        if response.status_code != 200:
            raise Exception(f"GPU transcription failed: {response.text}")
        
        result = response.json()
        
        # Read result from media/results/
        result_file = result['result_file']
        with open(result_file, 'r') as f:
            result_data = json.load(f)
        
        return result_data['text']
```

### Преимущества
✅ Максимальная скорость (3.97x vs DeepInfra)  
✅ Максимальная экономия (GPU бесплатен vs $$ API)  
✅ Полный контроль над обработкой  
✅ Работает оффлайн (не зависит от интернета)  

### Недостатки
❌ Высокий риск (переводим всех пользователей на GPU)  
❌ Если GPU упадет → все падает  
❌ Нужна готовность к быстрому откату  
❌ Требует тщательного тестирования  

### Рекомендуемый Процесс

```
Phase 1: Testing (1 неделя)
  ├─ Включить GPU для 10% пользователей
  ├─ Мониторить ошибки, задержки
  └─ Собрать метрики качества

Phase 2: Rollout (1 неделя)
  ├─ Увеличить до 50% пользователей
  ├─ Продолжить мониторинг
  └─ Иметь готовый откат

Phase 3: Full Deployment (1 день)
  ├─ 100% пользователей на GPU
  ├─ Провести A/B тест качества vs DeepInfra
  └─ Отключить DeepInfra
```

---

## 🎯 Рекомендация: Гибридный Подход

### Стратегия: 1 + 2 (Лучшее Из Обоих)

```
┌────────────────────────────────────────────────────────────┐
│ Вариант для пользователей:                                │
│                                                            │
│ 1️⃣ Отправить видео + /transcribe ──► DeepInfra (текущий)│
│ 2️⃣ Отправить видео + /transcribe_gpu ──► GPU (новый)    │
│ 3️⃣ /settings:                                              │
│     └─ [✓] Автоматически использовать GPU для больших   │
│     └─ [✓] Приоритет скорости (GPU) vs экономия (API)   │
└────────────────────────────────────────────────────────────┘
```

### Реализация

**Шаг 1:** Добавить GPU команду (Стратегия 1)
```python
application.add_handler(CommandHandler("transcribe_gpu", handle_gpu_transcription))
```

**Шаг 2:** Добавить автоматическое переключение (Стратегия 2)
```python
if file_size_mb > 100:  # Большие файлы → GPU
    use_gpu = True
else:                    # Маленькие файлы → DeepInfra
    use_gpu = False
```

**Шаг 3:** Добавить пользовательское управление
```python
if user.settings.get('prefer_gpu'):
    use_gpu = True
```

---

## 📋 Чек-лист Реализации

### Для Стратегии 1 (30 минут)
- [ ] Открыть `transkribator_modules/main.py`
- [ ] Найти строку ~30 с импортами
- [ ] Добавить: `from transkribator_modules.bot.handlers_gpu import handle_gpu_transcription, handle_gpu_status`
- [ ] Найти строку ~145 с CommandHandler'ами
- [ ] Добавить две новые строки
- [ ] Протестировать команду `/transcribe_gpu`
- [ ] Готово! ✅

### Для Стратегии 2 (2 часа)
- [ ] Все из Стратегии 1
- [ ] Модифицировать `transkribator_modules/jobs/services.py`
- [ ] Добавить условную логику в `transcribe()`
- [ ] Добавить методы `_transcribe_gpu()` и `_transcribe_deepinfra()`
- [ ] Протестировать с разными размерами файлов
- [ ] Добавить логирование какой метод использовался
- [ ] Готово! ✅

### Для Стратегии 3 (4 часа + риск)
- [ ] Все из Стратегии 2
- [ ] Создать функцию отката (переключение обратно на DeepInfra)
- [ ] Развернуть на тестовой группе (10%)
- [ ] Мониторить метрики 3-5 дней
- [ ] Постепенное расширение (10% → 50% → 100%)
- [ ] Финальное тестирование и обучение команды
- [ ] Готово! ✅

---

## 🚨 Риски и Миtigations

### Риск 1: GPU Упадет

**Миtigations:**
```python
try:
    response = requests.post("http://localhost:8000/api/v1/transcribe-gpu", timeout=600)
except (ConnectionError, Timeout):
    logger.error("GPU API unavailable, falling back to DeepInfra")
    return use_deepinfra(media_path)
```

### Риск 2: Качество GPU Хуже DeepInfra

**Миtigations:**
- Протестировать на примерах перед развертыванием
- A/B тест на подмножестве пользователей
- Мониторить user feedback и ошибки
- Метрики: WER (Word Error Rate), RTF (Real Time Factor)

### Риск 3: GPU Медленнее DeepInfra

**Миtigations:**
- Использовать GPU только для больших файлов
- DeepInfra для маленьких файлов
- Параллельная обработка (несколько файлов на GPU)
- Кэширование результатов

### Риск 4: Конфликты памяти

**Миtigations:**
- Ограничить на 5 параллельных задач (уже учтено)
- Мониторить VRAM usage
- Добавить очередь обработки в случае переполнения

---

## 🏁 Финальные Рекомендации

### ✅ РЕКОМЕНДУЕТСЯ: Стратегия 1 + 2

1. **Сейчас (30 минут):** Добавить `/transcribe_gpu` команду
2. **Завтра (2 часа):** Добавить автоматическое переключение по размеру
3. **На неделю:** Мониторить стабильность
4. **Через 2 недели:** Решить о полной замене или оставить как опцию

### ✅ Преимущества Такого Подхода

```
✓ Минимальный риск на старте (30 минут реализации)
✓ Быстрый откат если что-то пойдет не так
✓ Данные для принятия решения о полной замене
✓ Пользователи сам выбирают метод
✓ Экономия денег уже с первого дня
✓ Опыт для дальнейшей оптимизации
```

### ❌ НЕ РЕКОМЕНДУЕТСЯ (изначально)

```
✗ Полная замена DeepInfra сразу (Стратегия 3)
  Причины:
  - Риск потери всех пользователей если GPU упадет
  - Без тестирования на реальной нагрузке
  - Сложно откатиться если качество плохое
```

---

## 🚀 Готовы Начать?

```bash
# Шаг 1: Добавить импорт в main.py
nano transkribator_modules/main.py
# Добавить две строки

# Шаг 2: Перезагрузить бот
docker restart cyberkitty19-transkribator-bot

# Шаг 3: Протестировать
# В Telegram: /transcribe_gpu → ответить на видео

# Готово! 🎉
```

