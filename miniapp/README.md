# Telegram Mini App UI

Мини-приложение собрано на **Vite + React + TypeScript** и реализует интерфейс из `docs/miniapp_plan.md`. Клиент готов к работе внутри Telegram WebApp, но корректно запускается и в обычном браузере.

## Возможности

- Список заметок с фильтрами по периоду, статусу, типу, тегам и полнотекстовым поиском.
- Календарное представление (день/неделя/месяц) с agenda-представлением и быстрым переходом к редактору.
- Управление группами/тегами: создание, редактирование, объединение, AI-подсказки (через моковые данные).
- Редактор заметки с поддержкой тегов, статусов, связанных дат, deeplink в Telegram и интеграцией MainButton/BackButton.
- Экран настроек (таймзона, beta-mode, автосохранение, аналитика, текущая цветовая схема Telegram).
- Базовые хаптики, применение `themeParams`, работа с `initData`.

## Запуск

```bash
cd miniapp
npm install
npm run dev   # http://localhost:5173

npm run build # продакшен-сборка в dist/
npm run preview
```

## Переменные окружения

| Env                     | По умолчанию | Назначение |
|-------------------------|--------------|------------|
| `VITE_API_URL`          | `/api/miniapp` | Бэкенд для заметок/групп |
| `VITE_TWA_BOT_NAME`     | `your_bot`   | Telegram deeplink (`tg://resolve?domain=`) |
| `VITE_USE_MOCK_DATA`    | `true`       | Использовать встроенные мок-данные |

При `VITE_USE_MOCK_DATA=true` все CRUD-операции выполняются поверх локального in-memory стора (см. `src/mocks`). Отключите флаг и настройте `VITE_API_URL`, когда появятся готовые эндпойнты (`/notes`, `/groups`, `/calendar`, ...).

## Структура

- `src/app/providers` — обёртки над Telegram WebApp SDK, тема, QueryProvider.
- `src/app/hooks` — вспомогательные хуки (`useTelegram`, `useTelegramMainButton`, `useTelegramHaptic`).
- `src/features/*` — модули домена (notes, groups, filters, calendar).
- `src/pages` — основные экраны.
- `src/components/common` — переиспользуемые UI-компоненты.
- `src/mocks` — мок-данные и фабрики.

## Интеграция с Telegram

- `TelegramProvider` вызывает `WebApp.ready()`, `expand()`, применяет `themeParams`, отслеживает `themeChanged`.
- `NoteEditor` использует `MainButton`, `BackButton` и haptic feedback.
- initData отображается в настройках; токен хранится в `localStorage` (готово для будущей авторизации).

## Что дальше

- Подключить реальные API-эндпойнты и заменить моковые сервисы.
- Реализовать историю версий заметок и IndexedDB-офлайн.
- Настроить e2e (Playwright) и unit-тесты (React Testing Library) для критичных сценариев.
