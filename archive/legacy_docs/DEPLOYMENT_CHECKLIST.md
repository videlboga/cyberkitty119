# ✅ Чек-лист развертывания Cyberkitty19 Transkribator

## 📋 Подготовка к развертыванию

### Перед началом убедитесь, что у вас есть:

- [ ] **Сервер** с Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- [ ] **SSH доступ** к серверу с правами sudo
- [ ] **Токен Telegram бота** от @BotFather
- [ ] **API ключи** для транскрибации (OpenAI или OpenRouter)
- [ ] **Telegram API** данные (API_ID, API_HASH) с https://my.telegram.org/apps
- [ ] **Домен** (опционально, для HTTPS)

## 🚀 Процесс развертывания

### Шаг 1: Подготовка сервера
```bash
# Подключение к серверу
ssh user@your-server-ip

# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перелогиньтесь
exit
ssh user@your-server-ip
```

**Проверка:**
- [ ] `docker --version` работает
- [ ] `docker-compose --version` работает
- [ ] `docker ps` выполняется без sudo

### Шаг 2: Клонирование проекта
```bash
# Переход в директорию для проектов
cd /opt
sudo git clone https://github.com/your-username/cyberkitty19-transkribator.git
sudo chown -R $USER:$USER cyberkitty19-transkribator
cd cyberkitty19-transkribator
```

**Проверка:**
- [ ] Проект склонирован в `/opt/cyberkitty19-transkribator`
- [ ] У пользователя есть права на директорию

### Шаг 3: Настройка конфигурации
```bash
# Создание .env файла
cp env.sample .env
nano .env
```

**Заполните обязательные поля:**
- [ ] `TELEGRAM_BOT_TOKEN` - токен от @BotFather
- [ ] `OPENAI_API_KEY` или `OPENROUTER_API_KEY` - API ключ для транскрибации
- [ ] `TELEGRAM_API_ID` и `TELEGRAM_API_HASH` - для больших видео
- [ ] `HEALTH_CHECK_CHAT_ID` - ваш chat_id для уведомлений (опционально)

### Шаг 4: Развертывание
```bash
# Автоматическое развертывание
./deploy.sh production
```

**Проверка:**
- [ ] Все контейнеры запущены: `docker-compose ps`
- [ ] API отвечает: `curl http://localhost:8000/health`
- [ ] Нет критических ошибок в логах: `docker-compose logs`

### Шаг 5: Настройка Pyrogram (для больших видео)
```bash
# Авторизация Pyrogram воркера
docker-compose exec cyberkitty19-transkribator-pyro-worker python -m transkribator_modules.workers.pyro_auth
```

**Следуйте инструкциям:**
- [ ] Введите номер телефона
- [ ] Введите код подтверждения
- [ ] Сессия создана успешно

### Шаг 6: Тестирование
- [ ] Найдите бота в Telegram
- [ ] Отправьте `/start` - бот должен ответить
- [ ] Отправьте небольшое видео - должна прийти транскрипция
- [ ] Отправьте большое видео (>20MB) - должен сработать Pyrogram воркер

## 🔐 Настройка безопасности

### Файрвол
```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8000/tcp  # API (если нужен внешний доступ)
sudo ufw enable
```

**Проверка:**
- [ ] SSH доступ работает
- [ ] Ненужные порты закрыты

### Создание отдельного пользователя
```bash
sudo useradd -m -s /bin/bash cyberkitty
sudo usermod -aG docker cyberkitty
sudo chown -R cyberkitty:cyberkitty /opt/cyberkitty19-transkribator
```

**Проверка:**
- [ ] Пользователь `cyberkitty` создан
- [ ] Права на проект переданы

### Настройка systemd сервиса
```bash
# Копирование сервис файла
sudo cp cyberkitty19-transkribator.service /etc/systemd/system/

# Редактирование путей в сервис файле
sudo nano /etc/systemd/system/cyberkitty19-transkribator.service

# Активация сервиса
sudo systemctl enable cyberkitty19-transkribator.service
sudo systemctl start cyberkitty19-transkribator.service
```

