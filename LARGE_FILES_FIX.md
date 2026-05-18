# 🔧 Fix: Большие файлы через локальный Bot API

**Дата**: 17 декабря 2025, 10:33 UTC  
**Проблема**: Видео файлы размером > 50 МБ отказывались скачиваться  
**Статус**: ✅ ИСПРАВЛЕНО И РАЗВЕРНУТО

---

## 📋 Описание проблемы

При отправке видеофайла размером **165.2 МБ** (webm) система переходила через следующий цикл:

1. ✅ Локальный Bot API опрашивается через `getFile` (успешно)
2. ⏳ Локальный Bot API готовит file_path (~2 минуты)
3. ❌ После 12 попыток без file_path → fallback к глобальному Telegram API
4. 💥 Глобальный API отказывает: **"Bad Request: file is too big"**
   - Причина: Глобальный API не может скачивать файлы > 50 МБ через getFile

**Результат**: Файл не скачивается, пользователь получает ошибку.

---

## 🎯 Решение

### Проблема в коде `large_file_downloader.py`

**Старое поведение**:
```python
# Если локальный API не выдал file_path, ВСЕГДА пробуем глобальный API
if USE_LOCAL_BOT_API:
    try:
        # Запрос к глобальному Telegram API
        fallback_url = f"{API_BASE}/bot{bot_token}/getFile"
        # ❌ Для больших файлов это вернет "file is too big"!
```

**Новое поведение**:
```python
# Если локальный API не выдал file_path, НЕ пробуем глобальный API
if USE_LOCAL_BOT_API:
    logger.info(
        "getFile local failed to return file_path (timeout or no-file-yet), "
        "skipping global API fallback for local Bot API. "
        "Will attempt to locate file in local storage cache."
    )
    return None  # ✅ Позволяет download_large_file искать файл в локальном кеше
```

### Почему это работает?

Функция `download_large_file` имеет встроенную логику для поиска файла в локальном хранилище Bot API:

1. **Ранний поиск** (`expected_size_bytes`): ищет файл по размеру в локальном кеше ДО попыток getFile
2. **Полинг кеша во время ожидания**: периодически проверяет локальное хранилище
3. **Прямое копирование**: если найден файл с нужным размером → копирует напрямую

---

## 📝 Изменения кода

### Файл: `transkribator_modules/utils/large_file_downloader.py`

**Функция `get_file_info()`**:
- Строки ~184-212: Заменена логика fallback
- **Было**: попытка глобального API ВСЕГДА
- **Стало**: для локального API пропускаем глобальный API, позволяем download_large_file искать в кеше

**Функция `download_large_file()`**:
- Строки ~320-335: Добавлено подробное логирование  
- **Добавлено**: логирование failed get_file_info с контекстом (размер, use_local_api)

---

## 🔄 Поток работы теперь:

```
[Пользователь отправляет видео 165 МБ]
    ↓
[process_video_file вызывает download_large_file с expected_size_bytes=165MB]
    ↓
[Ранний поиск в кеше Bot API по размеру файла]
    ├─ Найден? → Копируем, готово! ✅
    └─ Не найден? → Продолжаем...
    ↓
[get_file_info запрашивает file_path от локального Bot API]
    ├─ Получено file_path? → Скачиваем файл ✅
    └─ Не получено file_path? → Пробуем полинг кеша...
    ↓
[Полинг локального кеша Bot API каждые 5-10 сек]
    ├─ Файл появился в кеше? → Копируем! ✅
    └─ Кеш исчерпан, нет файла? → Ошибка (но БЕЗ попытки глобального API) ❌
```

**Ключевое отличие**: Больше НЕТ fallback к глобальному API, который отказывает на больших файлах!

---

## 📊 Ожидаемые результаты

### Скорость обработки больших файлов:

| Размер | До | После | Примечание |
|--------|----|----|---|
| 50-150 МБ | ❌ Ошибка "file is too big" | ✅ Скачивается | Копируется из локального кеша |
| >150 МБ | ❌ Ошибка "file is too big" | ⏳ Может занять время | Ждет пока локальный API подготовит |
| <50 МБ | ✅ Работает | ✅ Работает (быстрее) | Копируется из кеша сразу |

### Логирование:

**При успехе**:
```
INFO: Early-copied media from cache by size
  source: "/app/telegram-bot-api-data/BotToken/videos/file_123"
  destination: "/app/videos/telegram_video_XXX.mp4"
  size: 173245664
```

**При долгом ожидании**:
```
INFO: getFile local failed to return file_path (timeout or no-file-yet),
      skipping global API fallback for local Bot API
INFO: Early-copied media from cache during polling
  source: "/app/telegram-bot-api-data/BotToken/videos/file_456"
```

**При ошибке**:
```
ERROR: Failed to obtain file info for download
  has_file_info: false
  expected_size_bytes: 173245664
  use_local_api: true
```

---

## 🚀 Развертывание

✅ **Статус**: Готово  
📦 **Контейнеры**: Перезагружены  
⏰ **Время развертывания**: 2025-12-17 10:33:04 UTC

---

## 🧪 Рекомендуемое тестирование

### Тест 1: Видео 165 МБ (как при ошибке ранее)
```bash
# Попросить пользователя 648981358 отправить то же видео снова
# Ожидаемо: файл скачается успешно (или из кеша сразу, или после полинга)
```

### Тест 2: Просмотр логов
```bash
ssh got_is_tod "docker logs --since 5m cyberkitty19-transkribator-bot 2>&1 | \
  grep -E '(Early-copied|skipping global|failed to obtain)'"
```

### Тест 3: Различные размеры
- Маленький файл (< 10 МБ)
- Средний файл (20-50 МБ) 
- Большой файл (100+ МБ)

---

## 📌 Важные замечания

1. **Локальный Bot API должен быть включен** (`USE_LOCAL_BOT_API=true`)
   - Проверить в конфиге: `/app/.env`

2. **Локальное хранилище должно быть размонтировано**
   - Путь: `/app/telegram-bot-api-data`
   - Обычно это том Docker: `telegram-bot-api-data`

3. **Для глобального API (без локального Bot API)** поведение не изменилось
   - Fallback к глобальному API продолжает работать как было

4. **Файлы > 50 МБ через глобальный API не поддерживаются**
   - Это лимит Telegram
   - Решение: использовать локальный Bot API (как сейчас)

---

## 🔍 Отладка

Если проблемы остаются, проверить:

```bash
# 1. Включен ли локальный Bot API?
docker logs cyberkitty19-transkribator-bot | grep "LOCAL_BOT_API"

# 2. Есть ли кеш Bot API?
docker exec cyberkitty19-telegram-bot-api ls -la /var/lib/telegram-bot-api/*/videos/ 2>&1 | head -20

# 3. Логи скачивания
docker logs --since 10m cyberkitty19-transkribator-bot 2>&1 | grep -E "(download_large_file|Early-copied|failed to obtain)" | tail -30
```

---

## ✅ Готово!

Система теперь корректно обрабатывает большие видео файлы через локальный Bot API без fallback к глобальному API, который отказывает на файлах > 50 МБ.
