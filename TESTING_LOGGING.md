# 🧪 Инструкция по тестированию логирования

## Статус развертывания: ✅ УСПЕШНО (2025-12-17 10:12:54 UTC)

Контейнеры перезагружены:
- cyberkitty19-transkribator-bot
- cyberkitty19-transkribator-api

Модуль extractor успешно загружен ✅

---

## Как протестировать

### Шаг 1: Запросить пользователя отправить видео

Текст для пользователя 376134276 (bimboru):

```
Привет! 👋 

Мы обновили систему логирования обработки видео. 
Можешь ещё раз отправить то webm видео, которое не обработалось раньше?

Теперь мы сможем увидеть ТОЧНО, почему это произошло.
```

### Шаг 2: Отследить логи в реальном времени

```bash
# Подключиться к серверу
ssh got_is_tod

# Просмотреть логи бота в реальном времени
docker logs -f cyberkitty19-transkribator-bot 2>&1 | grep -E "(376134276|Audio extraction|ffprobe|Получен видео|Извлечение аудио|Удален|ERROR)" &

# Или для API
docker logs -f cyberkitty19-transkribator-api 2>&1 | grep -E "(376134276|Audio extraction|ffprobe|Получен видео|Извлечение аудио|Удален|ERROR)" &

# Нажать Ctrl+C чтобы остановить
```

### Шаг 3: Анализировать результаты

#### Сценарий 1: Видео без аудио
```
WARNING: Видео не содержит аудио потока
  probe_stdout: ""
  probe_stderr: "[stderr ffprobe]"
```

**Действие**: Попросить пользователя конвертировать в mp4 с аудио.

#### Сценарий 2: Несовместимый кодек
```
ERROR: Ошибка при извлечении аудио ffmpeg
  return_code: 1
  stderr: "[детали ошибки ffmpeg]"
```

**Действие**: Проанализировать stderr и обновить поддержку кодека.

#### Сценарий 3: Проблема с памятью
```
ERROR: Ошибка при извлечении аудио
  error: "No space left on device"
  error_type: "OSError"
```

**Действие**: Освободить место на диске.

#### Сценарий 4: Успешное извлечение
```
INFO: Аудио успешно извлечено
  audio: "/app/audio/telegram_audio_XXXXX.wav"
  size_mb: 245.3
  original_video_mb: 173.2

INFO: Удален видео-файл: /app/videos/telegram_video_XXXXX.mp4
INFO: Удален аудио-файл: /app/audio/telegram_audio_XXXXX.wav
```

**Результат**: ✅ Видео успешно обработано!

---

## Поиск конкретного события

### По пользователю
```bash
ssh got_is_tod "docker logs --since 1h cyberkitty19-transkribator-bot 2>&1 | grep 376134276"
```

### По ошибке аудио
```bash
ssh got_is_tod "docker logs --since 1h cyberkitty19-transkribator-bot 2>&1 | grep 'Audio extraction failed' -A5"
```

### По ffmpeg ошибкам
```bash
ssh got_is_tod "docker logs --since 1h cyberkitty19-transkribator-bot 2>&1 | grep 'ffmpeg' -A3"
```

### По удаленным файлам
```bash
ssh got_is_tod "docker logs --since 1h cyberkitty19-transkribator-bot 2>&1 | grep 'Удален' "
```

---

## Примеры команд для отладки на продакшене

```bash
# 1. Проверить, что файл действительно загружается
ssh got_is_tod "docker exec cyberkitty19-transkribator-api ls -lah /app/videos/ | head -20"

# 2. Проверить логи последних 5 минут
ssh got_is_tod "docker logs --since 5m cyberkitty19-transkribator-bot 2>&1 | tail -100"

# 3. Получить полный лог последней обработки видео
ssh got_is_tod "docker logs cyberkitty19-transkribator-bot 2>&1 | grep -B20 'Удален видео-файл' | tail -50"

# 4. Проверить ffmpeg версию и доступные кодеки
ssh got_is_tod "docker exec cyberkitty19-transkribator-api ffmpeg -codecs 2>&1 | grep -E 'vp8|vp9|opus|h264'"

# 5. Проверить ffprobe на конкретном файле (если он есть)
ssh got_is_tod "docker exec cyberkitty19-transkribator-api ffprobe /app/videos/telegram_video_BQACAgIA.mp4 2>&1 | grep Duration"
```

---

## Важные замечания

⚠️ **SUPPRESS_FAILURE_MESSAGES все еще ВКЛЮЧЕН**
- Пользователь НЕ увидит детали ошибки (это по дизайну)
- Но вся информация есть в логах для администраторов
- Если нужно отключить: установить `SUPPRESS_FAILURE_MESSAGES=false` в .env

📋 **Логи содержат:**
- Имя файла и размер
- MIME type
- Результаты ffprobe (есть ли аудио)
- Детали ошибок ffmpeg (stderr)
- Время жизни файла

✅ **Все изменения готовы к использованию**
- Модули загружены
- Синтаксис проверен
- Контейнеры перезагружены
- Система запущена

---

## Контактная информация

При возникновении проблем:
1. Проверить логи по инструкции выше
2. Сохранить релевантные отрывки логов
3. Сообщить о проблеме с указанием timestamp и user_id
