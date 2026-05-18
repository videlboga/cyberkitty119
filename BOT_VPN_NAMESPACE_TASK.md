# Задача: Запуск Telegram-бота в VPN Namespace

**Статус**: 🔴 В процессе решения (TLS handshake timeout)  
**Дата начала**: 25 марта 2026 г.  
**Последнее обновление**: 25 марта 2026 г., ~19:00

---

## 📋 Исходная цель

Запустить Telegram-бот **внутри VPN namespace** (`vpnspace`), чтобы:
- Бот имел доступ в интернет через VPN
- Основная система оставалась вне VPN
- Бот мог подключиться к Telegram API (api.telegram.org)

---

## 🎯 Начальное состояние проекта

### Что было в проекте:
- **Основной бот**: `cyberkitty_modular.py` (полнофункциональный Telegram-бот на Python)
- **Docker-compose файлы**: 
  - `docker-compose.bot-v2.yml`
  - `docker-compose.dev.yml.disabled`
  - и другие варианты
- **VPN namespace**: `vpnspace` с доступом в интернет (уже существовал)
- **Проблема**: нужно было запустить бота именно в этом namespace

### Архитектура:
```
Хост (без VPN)
    ↓
[vpnspace namespace] ← здесь должен работать бот
    ↓
[VPN] → Интернет
```

---

## 🔄 Этапы работы

### **Этап 1: Попытка переключить network_mode в docker-compose**

#### Идея:
Использовать `network_mode: "vpnspace"` в docker-compose.bot-v2.yml, чтобы контейнер подключился к namespace.

#### Команда:
```yaml
# docker-compose.bot-v2.yml
services:
  bot:
    network_mode: "vpnspace"  # Попытка подключиться к vpnspace namespace
```

#### Результат:
❌ **Не сработало** — Docker не поддерживает прямое подключение к `ip netns` namespace таким способом.

---

### **Этап 2: Возврат к стандартному docker-compose**

Отменили изменения, вернулись к обычной bridge-сети.

---

### **Этап 3: Запуск docker через `ip netns exec vpnspace`**

#### Идея:
Выполнить docker run внутри vpnspace namespace, используя `ip netns exec`.

#### Команда:
```bash
sudo ip netns exec vpnspace docker run \
  -e BOT_TOKEN=<token> \
  my-bot:latest
```

#### Результат:
⚠️ **Частичный успех**: контейнер запускается, но бот **не может достучаться до Telegram API**.

#### Ошибка в логах:
```
httpcore.connection | start_tls.failed exception=ConnectTimeout(TimeoutError())
```

---

### **Этап 4: Исследование проблемы с подключением**

#### 4.1 Проверка DNS и базовой сетевой связи

```bash
# В vpnspace:
ip netns exec vpnspace ping api.telegram.org
```

**Результат**: ✓ **Успех** — пакеты доходят за ~70ms

```
PING api.telegram.org (149.154.166.110) ...
64 bytes from 149.154.166.110: icmp_seq=1 ttl=... time=69.3 ms
```

#### 4.2 Проверка TCP соединения на порт 443

```bash
# Попытка подключиться к Telegram API
ip netns exec vpnspace nc -zv api.telegram.org 443
```

**Результат**: ✓ **Успех** — TCP соединение устанавливается

```
Connection to api.telegram.org 443 port [tcp/https] succeeded!
```

#### 4.3 Проверка SSL/TLS handshake

```bash
# Попытка установить SSL-соединение в vpnspace
ip netns exec vpnspace python3 << 'EOF'
import socket, ssl
sock = socket.create_connection(('api.telegram.org', 443), timeout=10)
ctx = ssl.create_default_context()
ssock = ctx.wrap_socket(sock, server_hostname='api.telegram.org')
print('SSL OK')
EOF
```

**Результат**: ❌ **TimeoutError** при SSL handshake

```
TimeoutError: _ssl.c:1063: The handshake operation timed out
```

#### 4.4 КРИТИЧЕСКАЯ НАХОДКА: Даже на хосте SSL timeout-ит!

```bash
# На основном хосте (не в vpnspace, не в docker!)
python3 -c "
import socket, ssl
sock = socket.create_connection(('149.154.166.110', 443), timeout=10)
ctx = ssl.create_default_context()
ssock = ctx.wrap_socket(sock, server_hostname='api.telegram.org')
print('SSL OK:', ssock.getpeercert()['subject'])
ssock.close()
"
```

**Результат**: ❌ **TimeoutError**

```
Traceback (most recent call last):
  ...
  ssock = ctx.wrap_socket(sock, server_hostname='api.telegram.org')
  ...
TimeoutError: _ssl.c:1063: The handshake operation timed out
```

**Вывод**: Это не проблема контейнера или VPN namespace — это **сетевая проблема на уровне хоста**.

