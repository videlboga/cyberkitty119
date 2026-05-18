# 🤖 Подробный Разбор Логики Telegram Бота

## 📊 Архитектура Системы

```
┌─────────────────────────────────────────────────────────────────┐
│                      Telegram User                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │Telegram API  │
                    │  (T.me Bot)  │
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌─────▼──────┐   ┌─────▼──────┐
    │  Commands │   │   Buttons  │   │   Media    │
    │ (/start)  │   │  (Callback)│   │  (Video,   │
    └─────┬─────┘   └─────┬──────┘   │   Audio)   │
          │                │         └─────┬──────┘
          │                │               │
    ┌─────────────────────────────────────────────┐
    │  Telegram Bot (Python-telegram-bot)         │
    │  cyberkitty_modular.py                      │
    └─────────────────────────────────────────────┘
          │                │                │
    ┌─────▼────────┬──────▼────────┬───────▼─────────┐
    │   Commands   │  Callbacks    │  MessageHandler │
    │  Handler     │  Handler      │  (Media)        │
    └─────┬────────┴──────┬────────┴───────┬─────────┘
          │               │                │
    ┌─────────────────────────────────────────────────────┐
    │  Business Logic (handlers.py, callbacks.py, etc)    │
    └──────────────────────┬────────────────────────────┘
          │
    ┌─────────────────────────────────────────────────────┐
    │  Database (PostgreSQL) + File Storage               │
    │  • User profiles (limits, settings)                 │
    │  • Transcriptions history                           │
    │  • Payments, referrals                              │
    └──────────────────────────────────────────────────────┘
          │
    ┌─────────────────────────────────────────────────────┐
    │  External Services                                  │
    │  • DeepInfra API (Whisper transcription)           │
    │  • LLM (text formatting, QA)                       │
    │  • Google Drive API (optional)                     │
    └──────────────────────────────────────────────────────┘
```

---

## 🎯 Главные Хендлеры

### 1️⃣ **КОМАНДЫ** (Commands Handler)

**Регистрируются в:** `transkribator_modules/main.py` (строка ~145)

```python
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("status", status_command))
application.add_handler(CommandHandler("backlog", backlog_command))
application.add_handler(CommandHandler("plans", plans_command))
application.add_handler(CommandHandler("stats", stats_command))
```

**Поддерживаемые команды:**

| Команда | Функция | Результат |
|---------|---------|-----------|
| `/start` | Инициализирует пользователя | Показывает главное меню (WAI) |
| `/help` | Справка | Информация об использовании |
| `/status` | Проверка статуса | Статус всех компонентов |
| `/backlog` | Управление заметками | Меню обработки заметок |
| `/plans` | Тарифные планы | Показывает план подписки |
| `/stats` | Статистика | Показывает использованные лимиты |
| `/promo` | Промокоды | Применить промокод |

**Где обрабатываются:** `transkribator_modules/bot/commands.py` (581 строка)

---

### 2️⃣ **ГЛАВНОЕ МЕНЮ** (WAI Flow - Main Menu)

**Тип:** Inline кнопки (CallbackQuery)

**Логика:**

```
/start или нажать "Главное меню 🐱"
         ↓
    WAI Menu
         ├─ ⚡️ Подписка → Показать тарифы
         ├─ 🤝 Реферальная программа → Показать реферальную инфу
         ├─ 🔎 Поиск по заметкам → Поиск
         └─ 📚 Помощь → FAQ
```

**Где находится:** `transkribator_modules/wai_flow.py` (300 строк)

**Кнопки главного меню:**

```python
rows = [
    [InlineKeyboardButton("⚡️ Подписка", callback_data="main:subscription")],
    [InlineKeyboardButton("🤝 Реферальная программа", callback_data="main:referral")],
    [InlineKeyboardButton("🔎 Поиск по заметкам", callback_data="main:search")],
    [InlineKeyboardButton("📚 Помощь", callback_data="main:help")],
]
```

