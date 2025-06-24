# Настройка Google Docs API для CyberKitty Transkribator

## 🎯 Зачем нужно?

Google Docs интеграция позволяет:
- 📄 Создавать красиво оформленные документы с транскрипциями
- 🔗 Делиться постоянными ссылками вместо файлов  
- 💾 Автоматически сохранять результаты в облаке
- 🎨 Красиво оформлять длинные транскрипции

## 🚀 Быстрая настройка

### Шаг 1: Создание Google Cloud проекта

1. Перейди в [Google Cloud Console](https://console.cloud.google.com/)
2. Создай новый проект или выбери существующий
3. В названии проекта укажи что-то вроде "cyberkitty-transkribator"

### Шаг 2: Включение API

1. Перейди в раздел "API и сервисы" → "Библиотека"
2. Найди и включи:
   - **Google Docs API**
   - **Google Drive API**

### Шаг 3: Создание Service Account

1. Перейди в "API и сервисы" → "Учетные данные"
2. Нажми "Создать учетные данные" → "Сервисный аккаунт"
3. Укажи имя: `cyberkitty-docs-service`
4. Роль: **Редактор** (Editor)

### Шаг 4: Генерация ключа

1. Найди созданный сервисный аккаунт
2. Нажми "Действия" → "Управление ключами"
3. "Добавить ключ" → "Создать новый ключ"
4. Формат: **JSON**
5. Скачай файл (например: `cyberkitty-credentials.json`)

### Шаг 5: Установка в проект

```bash
# Скопируй credentials файл в проект
cp cyberkitty-credentials.json /var/www/cyberkitty19-transkribator/data/google_credentials.json

# Установи переменную окружения (опционально)
export GOOGLE_CREDENTIALS_PATH="/var/www/cyberkitty19-transkribator/data/google_credentials.json"
```

### Шаг 6: Для Docker

Добавь в `docker-compose.yml`:

```yaml
volumes:
  - ./data/google_credentials.json:/app/data/google_credentials.json:ro
```

## 🔧 Проверка работы

После настройки перезапусти бота:

```bash
docker restart cyberkitty19-transkribator-bot
```

В логах должно появиться:
```
✅ Google Docs API инициализирован
```

## ⚠️ Важные моменты

1. **Безопасность**: Никогда не коммитьте credentials файл в git!
2. **Права**: Service Account автоматически создает документы
3. **Лимиты**: Google API имеет лимиты на количество запросов
4. **Fallback**: Если API недоступен, бот отправит файл как обычно

## 🚫 Что делать если нет Google API?

Без настройки Google API бот будет:
- ✅ Отправлять короткие транскрипции в чате
- 📎 Отправлять длинные транскрипции файлами
- 🔄 Работать как обычно, просто без Google Docs

## 🆓 Бесплатные лимиты Google API

- **Google Docs API**: 100 запросов/минуту
- **Google Drive API**: 1000 запросов/день  
- Для небольшого бота - более чем достаточно!

## 🐛 Устранение проблем

### Ошибка: "Google credentials не найдены"
- Проверь путь к файлу credentials
- Убедись что файл существует и читаемый

### Ошибка: "403 Forbidden"  
- Проверь что API включены в Google Cloud Console
- Убедись что у Service Account есть нужные права

### Ошибка: "Invalid credentials"
- Пересоздай ключ Service Account
- Проверь что файл JSON не поврежден 