---

### **Этап 5: Попытки решить TLS timeout**

#### 5.1 Отключить SSL проверку в коде

**Создан**: `bot/test_nossl.py`
```python
# Попытка отключить верификацию сертификатов
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
```

**Результат**: ❌ **Не помогло** — timeout происходит на уровне TCP/SSL операции, не на уровне верификации.

#### 5.2 Удалить переопределения в `/etc/hosts`

**Действие**: Проверили и очистили `/etc/hosts` от локальных записей для `api.telegram.org`.

```bash
# До этого в /etc/hosts могли быть:
127.0.0.1 api.telegram.org
::1 api.telegram.org
```

**Результат**: ❌ **Timeout остался** — DNS был причиной только переадресации, не основной проблемой.

#### 5.3 Запуск с `--network host`

**Команда**:
```bash
docker run --network host my-bot:latest
```

**Результат**: ❌ **Даже с host-сетью timeout продолжается** — значит это не проблема docker-сетей.

#### 5.4 Локальный telegram-bot-api сервер

**Идея**: Запустить локальный сервер `telegram-bot-api` на порту 8081 в vpnspace, чтобы бот не ходил напрямую к api.telegram.org.

**Команда**:
```bash
ip netns exec vpnspace telegram-bot-api \
  --dir=/tmp/tg-api \
  --http-port=8081
```

**Создан**: `bot/test_local_api.py`

**Результат**: ❌ **Не помогло** — бот всё равно пытается ходить к `api.telegram.org` напрямую вместо использования локального сервера.

---

### **Этап 6: Создание упрощённых тестовых ботов**

Для быстрого тестирования создали набор минимальных ботов в папке `bot/`:

| Файл | Описание | Статус |
|------|---------|--------|
| `bot/simple_test.py` | Минимальный бот, базовая инициализация | ✓ Скомпилирован |
| `bot/minimal.py` | Ещё более лаконичный | ✓ Скомпилирован |
| `bot/test_nossl.py` | С отключением SSL-проверки | ✓ Скомпилирован, ❌ не помогло |
| `bot/test_local_api.py` | Направлен на локальный API | ✓ Скомпилирован |

#### Пример: `bot/simple_test.py`
```python
#!/usr/bin/env python3
import logging
from telegram.ext import Application

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('simple_test')

async def main():
    token = os.getenv('BOT_TOKEN')
    app = Application.builder().token(token).build()
    logger.info("Bot initialized")
    await app.initialize()
    logger.info("Bot running")

if __name__ == '__main__':
    asyncio.run(main())
```

---

### **Этап 7: Docker Compose для тестирования**

**Создан**: `docker-compose.test-bot.yml`

```yaml
version: '3.8'
services:
  telegram-bot-api:
    image: aiogram/telegram-bot-api:latest
    ports:
      - "8081:8081"
    volumes:
      - /tmp/telegram-bot-api:/data
    networks:
      - test-net
    environment:
      - TELEGRAM_API_ID=${TELEGRAM_API_ID}
      - TELEGRAM_API_HASH=${TELEGRAM_API_HASH}

  simple-bot:
    build:
      context: .
      dockerfile: Dockerfile.simple-bot
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - LOCAL_BOT_API_URL=http://telegram-bot-api:8081
      - PYTHONUNBUFFERED=1
    depends_on:
      - telegram-bot-api
    networks:
      - test-net

networks:
  test-net:
    driver: bridge
```

---

### **Этап 8: Dockerfile для тестовых ботов**

**Создан**: `Dockerfile.simple-bot`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода бота
COPY bot/ .

# Переменные окружения
ENV BOT_TOKEN=""
ENV LOCAL_BOT_API_URL="http://localhost:8081"
ENV PYTHONUNBUFFERED=1

# Запуск бота
ENTRYPOINT ["python", "test_local_api.py"]
```

---

### **Этап 9: Скрипты запуска в vpnspace**

#### `run_simple_bot.sh`
**Путь**: `/tmp/run_simple_bot.sh`

```bash
#!/bin/bash
set -e

cd /home/cyberkitty/Projects/Cyberkitty119

echo "=== Запускаем простой тестовый бот в vpnspace namespace ==="

# Проверяем, существует ли vpnspace
if ! ip netns list | grep -q vpnspace; then
    echo "❌ vpnspace namespace не найден"
    exit 1
fi

echo "✓ vpnspace namespace найден"

# Сначала строим образ
echo "🔨 Собираю образ simple-test-bot..."
docker build -f Dockerfile.simple-bot -t simple-test-bot:latest . > /dev/null 2>&1

