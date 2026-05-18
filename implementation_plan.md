# План доработки Транскрибатора (Standalone)

Дата: 2025-09-25T10:33:27.936420Z

## Обновления 2025-09
- Расширены действия команд: `post`, `quotes`, `timed_outline`, `move`, `retag`, `task_from_note`, `free_prompt`.
- Режим бэклога обновлён: повторная обработка заметки меняет исходную карточку без дублей, прогресс отображается в чате.
- Семантический поиск переведён на `pgvector` с размерностью 1536 и live-эмбеддингами через OpenRouter (остался fallback без сети).
- Каталог пресетов дополнен сценариями для постов, цитат и таймлайнов; `post_actions` маркируют доступные ветки команд.
- Ручные формы поддерживают intent `help` и новый набор полей для действий.
- /help и другие интенты роутера возвращают дружественные подсказки вместо заглушек.

## Основные изменения
- Роутер включается **только для команд**.
- Все медиа → транскрибируются и показывают экран «Обработка».
- Экран «Обработка»: 4 кнопки (Обработать сейчас, Обработать позже, Просто сохранить, Закрыть).
- Автобэклог: любая карточка, которую не обработали, уходит в backlog автоматически при следующем сообщении.
- «Обработать сейчас»: показываются top-3 варианта из каталога промтов + «Свободный промпт».

## Миграции БД
Добавить поля в `notes`: status, type_hint, type_confidence, tags, summary, drive_file_id, sheet_row_id, meta(json).  
И таблицу note_embeddings для семантического поиска.

## Каталог пресетов (`prompts_catalog.json`)
- Поля пресета: `content_types`, `priority`, `match_hints`, `min_characters`, `max_characters`, `requires_timecodes`, `system_prompt`, `user_prompt_template`, `post_actions`.
- `custom.free_prompt` хранит заглушку для ручного ввода.
- Каталог загружается один раз при старте, кешируется и пробрасывается в `suggest_top3` и контентный процессор.

## suggest_top3
- Фильтр по типу заметки, длине и признаку `requires_timecodes`.
- Семантический скоринг по `match_hints` (BM25/TF-IDF + хвост по эмбеддингам, если есть).
- Если нет уверенного топа → дефолт пользователя на первое место.

## Команды (роутер mode=command)
- conf≥0.80 → одно подтверждение «Да/Изменить».
- 0.55–0.79 → «Похоже, команда. Выполнить? Да/Нет».
- <0.55 → контент.

## Сохранение
- Markdown с YAML → Drive (/CyberKitty/<user>/<folder>) и Index (Sheets).
- Файл локально всегда, даже если Drive упал.

## Поиск
- /search <q> → top-k из note_embeddings ∩ фильтры из Index.
- Режимы: quotes, timeline, tldr.

## Acceptance
- ≤2 клика до результата для 80% кейсов.
- На первом экране «Обработка» всегда 4 кнопки.
- Автобэклог включён для всего необработанного.
- Команды подтверждаются одним диалогом.

## Progress 2026-01-27 — containerized DeepInfra worker (brief)

- Implemented a containerized worker image under `tools/di_worker` to POST audio to DeepInfra and extract segment timestamps.
- Added `wg_entrypoint.sh` and updated Dockerfile to include `wireguard-tools`, `openresolv`, `procps`, and `iptables` so the container can bring up WireGuard if required.
- Created `extract_segments.py` that writes CSV and human-readable timestamped transcript from DeepInfra JSON.
- Performed E2E run: mounted host `/home/cyberkitty/Projects/torrent/wg0.conf`, used host `DEEPINFRA_API_KEY`, and executed `run_e2e` inside the image; outputs written to `/home/cyberkitty/Projects/Cyberkitty119/results/di_e2e/`.
- Observed runtime requirements: bringing up WG inside container needs host capabilities (tested `--privileged`; `--cap-add=NET_ADMIN --device=/dev/net/tun` may work with tuned host policies).

Next steps:
- Decide runtime model for deployment (host netns vs in-container WG vs podman ns attach).
- Harden the image and runbook (systemd unit template, limited capabilities, secret handling guidance).

