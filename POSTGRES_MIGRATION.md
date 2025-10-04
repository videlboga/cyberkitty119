# Миграция данных из SQLite в PostgreSQL

Эти шаги помогут перейти на PostgreSQL после подготовки инфраструктуры.

## 1. Подготовка окружения
1. Убедитесь, что в `.env` заданы переменные:
   ```bash
   DATABASE_URL=postgresql+psycopg://transkribator:strong_password@postgres:5432/transkribator
   POSTGRES_DB=transkribator
   POSTGRES_USER=transkribator
   POSTGRES_PASSWORD=strong_password
   ```
2. Примените миграции: `make migrate` (или `alembic upgrade head`) — создаст пустые таблицы в новой БД.

## 2. Экспорт из SQLite
Создайте SQL-дамп текущей базы:
```bash
sqlite3 data/cyberkitty19_transkribator.db '.backup /tmp/sqlite_dump.sql'
```

## 3. Загрузка в PostgreSQL
Используйте psql (доступно внутри контейнера Postgres):
```bash
cat /tmp/sqlite_dump.sql |
  docker compose exec -T postgres psql \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```
> При необходимости можно воспользоваться `pgloader` для автоматического преобразования типов.

## 4. Проверка
1. Запустите `alembic upgrade head` ещё раз — убедитесь, что схема совпадает.
2. Прогоните базовые тесты: `make test` (`pytest`) или `python -m unittest` (при наличии тестов) и смоук-сценарии бота/API.
3. Проверьте ручные сценарии: вход в бота, апгрейд тарифа, активация промокода, транскрибация файла.

## 5. Резервные копии
После миграции настройте регулярный бэкап PostgreSQL, например через `pg_dump`:
```bash
docker compose exec postgres pg_dump \
  -U "$POSTGRES_USER" "$POSTGRES_DB" \
  > backups/transkribator-$(date +%F).sql
```

## 6. Обновление сервисов
- Перезапустите контейнеры с новым `DATABASE_URL`.
- Убедитесь, что все сервисы (бот, API, воркеры) сообщают об успешном подключении к PostgreSQL.

## 7. Pgvector 1536 и переиндексация
1. Установите расширение `vector`, если оно ещё не активировано: `CREATE EXTENSION IF NOT EXISTS vector;`.
2. Примените новую миграцию: `alembic upgrade 0004_pgvector_dim_1536`.
3. Пересоберите векторный индекс после миграции: `python3 scripts/rebuild_vector_index.py`.
4. Убедитесь, что поисковый запрос в `/search` возвращает результаты и что в таблице `note_chunks` сохраняются векторы размером 1536.