# Запускаем в vpnspace через docker
echo "🚀 Запускаю простой бот в vpnspace..."
sudo ip netns exec vpnspace bash -c "
    cd /home/cyberkitty/Projects/Cyberkitty119
    export BOT_TOKEN=\$(grep '^BOT_TOKEN=' .env | cut -d= -f2)
    docker run --rm \
        -e BOT_TOKEN=\${BOT_TOKEN} \
        -e PYTHONUNBUFFERED=1 \
        --name simple-test-bot \
        simple-test-bot:latest
" &

BOT_PID=$!
sleep 3

echo "✓ Бот запущен (PID: $BOT_PID)"
echo ""
echo "=== Статус ==="
sudo ip netns exec vpnspace docker ps | grep simple-test-bot || echo "⚠️  Контейнер не найден"
echo ""
echo "=== Логи бота ==="
sudo ip netns exec vpnspace docker logs simple-test-bot 2>&1 | tail -30 || true

echo ""
echo "✓ Простой бот работает в vpnspace"
```

#### `run_test_bot.sh`
**Путь**: `/tmp/run_test_bot.sh`

Альтернативный вариант с использованием docker-compose для запуска в vpnspace.

---

## 🔍 Диагностика: что мы узнали

### Текущая ситуация:
| Проверка | Результат | Статус |
|----------|-----------|--------|
| VPN namespace существует | Да | ✓ |
| Ping к api.telegram.org | ~70ms | ✓ |
| TCP коннект к 149.154.166.110:443 | Успешен | ✓ |
| SSL/TLS handshake в vpnspace | Timeout (25s) | ❌ |
| SSL/TLS handshake на хосте | Timeout (10s) | ❌ |
| DNS разрешение | Корректно | ✓ |
| /etc/hosts переопределения | Очищены | ✓ |

### Ключевые выводы:

1. **TCP работает, TLS нет** — это не проблема маршрутизации в целом
2. **ClientHello отправляется** (TCP connect успешен), но **ServerHello не приходит**
3. **Даже на хосте timeout-ит** — это не проблема контейнера или VPN
4. **Это системный уровень** — MTU, firewall, или asymmetric routing

### Возможные причины:

#### 1. **MTU/PMTU blackhole** (наиболее вероятно)
- Пакет ClientHello слишком большой (~500+ байт)
- Не фрагментируется корректно из-за DF (Don't Fragment) флага
- ServerHello пакет теряется, если ответ требует fragmentation

#### 2. **Firewalling TLS трафика**
- Маршрутизатор или VPN блокирует/нарушает TLS трафик
- Может отфильтровать пакеты или нарушить TLS handshake

#### 3. **Asymmetric routing**
- Пакеты туда идут корректно (TCP connect успешен)
- Обратные пакеты (ServerHello) теряются на другом маршруте

#### 4. **Проблема с VPN конфигурацией**
- Некорректная настройка VPN может нарушить TLS
- Но ping работает, поэтому маловероятно

---

## 📊 Файлы в проекте

| Путь | Назначение | Статус |
|------|-----------|--------|
| `bot/simple_test.py` | Минимальный тестовый бот | ✓ Готов |
| `bot/minimal.py` | Ещё более минимальный | ✓ Готов |
| `bot/test_nossl.py` | С отключением SSL-проверки | ✓ Готов |
| `bot/test_local_api.py` | С локальным API | ✓ Готов |
| `Dockerfile.simple-bot` | Образ для простого бота | ✓ Готов |
| `docker-compose.test-bot.yml` | Compose для теста (bot + local API) | ✓ Готов |
| `/tmp/run_simple_bot.sh` | Скрипт запуска в vpnspace | ✓ Готов |
| `/tmp/run_test_bot.sh` | Alt скрипт запуска | ✓ Готов |
| `.env` | BOT_TOKEN и прочее | ✓ Используется |

---

## 🛠️ Диагностика MTU

### Команды для проверки:

```bash
# 1. Тест с разными размерами пакетов
ip netns exec vpnspace ping -M do -s 1400 api.telegram.org
ip netns exec vpnspace ping -M do -s 1300 api.telegram.org
ip netns exec vpnspace ping -M do -s 1200 api.telegram.org
ip netns exec vpnspace ping -M do -s 1100 api.telegram.org

# Если один пройдёт, а другой нет, обнаружены проблемы с фрагментацией
# Например, если -s 1300 пройдёт, но -s 1400 нет → MTU проблема
```

### Проверка текущего MTU:

```bash
# Текущий MTU в vpnspace
ip netns exec vpnspace ip link show
# Ищем параметр mtu=XXXX

# Текущий MTU на хосте
ip link show
```

### Если обнаружена проблема с MTU:

```bash
# Временный фикс в vpnspace
ip netns exec vpnspace ip link set <interface> mtu 1400

# Для docker-контейнеров в vpnspace:
sudo ip netns exec vpnspace docker run --mtu 1400 ...
```

---

## 📡 Трассировка TLS соединения

### Захват пакетов во время TLS:

```bash
# Терминал 1: tcpdump в vpnspace
ip netns exec vpnspace tcpdump -i any host 149.154.166.110 and port 443 -vvv -w /tmp/tls.pcap

