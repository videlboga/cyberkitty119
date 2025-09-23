# ⚡ Быстрое развертывание Cyberkitty19 Transkribator на сервере

## 🚀 Одной командой

```bash
# Клонирование и развертывание
git clone https://github.com/your-username/cyberkitty19-transkribator.git
cd cyberkitty19-transkribator
./deploy.sh production
```

## 📝 Что нужно подготовить заранее

### 1. Токен Telegram бота
- Найдите @BotFather в Telegram
- Создайте нового бота: `/newbot`
- Сохраните токен

### 2. API ключи для транскрибации (минимум один)
- **OpenAI**: https://platform.openai.com/api-keys
- **OpenRouter**: https://openrouter.ai/keys (поддерживает Claude, Gemini)

### 3. Telegram API (для больших видео)
- Перейдите на https://my.telegram.org/apps
- Создайте приложение
- Сохраните API_ID и API_HASH

## 🔧 Настройка на сервере

### Шаг 1: Подготовка сервера
```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Установка Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перелогиньтесь или выполните:
newgrp docker
```

### Шаг 2: Развертывание проекта
```bash
# Клонирование
git clone https://github.com/your-username/cyberkitty19-transkribator.git
cd cyberkitty19-transkribator

# Настройка конфигурации
cp env.sample .env
nano .env  # Заполните ваши API ключи

# Автоматическое развертывание
./deploy.sh production
```


## 📊 Управление сервисом

После развертывания у вас будут доступны скрипты:

```bash
./view-logs.sh   # Просмотр логов
./restart.sh     # Перезапуск сервисов  
./stop.sh        # Остановка сервисов
./update.sh      # Обновление проекта
```

## 🔍 Проверка работы

### 1. Статус контейнеров
```bash
docker-compose ps
```

### 2. Логи сервисов
```bash
docker-compose logs -f
```

### 3. Тест API
```bash
curl http://localhost:8000/health
```

### 4. Тест бота
- Найдите вашего бота в Telegram
- Отправьте `/start`
- Попробуйте отправить видео

## 🚨 Устранение проблем

### Бот не отвечает
```bash
# Проверьте логи
docker-compose logs cyberkitty19-transkribator-bot

# Проверьте токен
grep TELEGRAM_BOT_TOKEN .env
```

### API недоступен
```bash
# Проверьте статус API контейнера
docker-compose ps cyberkitty19-transkribator-api

# Проверьте логи API
docker-compose logs cyberkitty19-transkribator-api
```

## 🔄 Обновление

```bash
# Автоматическое обновление
./update.sh

# Или вручную
docker-compose down
git pull
docker-compose build
docker-compose up -d
```

## 🔐 Безопасность

### Настройка файрвола
```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8000/tcp  # API (опционально)
sudo ufw enable

# Firewalld (CentOS)
sudo firewall-cmd --permanent --add-port=22/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### Создание отдельного пользователя
```bash
sudo useradd -m -s /bin/bash cyberkitty
sudo usermod -aG docker cyberkitty
sudo chown -R cyberkitty:cyberkitty /path/to/cyberkitty19-transkribator
```

## 📈 Мониторинг

### Использование ресурсов
```bash
docker stats --no-stream
```

### Размер логов
```bash
du -sh logs/
```

### Автоматическая очистка
```bash
# Добавьте в crontab
0 2 * * * docker system prune -f
0 3 * * * find /path/to/cyberkitty19-transkribator/videos -mtime +7 -delete
```

---

**🎉 Ваш Cyberkitty19 Transkribator готов к работе на продакшн сервере!**

**Время развертывания: ~5-10 минут** ⏱️ 
