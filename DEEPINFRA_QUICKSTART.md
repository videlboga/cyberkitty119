# 🚀 DeepInfra Adapter - QUICK START

## За 5 минут до использования

### 1️⃣ Установить зависимости (1 мин)

```bash
# Убедитесь что ffmpeg установлен
ffmpeg -version

# Установить Python зависимости
pip install requests openai-whisper
```

### 2️⃣ Настроить API ключ (1 мин)

```bash
# Вариант 1: Export переменную окружения
export DEEPINFRA_API_KEY="sk-..."

# Вариант 2: Добавить в .env файл
echo "DEEPINFRA_API_KEY=sk-..." >> .env
source .env

# Вариант 3: Передать при инициализации
adapter = DeepInfraAdapter(api_key="sk-...")
```

### 3️⃣ Использовать в коде (1 мин)

```python
from transcribe_client.deepinfra import DeepInfraAdapter

# Инициализация
adapter = DeepInfraAdapter()

# Транскрибирование одного файла
result = adapter.transcribe('/path/to/audio.mp3')
print(result['text'])

# Информация о провайдере
print(f"Провайдер: {result['meta']['provider']}")
```

### 4️⃣ Протестировать (2 мин)

```bash
# Запустить тест suite
python3 test_deepinfra_adapter.py

# Ожидаемый результат:
# ✅ ALL TESTS PASSED - Ready for production!
```

---

## 💻 Примеры кода

### Пример 1: Базовое использование

```python
from transcribe_client.deepinfra import DeepInfraAdapter
import json

adapter = DeepInfraAdapter()

# Транскрибировать
result = adapter.transcribe('audio.mp3')

# Вывести результат
print("Текст:", result['text'])
print("Провайдер:", result['meta']['provider'])
print("Сегментов:", len(result['segments']))
```

### Пример 2: Обработка ошибок

```python
from transcribe_client.deepinfra import DeepInfraAdapter

adapter = DeepInfraAdapter()

try:
    result = adapter.transcribe('audio.mp3')
    print("✅ Успешно:")
    print(f"  - Текст: {result['text'][:100]}...")
    print(f"  - Провайдер: {result['meta']['provider']}")
except FileNotFoundError:
    print("❌ Файл не найден")
except RuntimeError as e:
    print(f"❌ Ошибка: {e}")
```

### Пример 3: Обработка сегментов

```python
from transcribe_client.deepinfra import DeepInfraAdapter

adapter = DeepInfraAdapter()
result = adapter.transcribe('audio.mp3')

# Итерировать сегменты
for segment in result['segments']:
    start = segment['start']
    end = segment['end']
    text = segment['text']
    print(f"[{start:.1f}s - {end:.1f}s] {text}")
```

### Пример 4: Отслеживание провайдера

```python
from transcribe_client.deepinfra import DeepInfraAdapter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

adapter = DeepInfraAdapter()
result = adapter.transcribe('audio.mp3')

provider = result['meta']['provider']
if provider == 'deepinfra':
    logger.info("✅ Использован DeepInfra API")
elif provider == 'local_whisper':
    logger.warning("⚠️  Использован local Whisper (fallback)")
```

### Пример 5: Пакетная обработка

```python
from pathlib import Path
from transcribe_client.deepinfra import DeepInfraAdapter

adapter = DeepInfraAdapter()
audio_dir = Path('/path/to/audio/files')

results = {}
for audio_file in audio_dir.glob('*.mp3'):
    print(f"Обработка {audio_file.name}...")
    result = adapter.transcribe(str(audio_file))
    results[audio_file.name] = {
        'text': result['text'],
        'provider': result['meta']['provider'],
        'segments': len(result['segments'])
    }

# Вывести результаты
for filename, data in results.items():
    print(f"{filename}: {data['text'][:50]}...")
```

---

## ⚙️ Переменные окружения

| Переменная | По умолчанию | Описание |
|-----------|--------------|---------|
| `DEEPINFRA_API_KEY` | ❌ обязательна | API ключ от DeepInfra |
| `DEEPINFRA_TASK` | `transcribe` | Задача (transcribe/translate) |
| `DEEPINFRA_TEMPERATURE` | `0` | Детерминизм (0-1) |
| `DEEPINFRA_LANGUAGE` | `ru` | Язык аудио |
| `DEEPINFRA_REQUEST_TIMEOUT_SEC` | `1800` | Timeout в секундах |

Пример `.env`:
```bash
DEEPINFRA_API_KEY=sk-abcd1234
DEEPINFRA_TASK=transcribe
DEEPINFRA_TEMPERATURE=0
DEEPINFRA_LANGUAGE=ru
DEEPINFRA_REQUEST_TIMEOUT_SEC=1800
```

---

## 🔍 Отладка

### DeepInfra работает?

```bash
# Проверить API доступность
curl -I -X GET 'https://api.deepinfra.com/v1/models' \
  -H "Authorization: Bearer $DEEPINFRA_API_KEY"
```

Ожидаемый результат:
```
HTTP/2 200
```

### Проверить логи

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Теперь будут видны все логи адаптера
```

### Проблема: ffmpeg не найден

```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# Arch
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

### Проблема: whisper не установлен

```bash
pip install openai-whisper
```

### Проблема: API ключ неверный

```
RuntimeError: DEEPINFRA_API_KEY is required for DeepInfraAdapter
```

Решение:
```bash
export DEEPINFRA_API_KEY="sk-..." # вставить реальный ключ
```

---

## 📊 Что ожидать

### Первый вызов (первая загрузка модели)
```
[*] Loading local Whisper model (size=base)...
⏱️  13 секунд загрузки

[*] Transcribing audio.mp3 with local Whisper...
⏱️  ~3 секунды на 60 сек аудио
```

### Последующие вызовы
```
[*] Transcribing audio.mp3 with local Whisper...
⏱️  ~3 секунды на 60 сек аудио (модель уже в памяти)
```

### Если DeepInfra работает
```
✅ SUCCESS
   Provider: deepinfra
   Time: 2-3s
```

---

## 🎯 Типичные использования

### 1. В Telegram боте
```python
@bot.message_handler(content_types=['voice', 'audio'])
def handle_audio(message):
    adapter = DeepInfraAdapter()
    result = adapter.transcribe(audio_file)
    bot.send_message(message.chat.id, result['text'])
```

### 2. В REST API
```python
from flask import Flask, request, jsonify
from transcribe_client.deepinfra import DeepInfraAdapter

app = Flask(__name__)
adapter = DeepInfraAdapter()

@app.post('/transcribe')
def transcribe():
    audio_file = request.files['audio']
    audio_file.save('temp.mp3')
    result = adapter.transcribe('temp.mp3')
    return jsonify(result)
```

### 3. В CLI утилите
```python
import sys
from transcribe_client.deepinfra import DeepInfraAdapter

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python transcribe.py <audio_file>")
        sys.exit(1)
    
    adapter = DeepInfraAdapter()
    result = adapter.transcribe(sys.argv[1])
    print(result['text'])
```

---

## 📞 Поддержка

### Когда DeepInfra недоступна
✅ **Не паникуйте!** - автоматически переключится на local Whisper

### Если проблема остается
1. Проверить логи: `DEEPINFRA_API_KEY` установлена?
2. Проверить интернет: `curl https://api.deepinfra.com/v1/models`
3. Проверить ffmpeg: `ffmpeg -version`
4. Читать: `DEEPINFRA_FINAL_REPORT.md`

---

**🎉 Вы готовы! Начните использовать DeepInfra адаптер прямо сейчас!**
