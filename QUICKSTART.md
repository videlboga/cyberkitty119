# 🚀 Быстрый старт Cyberkitty19 Transkribator

## 1. Подготовка

```bash
# Клонируем репозиторий
git clone <your-repo-url>
cd cyberkitty19-transkribator

# Копируем и настраиваем переменные окружения
cp env.sample .env
# Отредактируйте .env файл, добавив ваши API ключи
```

## MiniApp на локальной машине (вариант A: HTTPS tunnel для Telegram)

Telegram MiniApp требует **HTTPS**. Чтобы разрабатывать MiniApp локально и открывать его на телефоне в Telegram, используйте dev-сервер Vite + cloudflared туннель.

### 1) Запустите MiniApp dev-сервер

```bash
cd miniapp
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

### 2) Поднимите HTTPS-туннель (cloudflared)

```bash
docker compose -f docker-compose.miniapp-dev.yml up -d cloudflared
docker compose -f docker-compose.miniapp-dev.yml logs -f cloudflared
```

В логах появится URL вида `https://xxxxx.trycloudflare.com` — это HTTPS адрес MiniApp.

### 3) Укажите URL туннеля для бота

Установите переменную окружения (в `.env` или окружении контейнера бота):

- `MINIAPP_DEV_TUNNEL_URL=https://xxxxx.trycloudflare.com`

и перезапустите сервис `bot`. 

Бот использует `MINIAPP_DEV_TUNNEL_URL` (если задан) вместо `MINIAPP_PUBLIC_URL` для кнопки «🗂 Открыть MiniApp».