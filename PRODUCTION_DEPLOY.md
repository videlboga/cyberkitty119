# 🚀 Развертывание Cyberkitty19 Transkribator на продакшн сервере

## 📋 Требования к серверу

### Минимальные требования:
- **ОС**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **RAM**: 4 ГБ (рекомендуется 8 ГБ)
- **CPU**: 2 ядра (рекомендуется 4 ядра)
- **Диск**: 50 ГБ свободного места
- **Сеть**: Стабильное интернет-соединение

### Необходимое ПО:
- Docker и Docker Compose
- Git
- tmux (опционально)

## 🔧 Подготовка сервера

### 1. Обновление системы
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

### 2. Установка Docker
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Перелогиньтесь или выполните:
newgrp docker

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 3. Установка дополнительных пакетов
```bash
# Ubuntu/Debian
sudo apt install -y git tmux htop nano

# CentOS/RHEL
sudo yum install -y git tmux htop nano
```

## 📦 Развертывание проекта

### 1. Клонирование репозитория
```bash
cd /opt
sudo git clone https://github.com/your-username/cyberkitty19-transkribator.git
sudo chown -R $USER:$USER cyberkitty19-transkribator
cd cyberkitty19-transkribator
```

### 2. Настройка переменных окружения
```bash
# Копируем шаблон
cp env.sample .env

# Редактируем конфигурацию
nano .env
```

**Обязательно заполните:**
```bash
# Токен бота от @BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# API ключи для транскрибации (минимум один)
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Настройки Pyrogram для больших видео
PYROGRAM_WORKER_ENABLED=true
TELEGRAM_API_ID=21532963
TELEGRAM_API_HASH=66e38ebc131425924c2680e6c8fb6c09
PYROGRAM_WORKER_CHAT_ID=0  # Будет настроено позже

# База данных
DATABASE_URL=sqlite:///./cyberkitty19-transkribator.db
```

### 3. Создание необходимых директорий
```bash
mkdir -p videos audio transcriptions logs
chmod 755 videos audio transcriptions logs
```

### 4. Настройка файрвола (если используется)
```bash
# UFW (Ubuntu)
sudo ufw allow 8000/tcp  # API сервер
sudo ufw allow 22/tcp    # SSH

# Firewalld (CentOS)
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=22/tcp
sudo firewall-cmd --reload
```

## 🐳 Запуск через Docker (рекомендуется)

### 1. Сборка и запуск контейнеров
```bash
# Сборка образов
docker-compose build

# Запуск в фоновом режиме
docker-compose up -d

# Проверка статуса
docker-compose ps
```

### 2. Просмотр логов
```bash
# Все сервисы
docker-compose logs -f

# Конкретный сервис
docker-compose logs -f cyberkitty19-transkribator-bot
docker-compose logs -f cyberkitty19-transkribator-api
```

### 3. Авторизация Pyrogram воркера
```bash
# Запуск интерактивной авторизации
docker-compose exec cyberkitty19-transkribator-pyro-worker python -m transkribator_modules.workers.pyro_auth

# Следуйте инструкциям для ввода номера телефона и кода
```

## 🔧 Альтернативный запуск (без Docker)

### 1. Установка Python и зависимостей
```bash
# Установка Python 3.8+
sudo apt install -y python3 python3-pip python3-venv ffmpeg

# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 2. Запуск сервисов
```bash
# В tmux сессиях для фонового запуска

# Основной бот
tmux new-session -d -s cyberkitty-bot 'source venv/bin/activate && python cyberkitty_modular.py'

# API сервер
tmux new-session -d -s cyberkitty-api 'source venv/bin/activate && python api_server.py'