---

### 3️⃣ **КНОПКА ГЛАВНОГО МЕНЮ В ЧАТЕ** (Reply Keyboard)

**Тип:** Reply кнопка (видна всегда внизу)

```
┌─────────────────────────┐
│   Главное меню 🐱       │ ← Нажимаемая кнопка
└─────────────────────────┘
```

**Логика:**
- Всегда видна в конце диалога
- Нажатие = отправляет текстовое сообщение "Главное меню 🐱"
- Обрабатывается как обычное сообщение → показывает меню

---

### 4️⃣ **ОБРАБОТКА МЕДИА** (Media Handler)

**Тип:** MessageHandler с фильтрами

**Регистрируется в:** `transkribator_modules/main.py` (строка ~130)

```python
media_core = (
    filters.PHOTO
    | filters.VOICE
    | filters.AUDIO
    | filters.VIDEO
    | filters.Document.ALL
)
media_filters = media_core & ~filters.COMMAND
application.add_handler(MessageHandler(media_filters, handle_message), group=0)
```

**Поддерживаемые типы:**
- 🎥 **Видео:** MP4, AVI, MOV, MKV, WebM, FLV, WMV, M4V, 3GP
- 🎵 **Аудио:** MP3, WAV, FLAC, AAC, OGG, M4A, WMA, OPUS
- 🎤 **Голос:** Telegram voice messages
- 📎 **Документы:** Все форматы файлов
- 🖼️ **Фото:** Автоматически извлекается текст (OCR)
- 🔗 **Ссылки:** YouTube, ВКонтакте

**Где обрабатывается:** `transkribator_modules/bot/handlers.py` (2269 строк)

---

### 5️⃣ **CALLBACK ОБРАБОТЧИК** (Button Clicks)

**Тип:** CallbackQueryHandler

**Регистрируется в:** `transkribator_modules/main.py` (строка ~160)

```python
application.add_handler(CallbackQueryHandler(handle_callback_query))
```

**Где обрабатывается:** `transkribator_modules/bot/callbacks.py` (1266 строк)

**Типы колбеков:**

| Префикс | Действие | Примеры |
|---------|----------|---------|
| `wai:` | WAI Menu | `wai:settings`, `wai:language` |
| `main:` | Главное меню | `main:subscription`, `main:referral` |
| `settings:` | Настройки | `settings:lang_ru`, `settings:format_google` |
| `result:` | Результаты транскрипции | `result:download_text`, `result:ask` |
| `buy_plan_*` | Платежи | `buy_plan_pro_stars`, `buy_plan_pro_yukassa` |

---

## 🔄 ПОЛНЫЙ FLOW ОБРАБОТКИ МЕДИА

### Сценарий: Пользователь отправляет видео

```
1. Пользователь отправляет видео
         ↓
2. MessageHandler перехватывает (handle_message)
         ↓
3. Проверка лимитов пользователя
   ├─ Есть ли лимит?
   ├─ Размер файла < 2GB?
   └─ Длительность < 4 часа?
         ↓ (если OK)
4. Загружаем файл из Telegram
         ↓
5. Если это видео → Извлекаем аудио (FFmpeg)
         ↓
6. Отправляем аудио в очередь (Job Queue)
         ↓
7. Отправляем пользователю:
   "✅ Файл принят! Транскрипция началась…"
         ↓
8. Worker процесс обрабатывает:
   ├─ Отправляет на DeepInfra API (Whisper)
   ├─ Получает сырой текст
   ├─ Форматирует через LLM
   └─ Сохраняет в БД
         ↓
9. Показываем пользователю результат:
   ├─ 📄 Скачать текст
   ├─ 🔎 Задать вопросы (QA)
   └─ 🏠 Главное меню
```

**Временная шкала:**
- Загрузка: 1-5 секунд
- Обработка в очереди: 30 секунд - 5 минут
- Пользователь получает результат через web hook или polling

