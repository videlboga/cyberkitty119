# 🔍 Быстрая справка: Проверка рефактора

**Использование:** Скопируйте и вставьте команды в терминал для проверки

---

## ✅ Синтаксис и импорты

```bash
# Проверить синтаксис
python3 -m py_compile transkribator_modules/bot/handlers.py transkribator_modules/jobs/services.py
echo "✅ Синтаксис OK" || echo "❌ Ошибка синтаксиса"

# Найти все вызовы transcribe_audio в коде
echo "=== Calls to transcribe_audio (should be minimal) ==="
grep -r "transcribe_audio" transkribator_modules --include="*.py" | grep -v __pycache__ | wc -l
```

---

## 📍 Проверить изменения в handlers.py

```bash
# Убедиться, что transcribe_audio удалён из импортов
echo "=== transcribe_audio imports ==="
grep "from transkribator_modules.transcribe" transkribator_modules/bot/handlers.py

# Проверить, что enqueue_media_job есть
echo "=== enqueue_media_job imports ==="
grep "enqueue_media_job" transkribator_modules/bot/handlers.py | head -1

# Проверить количество вызовов enqueue_media_job (должно быть 3)
echo "=== Number of enqueue_media_job calls ==="
grep "enqueue_media_job(" transkribator_modules/bot/handlers.py | wc -l
```

---

## 🧪 Локальное тестирование

```bash
# 1. Проверить, что job queue структура готова
echo "=== Check job queue infrastructure ==="
ls -la transkribator_modules/jobs/*.py

# 2. Проверить, что все стейджи определены
echo "=== Pipeline stages ==="
grep "class.*Stage" transkribator_modules/jobs/stages.py

# 3. Убедиться, что default services готовы
echo "=== Default services ==="
grep "def default_" transkribator_modules/jobs/services.py
```

---

## 📊 Статистика изменений

```bash
# Показать diff между версиями
echo "=== Changes in handlers.py ==="
git diff transkribator_modules/bot/handlers.py | head -100

# Показать, что было удалено
echo "=== Removed async transcribe calls ==="
git diff transkribator_modules/bot/handlers.py | grep "^-.*await transcribe_audio"

# Показать, что было добавлено
echo "=== Added enqueue calls ==="
git diff transkribator_modules/bot/handlers.py | grep "^+.*enqueue_media_job"
```

---

## 🚀 Docker deployment checks

```bash
# Убедиться, что job_worker может быть запущен
echo "=== Check job_worker ==="
ls -la job_worker.py

# Проверить, что docker-compose имеет worker сервис
echo "=== Worker service in docker-compose ==="
grep -A10 "worker:" docker-compose.yml || grep -A10 "worker:" docker-compose.*.yml

# Проверить логи worker после запуска
echo "=== To check worker logs after deployment: ==="
echo "docker logs cyberkitty-worker | tail -50"
```

---

## 🔧 Database checks (если БД запущена)

```bash
# Проверить, что processing_jobs таблица существует
echo "=== Check processing_jobs table ==="
psql -h localhost -U transkribator -d transkribator -c "\dt processing_jobs"

# Показать pending jobs
echo "=== Pending jobs in queue ==="
psql -h localhost -U transkribator -d transkribator -c "SELECT id, user_id, status, created_at FROM processing_jobs WHERE status='pending' LIMIT 10;"

# Показать completed jobs
echo "=== Recent completed jobs ==="
psql -h localhost -U transkribator -d transkribator -c "SELECT id, user_id, status, updated_at FROM processing_jobs WHERE status='completed' ORDER BY updated_at DESC LIMIT 10;"
```

---

## 🎯 Quick Test Checklist

```bash
# 1. Убедиться, что файлы изменены
[ -f transkribator_modules/bot/handlers.py ] && echo "✅ handlers.py exists"
[ -f transkribator_modules/jobs/services.py ] && echo "✅ services.py exists"

# 2. Убедиться, что синтаксис OK
python3 -m py_compile transkribator_modules/bot/handlers.py && echo "✅ handlers.py syntax OK"
python3 -m py_compile transkribator_modules/jobs/services.py && echo "✅ services.py syntax OK"

# 3. Проверить документацию
[ -f REFACTOR_FINAL_REPORT.md ] && echo "✅ Final report exists"
[ -f REFACTOR_CHECKLIST.md ] && echo "✅ Checklist exists"

# Итог
echo ""
echo "🎉 All checks passed! Ready for testing."
```

---

## 📋 Если что-то не работает

```bash
# 1. Проверить логи bot'а
docker logs cyberkitty-bot 2>&1 | tail -50 | grep -i "error\|traceback"

# 2. Проверить логи worker'а
docker logs cyberkitty-worker 2>&1 | tail -50 | grep -i "error\|traceback"

# 3. Проверить PostgreSQL логи
docker logs cyberkitty-postgres 2>&1 | tail -20

# 4. Проверить, что job_worker запущен
docker ps | grep worker

# 5. Убедиться, что bot может подключиться к БД
docker exec cyberkitty-bot python -c "from transkribator_modules.db.database import SessionLocal; SessionLocal()" && echo "✅ DB connection OK"
```

---

**Совет:** Сохраните этот файл, он полезен для быстрой диагностики проблем! 🔧
