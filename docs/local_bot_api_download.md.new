---
title: "Local bot API download"
author: "Docs Team"
date: 2026-01-23
status: Draft
tags: [tg-bot, ingest]
related: []
---

# Manual download via local Bot API cache

Этот сценарий воспроизводит «рабочий» пайплайн: `getFile` через локальный
Bot API → файл появляется в общем томе `/app/telegram-bot-api-data` → бот копирует
его напрямую, не используя HTTP. Скрипт нужно запускать внутри контейнера
`cyberkitty19-transkribator-bot`, потому что только там есть доступ к тому и
нужные права (файлы лежат как `root:root`).

```bash
FILE_ID="<сюда file_id из логов>"
docker compose exec bot \
    python scripts/download_via_local_tgapi.py \
    "$FILE_ID" \
    --dest "/app/videos/manual_${FILE_ID}.mp4" \
    --expected-size 693548642
```

Что происходит:
- `getFile` идёт на `http://telegram-bot-api:8081`, tgapi скачивает файл в
  `/var/lib/telegram-bot-api/.../videos/file_X` (том смонтирован как
  `/app/telegram-bot-api-data`).
- `download_large_file` находит файл в общем томе и копирует его в `/app/videos/...`.
- HTTP-fallback не используется (на больших файлах он возвращает 404/400).

После копирования можно проверять файл в контейнере:

```bash
docker compose exec bot ls -lh \
    /app/videos/manual_${FILE_ID}.mp4
```

Важно убедиться, что в `docker-compose.prod.yml` у сервиса `bot` есть volume
`./telegram-bot-api-data:/app/telegram-bot-api-data` (по умолчанию так и есть).