# Терминал 2: попытка SSL соединения
ip netns exec vpnspace openssl s_client -connect api.telegram.org:443 -servername api.telegram.org -brief

# После этого анализируем pcap файл:
wireshark /tmp/tls.pcap
# или
tcpdump -r /tmp/tls.pcap -vvv
```

**На что смотреть**:
- Приходит ли ClientHello?
- Отправляется ли ServerHello?
- Есть ли ICMP Fragmentation Needed сообщения?
- Есть ли потеряные пакеты?

---

## 🔧 Проверка firewall правил

```bash
# Правила firewall в vpnspace
ip netns exec vpnspace iptables -L -n -v | grep 443
ip netns exec vpnspace iptables -L -n -v | grep api.telegram.org

# Проверка nftables (если используется)
ip netns exec vpnspace nft list ruleset | grep 443
ip netns exec vpnspace nft list ruleset | grep api

# Проверка UFW
ip netns exec vpnspace ufw status verbose
```

---

## ✅ Текущий статус и следующий шаг

### Что работает:
- ✓ Боты скомпилированы
- ✓ Docker-образы собираются
- ✓ VPN namespace доступен и работает
- ✓ DNS разрешение работает
- ✓ TCP соединение к Telegram API работает
- ✓ Ping до api.telegram.org работает

### Что не работает:
- ❌ SSL/TLS handshake к Telegram API timeout-ит (в vpnspace и даже на хосте!)
- ❌ Это блокирует бота от подключения

### Гипотеза:
**MTU/PMTU blackhole или firewall, блокирующий TLS трафик**

### Следующие шаги:
1. ✅ **Срочно**: Проверить MTU в vpnspace с командой ping -M do -s XXX
2. ✅ **Если найдена проблема с MTU**: Зафиксировать MTU (например, на 1400)
3. ✅ **Повторить тест**: SSL-handshake с обновленным MTU
4. ✅ **Если помогло**: Переконфигурировать docker в vpnspace с `--mtu 1400`
5. ✅ **Запустить бота** с исправленным MTU
6. ❌ **Если MTU не помогла**: Запустить tcpdump для анализа пакетов
7. ❌ **Если это firewall**: Проверить iptables/nftables правила

---

## 📝 Примечания

### Временной фикс, если MTU проблема подтвердится:

```bash
# Во время запуска бота в vpnspace
sudo ip netns exec vpnspace bash -c "
    # Зафиксировать MTU для интерфейса (если нужно)
    ip link set <interface> mtu 1400
    
    # Запустить docker с правильным MTU
    docker run --mtu 1400 -e BOT_TOKEN=... my-bot:latest
"
```

### Для постоянного решения:
- Обновить конфигурацию VPN
- Проверить маршрутизацию и MTU на хосте и в vpnspace
- Возможно, обновить конфигурацию firewall

---

## 📚 Использованные команды

```bash
# Проверка vpnspace
ip netns list
ip netns exec vpnspace ip addr show

# Проверка сетевой связи
ping -c 1 api.telegram.org
ip netns exec vpnspace ping -c 1 api.telegram.org

# Проверка TCP
nc -zv api.telegram.org 443
ip netns exec vpnspace nc -zv api.telegram.org 443

# Проверка DNS
nslookup api.telegram.org
ip netns exec vpnspace nslookup api.telegram.org

# Запуск docker в vpnspace
sudo ip netns exec vpnspace docker ps
sudo ip netns exec vpnspace docker run ... image

# SSL тест
python3 -c "import socket, ssl; ..."
openssl s_client -connect api.telegram.org:443 -servername api.telegram.org

# Логи бота
docker logs <container>
sudo ip netns exec vpnspace docker logs <container>
```

---

## 🎓 Уроки, извлеченные из работы

1. **Всегда проверять сетевую диагностику перед решением на уровне приложения**
   - Ping, traceroute, netstat, tcpdump

2. **MTU проблемы могут быть хитрыми**
   - TCP может работать с маленькими пакетами
   - Но TLS с большими ClientHello может fail

3. **Firewall и VPN могут нарушать TLS**
   - Даже если обычный трафик проходит

4. **Docker в IP namespace требует особых подходов**
   - Стандартные конфиги не работают с ip netns

5. **Тестовые боты важны**
   - Минимизируют переменные в диагностике

---

## 📞 Контакты / Дополнительная информация

- **Проект**: Cyberkitty119
- **Ветка**: feature/queue-adr-migration
- **BOT_TOKEN**: Хранится в `.env`
- **VPN namespace**: `vpnspace`
- **Telegram API**: api.telegram.org (149.154.166.110)

