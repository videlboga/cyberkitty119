# 🧹 Cleanup Log — Удаление дублирования и лишнего кода

**Дата:** 24 февраля 2026  
**Ветка:** `feature/queue-adr-migration`

## Что было удалено

### 1. Старые обработчики (данные в `data/`)
- ✅ `data/container_handlers.py` — устаревшая версия обработчиков
- ✅ `data/updated_container_handlers.py` — старая версия обработчиков (почти идентична выше)

**Причина:** Эти файлы не используются в production коде, являются дубликатами старой архитектуры и создают путаницу.

**Проверка:** `grep -r "from data.container_handlers\|from data.updated_container_handlers" transkribator_modules tools scripts 2>/dev/null` — результат пуст (ничего не использует).

### 2. Backup/remote файлы из корня → перемещены в `.backups/`
Перемещены из корня в `.backups/` (уменьшено шума в root directory):
- ✅ `api_server.py.backup` → `.backups/api_server.py.backup`
- ✅ `api_server.py.remote` → `.backups/api_server.py.remote`
- ✅ `docker-compose.yml.backup` → `.backups/docker-compose.yml.backup`
- ✅ `docker-compose.yml.bak` → `.backups/docker-compose.yml.bak`
- ✅ `Dockerfile.api.remote` → `.backups/Dockerfile.api.remote`
- ✅ `cyberkitty-ssl.conf.remote` → `.backups/cyberkitty-ssl.conf.remote`
- ✅ `.env.bak` → `.backups/.env.bak`

**Причина:** Очищены корневую директорию от backup'ов, собраны в одном месте.

**Примечание:** `.backups/` добавлен в `.gitignore` для слежения.

## Результаты

| Метрика | До | После | Улучшение |
|---------|-------|--------|-----------|
| Файлы в `data/` | 2 ненужных | 0 | Удалены дубликаты |
| Backup'ы в root | 7 разбросаны | 0 (в `.backups/`) | Организованы |
| Дублирования функций | ❌ `container_handlers.py` дублирует logic из `handlers.py` | ✅ Одно определение | Упрощено |

## Что осталось для дальнейшей очистки

### Фаза 2 (Medium priority — Архитектурный рефактор)
- [ ] Перенести inline транскрибацию из `handlers.py` в queue-based систему (`jobs/`)
- [ ] Убрать дублирование логики между `handlers.py` (процесс видео/аудио) и `jobs/stages.py` (pipeline stages)
- [ ] Консолидировать обработчики команд (`start_command`, `status_command`, `help_command`) — они определены в нескольких местах

### Фаза 3 (Low priority — Технический долг)
- [ ] Переместить `archive/` в отдельный branch или external storage (экономия места)
- [ ] Удалить тестовые файлы `test_*.py` из root, перенести в `tests/`
- [ ] Очистить `minimal_app/` — определить, активно ли используется

## Следующие шаги

После очистки рекомендуется:
1. ✅ **Этап 1 (완료)** — Удалить лишние файлы (выполнено выше)
2. ⏳ **Этап 2** — Рефактор: перенести основную транскрибацию на queue-based подход
3. ⏳ **Этап 3** — Документировать правильную архитектуру (Telegram → Bot handlers vs Job Queue)

## Команды для проверки

```bash
# Убедиться, что удалённые файлы не используются:
grep -r "container_handlers\|updated_container_handlers" . --include="*.py" 2>/dev/null

# Проверить структуру проекта после очистки:
find . -maxdepth 1 -type f \( -name '*.py' -o -name '*.bak' -o -name '*.backup' \) | sort

# Размер проекта до/после:
du -sh .
```
