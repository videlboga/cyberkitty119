# Cyberkitty19 Transkribator 🐱

Боевая версия Telegram‑бота и accompanying API для транскрибации видео/аудио, ведения заметок и умного ассистента c «кошачьим» тоном. Проект развёрнут в продакшне и использует Postgres, Docker и фоновый воркер.

## 🚀 Основные возможности
- Импорт медиа из Telegram, YouTube, Google Drive и внешних ссылок.
- Высокачественная транскрибация (DeepInfra Whisper) с последующим форматированием через LLM (OpenRouter).
- Автоматическое создание заметок/саммари, хранение истории и мини‑приложение в Telegram.
- Система тарифов и промокодов, поддержка Telegram Stars и API‑ключей.
- Планировщик напоминаний: за 3 дня до завершения платного плана и в момент истечения пользователю отправляется уведомление.
- Отдельный HTTP API (FastAPI) для мини‑аппа и внешних интеграций.

## 🧱 Архитектура
| Компонент | Назначение |
|-----------|------------|
| `bot` | Основной Telegram‑бот (`cyberkitty_modular.py`). Обрабатывает входящие сообщения, управляет тарифами и заметками. |
| `api` | FastAPI (`api_server.py`), служит фронтом для мини‑приложения, личного кабинета, webhook’ов и автоматизации. |
| `worker` | Фоновый воркер (`job_worker.py`), выполняет очередь задач + периодически рассылает уведомления о тарифах. |
| `telegram-bot-api` | Локальный контейнер Telegram Bot API Server для ускоренной загрузки больших файлов. |
| `postgres` | Основное persistent‑хранилище (таблицы пользователей, заметок, транскрипций, тарифов). |

> Дополнительная документация: `PRODUCTION_DEPLOY.md`, `QUICK_DEPLOY.md`, `POSTGRES_MIGRATION.md`, `MONETIZATION_GUIDE.md`, `TELEGRAM_STARS_GUIDE.md`.

## ⚙️ Быстрый старт (Docker Compose)
1. Клонировать репозиторий:
   ```bash
   git clone git@github.com:Videlboga/cyberkitty119.git
   cd cyberkitty119
   ```
2. Подготовить env:
   ```bash
   cp env.sample .env
   ```
   Минимальный набор переменных — `BOT_TOKEN`, `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `DEEPINFRA_API_KEY`, `OPENROUTER_API_KEY`, `POSTGRES_*`. Для продакшна обязательно заполните блоки монетизации/Google OAuth, при необходимости включите `FEATURE_BETA_MODE`.
3. Запустить стек:
   ```bash
   docker compose up -d --build
   ```
   Стартуют сервисы `bot`, `api`, `worker`, `telegram-bot-api`, `postgres`. Логи можно смотреть через `docker logs <container>`.

### Параметры воркера
- `PLAN_REMINDER_INTERVAL` — интервал (сек) между проверками подписок, по умолчанию 1800 (30 мин).
- `DISABLE_PLAN_REMINDERS=true` — выключить напоминания (например, в dev окружении).

## 🛠️ Локальная разработка (без Docker)
```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp env.sample .env                   # заполните токены/ключи
python api_server.py                 # поднимет API на 0.0.0.0:8000
python job_worker.py                 # фоновые задачи + уведомления
python cyberkitty_modular.py         # Telegram-бот
```
Для работы без Postgres можно временно использовать SQLite (см. `DATABASE_URL` в `.env`), но большинство продакшн‑фич (планы, мини‑апп) протестированы именно на Postgres 16.

## 📦 Структура репозитория
```
transkribator/
├── docker-compose.yml              # основной docker стек
├── transkribator_modules/
│   ├── bot/                        # команды и обработчики Telegram
│   ├── jobs/                       # очередь задач, планировщик напоминаний
│   ├── db/                         # модели SQLAlchemy, сервисы работы с БД
│   ├── api/                        # FastAPI ручки для миниаппа
│   └── ...
├── job_worker.py                   # CLI воркера
├── api_server.py                   # FastAPI приложение
├── cyberkitty_modular.py           # точка входа бота
├── scripts/                        # вспомогательные скрипты деплоя/обслуживания
└── docs (.md)                      # отдельные руководства (деплой, миграции и т.д.)
```

## 🔄 Миграции БД
Проект использует Alembic:
```bash
alembic upgrade head        # применить миграции
alembic revision -m "msg"   # создать новую миграцию
```
Конфиги находятся в `alembic/` и `alembic.ini`.

## ✅ Тестирование
```bash
pytest tests
```
Для интеграционных тестов, требующих брокеров/бота, настройте `.env.test` или мокните внешние сервисы.

## 🐾 Контакты и вклад
Pull request’ы приветствуются. Перед отправкой — прогоните тесты и отформатируйте код (black/isort). Описание релизов ведётся в `CHANGELOG.md`.

## 📄 Лицензия
MIT — см. `LICENSE`.