# Pyrogram воркер (после авторизации)
tmux new-session -d -s cyberkitty-pyro 'source venv/bin/activate && python -m transkribator_modules.workers.pyro_worker'
```

## 🔐 Настройка безопасности

### 1. Создание отдельного пользователя
```bash
sudo useradd -m -s /bin/bash cyberkitty
sudo usermod -aG docker cyberkitty
sudo chown -R cyberkitty:cyberkitty /opt/cyberkitty19-transkribator
```

### 2. Настройка systemd сервиса
```bash
sudo nano /etc/systemd/system/cyberkitty19-transkribator.service
```

```ini
[Unit]
Description=Cyberkitty19 Transkribator Bot Service
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=cyberkitty
WorkingDirectory=/opt/cyberkitty19-transkribator
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
# Активация сервиса
sudo systemctl enable cyberkitty19-transkribator.service
sudo systemctl start cyberkitty19-transkribator.service
```

### 3. Настройка логирования
```bash
# Ротация логов
sudo nano /etc/logrotate.d/cyberkitty19-transkribator
```

```
/opt/cyberkitty19-transkribator/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 cyberkitty cyberkitty
}
```

## 📊 Мониторинг и обслуживание

### 1. Проверка статуса
```bash
# Docker контейнеры
docker-compose ps

# Системный сервис
sudo systemctl status cyberkitty19-transkribator.service

# Использование ресурсов
docker stats
```

### 2. Резервное копирование
```bash
#!/bin/bash
# backup.sh
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/cyberkitty19-transkribator"

mkdir -p $BACKUP_DIR

# Бэкап базы данных
cp /opt/cyberkitty19-transkribator/cyberkitty19-transkribator.db $BACKUP_DIR/db_$DATE.db

# Бэкап конфигурации
cp /opt/cyberkitty19-transkribator/.env $BACKUP_DIR/env_$DATE.backup

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.backup" -mtime +30 -delete
```

### 3. Обновление проекта
```bash
#!/bin/bash
# update.sh
cd /opt/cyberkitty19-transkribator

# Остановка сервисов
docker-compose down

# Обновление кода
git pull

# Пересборка образов
docker-compose build

# Запуск сервисов
docker-compose up -d

# Проверка статуса
docker-compose ps
```

## 🚨 Устранение неполадок

### 1. Проблемы с запуском
```bash
# Проверка логов
docker-compose logs cyberkitty19-transkribator-bot

# Проверка переменных окружения
docker-compose exec cyberkitty19-transkribator-bot env | grep TELEGRAM

# Перезапуск сервисов
docker-compose restart
```

### 2. Проблемы с Pyrogram
```bash
# Удаление сессии и повторная авторизация
rm transkribator_modules/workers/pyro_worker.session*
docker-compose exec cyberkitty19-transkribator-pyro-worker python -m transkribator_modules.workers.pyro_auth
```

### 3. Проблемы с базой данных
```bash
# Проверка базы данных
docker-compose exec cyberkitty19-transkribator-bot python -c "
from transkribator_modules.db.database import SessionLocal
db = SessionLocal()
print('База данных доступна')
db.close()
"
```

## 📈 Оптимизация производительности

### 1. Настройка Docker
```yaml
# docker-compose.override.yml
version: '3.8'
services:
  cyberkitty19-transkribator-bot:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
  
  cyberkitty19-transkribator-api:
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 512M
```

### 2. Настройка nginx (опционально)
```nginx
# /etc/nginx/sites-available/cyberkitty19-transkribator
server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🔗 Полезные команды

```bash
# Быстрый перезапуск
docker-compose restart

# Просмотр логов в реальном времени
docker-compose logs -f --tail=100

# Подключение к контейнеру
docker-compose exec cyberkitty19-transkribator-bot bash

# Очистка старых образов
docker system prune -a

# Мониторинг ресурсов
docker stats --no-stream
```

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи: `docker-compose logs`
2. Убедитесь в правильности .env файла
3. Проверьте доступность API ключей
4. Обратитесь к документации: README.md

---

**🎉 Ваш Cyberkitty19 Transkribator готов к работе на продакшн сервере!** 