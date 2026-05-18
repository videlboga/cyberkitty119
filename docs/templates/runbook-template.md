---
title: "Runbook: ServiceName - краткое описание"
author: "Ops Team <ops@company>"
date: 2026-01-23
status: Draft
tags: [runbook, ops]
related: []
---

# Runbook: ServiceName

## Назначение
Кратко: что делает сервис и почему он важен.

## Контакты
- On-call: @oncall
- Owner: owner@company
- Escalation: team-lead -> infra -> dev

## Health checks
- HTTP: GET /health
- Liveness: ...

## Быстрая диагностика
- Просмотр логов: docker logs --tail 200 service-name
- Проверить очерёдь: redis-cli LRANGE transcribe_queue 0 10
- Проверить S3: mc ls minio/media/<id>

## Типичные инциденты и шаги восстановления
1) Сервис не отвечает:
   - Проверить статус контейнера
   - Перезапустить сервис
   - Проверить логи на ошибки
2) Backlog растёт:
   - Увеличить количество воркеров
   - Проверить очередь и slow jobs

## Быстрые команды
- Перезапуск: docker-compose restart service-name
- Проверить статус: docker ps | grep service-name

## После исправления
- Проверить, что backlog упал
- Проверить, что примеры задач проходят end-to-end