---

## 📋 ЛОГИКА ПРОВЕРОК И ОГРАНИЧЕНИЙ

### Проверка Лимитов (Check Usage Limit)

**Где:** `transkribator_modules/db/database.py` (UserService)

```python
def check_usage_limit(user) -> tuple[bool, str]:
    """
    Проверяет:
    1. Есть ли активная подписка?
    2. Не превышен ли лимит по минутам?
    3. Не превышено ли количество файлов?
    """
    
    # Бесплатный тариф: 3 видео в месяц
    # Pro: 100 часов в месяц
    # Premium: Безлимит
```

### Проверка Размера Файла

```python
MAX_FILE_SIZE_MB = 2048  # 2GB

if file_size_mb > MAX_FILE_SIZE_MB:
    return "❌ Файл слишком большой"
```

### Проверка Длительности

```python
MAX_DURATION_MINUTES = 240  # 4 часа

if duration_minutes > MAX_DURATION_MINUTES:
    return "❌ Аудио слишком длинное"
```

---

## 🔌 CALLBACK HANDLER ЛОГИКА

**Функция:** `handle_callback_query` в `callbacks.py`

**Алгоритм:**

```python
async def handle_callback_query(update, context):
    query = update.callback_query
    await query.answer()  # Убираем "часики" на кнопке
    
    data = query.data  # Например: "main:subscription"
    
    if data.startswith("wai:"):
        # Обработка меню
        await wai_handle_callback(update, context)
    
    elif data.startswith("main:"):
        # Обработка главного меню
        if data == "main:subscription":
            await show_payment_plans(update, context)
        elif data == "main:referral":
            await show_referral_info(update, context)
    
    elif data.startswith("result:"):
        # Обработка кнопок результатов
        if data == "result:download_text":
            await download_transcription_text(update, context)
        elif data == "result:ask":
            await start_qa_session(update, context)
    
    elif data.startswith("buy_plan_"):
        # Обработка платежей
        await initiate_payment(update, context, plan_id)
```

---

## 📤 РЕЗУЛЬТАТЫ ТРАНСКРИПЦИИ - Меню

После завершения обработки пользователю показывается меню:

```
✅ Обработка завершена!

📝 [Краткое содержание - 1-2 предложения]

🔗 Оригинал: [ссылка на видео, если была]

Выберите действие:
┌──────────────────────────┐
│ 📄 Скачать текст         │ → result:download_text
├──────────────────────────┤
│ 🔎 Задать вопросы        │ → result:ask
├──────────────────────────┤
│ 🏠 Главное меню          │ → main:menu
└──────────────────────────┘
```

**После нажатия кнопок:**

### `result:download_text`
```python
async def download_transcription_text(update, context):
    # Читает из media/transcriptions/
    # Отправляет пользователю текстовый файл
    # Формат: .txt с таймкодами
```

### `result:ask`
```python
async def start_qa_session(update, context):
    # Сохраняет транскрипт в context
    # Ждет вопроса от пользователя
    # На каждый вопрос отправляет в LLM:
    #   - Транскрипт
    #   - История предыдущих Q&A
    #   - Вопрос пользователя
    # Получает ответ и отправляет
```

---

## 🎛️ НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ (WAI Settings)

**Где сохраняются:** В `context.user_data` (в памяти бота)

```python
state = {
    "settings": {
        "lang": "ru",           # Язык интерфейса (ru/en)
        "format": "Google Docs", # Формат текста
        "model": "ChatGPT-4o",  # LLM модель
        "input_lang": "auto",   # Язык аудио (auto/ru/en)
    }
}
```

**Как это работает:**
1. Пользователь нажимает "Настройки" в меню WAI
2. Показываются inline кнопки для каждой настройки
3. Выбор сохраняется в `context.user_data`
4. Используется при следующей обработке медиа

---

## 💳 СИСТЕМА ПЛАТЕЖЕЙ

