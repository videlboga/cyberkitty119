# Локальная настройка для разработчиков

Этот документ описывает быстрые шаги для локальной валидации документации и включения локальных гит-хуков в проекте.

# Локальная настройка для разработчиков

---
title: "Локальная настройка — инструкция для разработчиков"
author: "Docs Team"
date: 2026-01-24
status: Draft
tags: [docs, dev, tools]
related: []
---

# Локальная настройка для разработчиков

Этот документ описывает быстрые шаги для локальной валидации документации и включения локальных гит-хуков в проекте.
## Включить локальные git-хуки

Проект содержит локальную папку `.githooks` с готовым хуком `pre-commit`, который запускает проверку метаданных через Docker.

Включите хуки один раз:

```bash
# включить локальные хуки из папки .githooks
git config core.hooksPath .githooks
```

После этого при коммите будет запускаться скрипт, который проверяет front-matter в `docs/`.

## Запуск валидатора вручную (Docker)

Если не хотите подключать хуки, можно запускать валидатор вручную:

```bash
./.github/scripts/run_metadata_validator_docker.sh
```

Скрипт поднимает временный контейнер Python 3.11, устанавливает `pyyaml` и запускает `.github/scripts/validate_metadata.py docs`.

## Локальная установка через virtualenv

Если вы предпочитаете установить зависимости в виртуальном окружении:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install pyyaml
python .github/scripts/validate_metadata.py docs
```

## Совет по работе с pre-commit

Если вы используете `pre-commit` (рекомендуется), можно добавить вызов Docker-скрипта или `python .github/scripts/validate_metadata.py docs` в `.pre-commit-config.yaml` как локальный hook.

## Что делать, если CI падает

- Запустите Docker-валидатор локально и исправьте замеченные поля front-matter.
- Если у вас нет прав на docker, используйте `virtualenv` и выполните `python .github/scripts/validate_metadata.py docs`.

---

Ссылка: см. также `docs/meta-instructions.md` (главная мета-инструкция по документам).
