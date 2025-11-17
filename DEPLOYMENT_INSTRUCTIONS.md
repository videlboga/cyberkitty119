# 🚀 Инструкция по деплою логирования событий

**Дата:** 1 ноября 2025  
**Версия:** Full Logging Coverage v1.1 (с beta callbacks)  
**Покрытие:** 57 событий (~86%)

---

## 📦 Файлы для деплоя

### Изменённые файлы (6 шт):
1. `transkribator_modules/bot/commands.py` (24K) - добавлено 9 событий
2. `transkribator_modules/bot/handlers.py` (81K) - добавлено 15 событий
3. `transkribator_modules/bot/callbacks.py` (51K) - добавлено 26 событий
4. `transkribator_modules/bot/payments.py` (22K) - добавлено 4 события
5. `transkribator_modules/beta/handlers/entrypoint.py` (31K) - добавлено 2 события ✨ NEW
6. `transkribator_modules/events_registry.py` (9.3K) - добавлены все названия событий

---

## 🌐 Новые переменные окружения

| Имя | Назначение | Пример |
| --- | --- | --- |
| `YTDLP_PROXY` | Необязательный HTTP/SOCKS-прокси для загрузки YouTube-видео через `yt_dlp`. Используется, если прямой доступ блокируется. | `socks5://login:password@proxy.example.com:1080` |

> Переменная считывается на старте бота. После изменения перезапустите сервис, чтобы опция вступила в силу.

---

## 🔧 Шаги деплоя

### 1. Подготовка (локально)
```bash
# Создать бэкап текущих файлов на сервере
ssh user@server "cd /path/to/app && \
  tar -czf backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  transkribator_modules/bot/commands.py \
  transkribator_modules/bot/handlers.py \
  transkribator_modules/bot/callbacks.py \
  transkribator_modules/bot/payments.py \
  transkribator_modules/beta/handlers/entrypoint.py \
  transkribator_modules/events_registry.py"
```

### 2. Загрузка файлов на сервер
```bash
# Вариант A: Через rsync (рекомендуется)
rsync -avz --progress \
  transkribator_modules/bot/commands.py \
  transkribator_modules/bot/handlers.py \
  transkribator_modules/bot/callbacks.py \
  transkribator_modules/bot/payments.py \
  transkribator_modules/beta/handlers/entrypoint.py \
  transkribator_modules/events_registry.py \
  user@server:/path/to/app/transkribator_modules/

# Вариант B: Через scp
scp logging_deployment_*.tar.gz user@server:/tmp/
ssh user@server "cd /path/to/app && tar -xzf /tmp/logging_deployment_*.tar.gz"

# Вариант C: Через git (если есть репозиторий)
git add transkribator_modules/bot/*.py \
        transkribator_modules/beta/handlers/entrypoint.py \
        transkribator_modules/events_registry.py
git commit -m "feat: добавлено полное логирование событий (86% покрытие, +40 событий)"
git push origin main
ssh user@server "cd /path/to/app && git pull origin main"
```

### 3. Проверка файлов на сервере
```bash
ssh user@server "cd /path/to/app && \
  python3 -m py_compile \
    transkribator_modules/bot/commands.py \
    transkribator_modules/bot/handlers.py \
    transkribator_modules/bot/callbacks.py \
    transkribator_modules/bot/payments.py \
    transkribator_modules/beta/handlers/entrypoint.py \
    transkribator_modules/events_registry.py && \
  echo '✅ Все файлы скомпилированы успешно'"
```

### 4. Подсчёт событий (верификация)
```bash
ssh user@server "cd /path/to/app && \
  grep -c 'log_event' transkribator_modules/bot/commands.py \
                      transkribator_modules/bot/handlers.py \
                      transkribator_modules/bot/callbacks.py \
                      transkribator_modules/bot/payments.py \
                      transkribator_modules/beta/handlers/entrypoint.py"
```

**Ожидаемый результат:**
```
commands.py:9
handlers.py:15
callbacks.py:26
payments.py:4
entrypoint.py:3
```

### 5. Перезапуск бота
```bash
# Остановить бота
ssh user@server "systemctl stop transkribator-bot"
# или
ssh user@server "supervisorctl stop transkribator-bot"
# или
ssh user@server "pkill -f api_server.py && pkill -f job_worker.py"

# Подождать 5 секунд
sleep 5

# Запустить бота
ssh user@server "systemctl start transkribator-bot"
# или
ssh user@server "supervisorctl start transkribator-bot"
# или
ssh user@server "cd /path/to/app && \
  nohup python3 api_server.py > logs/api_server.log 2>&1 & \
  nohup python3 job_worker.py > logs/job_worker.log 2>&1 &"
```