**Платежные системы:**
1. **Telegram Stars** - встроенный платеж в Telegram
2. **YuKassa** - российская платежная система
3. **Legacy** - старая система (если была)

**Flow:**

```
Пользователь нажимает "⚡️ Подписка"
         ↓
Показываются тарифы:
├─ Free: 3 видео/месяц
├─ Pro: 100 часов/месяц
└─ Premium: Безлимит
         ↓
Пользователь выбирает "buy_plan_pro_stars"
         ↓
initiate_payment(update, context, "pro", "stars")
         ↓
Telegram встроенный платежный форм
         ↓
Успешная оплата
         ↓
Обновляем БД: добавляем дни подписки
         ↓
Уведомляем пользователя ✅
```

---

## 📊 ГЛАВНЫЕ КОМПОНЕНТЫ

### 1. **handle_message** (handlers.py, линия 1000+)

**Что делает:**
- Определяет тип медиа
- Проверяет лимиты
- Скачивает файл из Telegram
- Отправляет в очередь обработки

```python
async def handle_message(update, context):
    if is_video(update.message):
        await process_video_file(update, context, ...)
    elif is_audio(update.message):
        await process_audio_file(update, context, ...)
    elif is_youtube_link(update.message):
        await process_youtube(update, context, ...)
```

### 2. **Job Queue Worker** (job_worker.py)

**Что делает:**
- Берет файлы из очереди
- Отправляет на DeepInfra API
- Форматирует текст через LLM
- Сохраняет результаты

### 3. **WAI Flow** (wai_flow.py)

**Что делает:**
- Показывает главное меню
- Управляет настройками
- Показывает информацию о подписке

### 4. **Callbacks** (callbacks.py)

**Что делает:**
- Обрабатывает все нажатия кнопок
- Переходит между экранами меню
- Обрабатывает платежи

---

## 🚀 КЛЮЧЕВЫЕ МОМЕНТЫ

### ❌ Команды НЕ нужны для бота
- Бот работает в основном через кнопки (Inline)
- Команды - это только для справки
- Главное управление через меню и кнопки

### ❌ API вызовы идут в WORKER, не в боте
- Бот только скачивает файл
- Бот отправляет в очередь
- WORKER обрабатывает в фоне
- WORKER вызывает DeepInfra, LLM и т.д.

### ✅ Боту нужно только:
- Получить медиа
- Проверить лимиты
- Отправить в очередь
- Показать статус

### ✅ Асинхронная обработка:
- Пользователь отправляет файл
- Сразу видит: "✅ Принято! Обработка началась"
- Продолжает писать сообщения
- Результат придет через несколько минут (webhook callback)

---

## 📚 Главные файлы для понимания

| Файл | Строк | Задача |
|------|-------|--------|
| **handlers.py** | 2269 | Основная логика обработки медиа |
| **callbacks.py** | 1266 | Обработка всех нажатий кнопок |
| **commands.py** | 581 | Команды (/start, /help и т.д.) |
| **wai_flow.py** | 300 | Главное меню и настройки |
| **main.py** | 172 | Регистрация всех хендлеров |
| **job_worker.py** | - | Фоновая обработка (DeepInfra API) |

---

## 🎯 ИТОГО: ЧТО ДЕЛАЕТ БОТ

1. **Получает медиа** - видео, аудио, ссылки
2. **Проверяет лимиты** - подписка, размер, длительность
3. **Скачивает файл** - из Telegram серверов
4. **Отправляет в очередь** - асинхронная обработка
5. **Показывает статус** - "Обработка началась"
6. **Принимает результат** - от worker процесса
7. **Показывает меню** - скачать, задать вопросы, меню
8. **QA сессия** - вопросы по транскрипту
9. **Платежи** - Stars, YuKassa
10. **Реферальная система** - приглашение друзей

**Всё через кнопки, меню и асинхронные callback'и!** 🚀