**Проверка:**
- [ ] Сервис активен: `sudo systemctl status cyberkitty19-transkribator.service`
- [ ] Автозапуск настроен

## 📊 Настройка мониторинга

### Проверка здоровья системы
```bash
# Ручная проверка
./health-check.sh --verbose

# Добавление в crontab для автоматической проверки
crontab -e
```

**Добавьте в crontab:**
```bash
# Проверка каждые 15 минут
*/15 * * * * cd /opt/cyberkitty19-transkribator && ./health-check.sh --telegram

# Очистка старых файлов каждую ночь
0 2 * * * cd /opt/cyberkitty19-transkribator && find videos -mtime +7 -delete
0 2 * * * cd /opt/cyberkitty19-transkribator && find audio -mtime +7 -delete
0 3 * * * docker system prune -f
```

**Проверка:**
- [ ] Скрипт проверки здоровья работает
- [ ] Cron задачи добавлены
- [ ] Уведомления в Telegram настроены (если нужно)

## 🔄 Настройка резервного копирования

### Создание скрипта бэкапа
```bash
# Создание директории для бэкапов
sudo mkdir -p /opt/backups/cyberkitty19-transkribator

# Создание скрипта бэкапа
cat > backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups/cyberkitty19-transkribator"

# Бэкап базы данных
cp cyberkitty19-transkribator.db $BACKUP_DIR/db_$DATE.db

# Бэкап конфигурации
cp .env $BACKUP_DIR/env_$DATE.backup

# Удаление старых бэкапов (старше 30 дней)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.backup" -mtime +30 -delete
EOF

chmod +x backup.sh
```

**Добавьте в crontab:**
```bash
# Ежедневный бэкап в 1:00
0 1 * * * cd /opt/cyberkitty19-transkribator && ./backup.sh
```

**Проверка:**
- [ ] Скрипт бэкапа создан
- [ ] Cron задача для бэкапа добавлена
- [ ] Тестовый бэкап создается

## 🌐 Настройка домена (опционально)

### Nginx reverse proxy
```bash
# Установка Nginx
sudo apt install -y nginx

# Создание конфигурации
sudo nano /etc/nginx/sites-available/cyberkitty19-transkribator
```

**Конфигурация Nginx:**
```nginx
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

```bash
# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/cyberkitty19-transkribator /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL сертификат (Let's Encrypt)
```bash
# Установка Certbot
sudo apt install -y certbot python3-certbot-nginx

# Получение сертификата
sudo certbot --nginx -d your-domain.com
```

**Проверка:**
- [ ] Nginx настроен
- [ ] SSL сертификат установлен
- [ ] API доступен через домен

## ✅ Финальная проверка

### Функциональность
- [ ] Бот отвечает на `/start`
- [ ] Транскрибация небольших видео работает
- [ ] Транскрибация больших видео работает (Pyrogram)
- [ ] API сервер доступен
- [ ] Система монетизации работает (если настроена)

### Безопасность
- [ ] Файрвол настроен
- [ ] SSH ключи настроены (рекомендуется)
- [ ] Отдельный пользователь создан
- [ ] Права доступа настроены

### Мониторинг
- [ ] Проверка здоровья работает
- [ ] Уведомления настроены
- [ ] Логи ротируются
- [ ] Бэкапы создаются

### Автоматизация
- [ ] Systemd сервис работает
- [ ] Автозапуск при перезагрузке
- [ ] Cron задачи настроены
- [ ] Скрипты управления работают

## 📞 Контакты и поддержка

**При возникновении проблем:**
1. Проверьте логи: `docker-compose logs -f`
2. Запустите проверку здоровья: `./health-check.sh --verbose`
3. Проверьте статус: `docker-compose ps`
4. Обратитесь к документации: [README.md](README.md)

**Полезные команды:**
```bash
./view-logs.sh    # Просмотр логов
./restart.sh      # Перезапуск
./stop.sh         # Остановка
./update.sh       # Обновление
./health-check.sh # Проверка здоровья
```

---

**🎉 Поздравляем! Cyberkitty19 Transkribator успешно развернут на продакшн сервере!** 