### 6. Проверка работы
```bash
# Проверить, что бот запустился
ssh user@server "ps aux | grep -E 'api_server|job_worker|python.*bot'"

# Проверить логи
ssh user@server "tail -f /path/to/app/logs/bot.log"
# Ожидаем увидеть: "Получен колбек:", "log_event", "Failed to log" и т.д.

# Проверить БД (последние события)
ssh user@server "cd /path/to/app && python3 -c \"
from transkribator_modules.db.database import SessionLocal
db = SessionLocal()
from sqlalchemy import text
result = db.execute(text('SELECT event_kind, COUNT(*) FROM events GROUP BY event_kind ORDER BY COUNT(*) DESC LIMIT 10'))
for row in result:
    print(f'{row[0]}: {row[1]}')
db.close()
\""
```

---

## ✅ Checklist деплоя

- [ ] 1. Создан бэкап старых файлов на сервере
- [ ] 2. Файлы загружены на сервер
- [ ] 3. Проверена компиляция Python файлов
- [ ] 4. Проверено количество log_event (57 ожидается)
- [ ] 5. Бот перезапущен
- [ ] 6. Бот успешно стартовал (проверены процессы)
- [ ] 7. Проверены логи (нет критических ошибок)
- [ ] 8. Тестовая команда `/start` отработала
- [ ] 9. Проверена запись событий в БД
- [ ] 10. Проверен dashboard `/events-dashboard`

---

## 🧪 Тестирование после деплоя

### Быстрые тесты (5 минут):
1. **Команды:**
   - `/start` → должно залогировать `bot_command_start`
   - `/help` → `bot_command_help`
   - `/stats` → `bot_command_stats`

2. **Кнопки:**
   - Нажать "💎 Тарифы" → `bot_button_show_payment_plans`
   - Нажать "🏠 Личный кабинет" → `bot_button_personal_cabinet`

3. **Медиа:**
   - Отправить голосовое сообщение → `bot_media_voice_received`
   - Отправить YouTube ссылку → `bot_media_youtube_link`

4. **Платежи:**
   - Начать покупку плана → `payment_pre_checkout`

5. **Beta (NEW):**
   - Отправить текст в beta-режиме → `bot_beta_note_confirm` или `bot_beta_note_decline`

### Проверка dashboard:
1. Открыть `https://your-domain.com/events-dashboard`
2. Выбрать "Последние 24 часа"
3. Убедиться, что видны новые события

---

## 🔄 Откат (если что-то пошло не так)

```bash
# Восстановить из бэкапа
ssh user@server "cd /path/to/app && \
  tar -xzf backup_YYYYMMDD_HHMMSS.tar.gz && \
  systemctl restart transkribator-bot"
```

---

## 📊 Что изменилось

### До деплоя:
- 17 событий (34% покрытие)
- Только базовые действия
- Нет payment tracking
- Нет beta callbacks

### После деплоя:
- **57 событий (86% покрытие)** ✨
- Все команды (9)
- Все типы сообщений (15)
- Все кнопки (26)
- Полный payment flow (4)
- Beta callbacks (2) ✨ NEW
- Agent actions (2)

---

## 📈 Новые возможности аналитики

После деплоя можно отслеживать:

1. **Payment Funnel:**
   - Просмотр тарифов → Клик "Купить" → Pre-checkout → Success
   - Конверсия по каждому этапу

2. **User Journey:**
   - От `/start` до первой покупки
   - Какие команды используются чаще
   - Какие кнопки не нажимаются (кандидаты на удаление)

3. **Content Processing:**
   - Соотношение audio/video/voice/text
   - YouTube vs VK ссылки
   - Успешность транскрипции

4. **Beta Adoption (NEW):**
   - Сколько создают заметки через агент
   - Конверсия: показ → подтверждение
   - Качество распознавания намерений

5. **Agent Usage:**
   - Save raw vs backlog
   - Активность в beta-режиме

---

## 🆘 Контакты поддержки

- Логи: `/path/to/app/logs/bot.log`
- БД: PostgreSQL на сервере
- Dashboard: `https://your-domain.com/events-dashboard`
- Документация: `/docs/admin_dashboard.md`

---

## 📝 Примечания

- Все логирование обёрнуто в `try/except` — падения бота не будет
- События пишутся асинхронно — не влияют на производительность
- Dashboard обновляется каждые 30 секунд автоматически
- Можно фильтровать по времени, категории, пользователю

**Удачного деплоя! 🚀**
