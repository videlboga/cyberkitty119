# Telegram Bot API через VPN туннель

Данные скрипты позволяют запустить Telegram Bot API так, чтобы весь трафик маршрутизировался через WireGuard туннель в `vpnspace` неймспейсе.

## Почему это нужно?

Проблема: Прямые загрузки файлов из Telegram (особенно больших файлов) часто заканчиваются таймаутами, потому что:
- Telegram Bot API долго получает файлы с серверов Telegram
- Соединение может быть ограничено/фильтровано локальной сетью
- VPN туннель может помочь избежать этих ограничений

**Решение:** Маршрутизировать весь трафик telegram-bot-api через VPN туннель

## Проверка текущего состояния

```bash
# Проверить наличие vpnspace неймспейса
sudo ip netns list

# Проверить WireGuard туннель
sudo ip netns exec vpnspace ip link show wg0
sudo ip netns exec vpnspace ip addr show wg0

# Проверить маршруты в vpnspace
sudo ip netns exec vpnspace ip route show
```

Вывод должен показать:
```
16362: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP>
    inet 10.8.0.2/24 scope global wg0
default via 10.8.0.1 dev wg0
```

## Варианты запуска

### 1. ❌ Наивный подход (НЕ РАБОТАЕТ)
**Файл:** `run-telegram-vpn.sh`
```bash
./run-telegram-vpn.sh
```
Проблема: Docker daemon работает на хосте, контейнеры не могут быть напрямую в namespace

### 2. ⚠️  Промежуточный подход (Частичное решение)
**Файл:** `run-telegram-vpn-simple.sh`
```bash
./run-telegram-vpn-simple.sh [PORT]
./run-telegram-vpn-simple.sh 9082
```
- Запускает контейнер обычным способом
- Контейнер имеет доступ к NET_ADMIN capabilities
- Все же большинство трафика идёт через стандартную сеть хоста, а не через VPN

### 3. 🔄 Прокси-подход (Экспериментальный)
**Файл:** `run-telegram-vpn-proxy.sh`
```bash
./run-telegram-vpn-proxy.sh [PORT]
./run-telegram-vpn-proxy.sh 9082
```
- Запускает telegram-bot-api в контейнере
- Создаёт socat proxy для маршрутизации
- Требует дополнительной настройки iptables
- Статус: Требует завершения

### 4. ✅ РЕКОМЕНДУЕМЫЙ подход - Native процесс в VPN namespace
**Файл:** `run-telegram-bot-api-native-vpn.sh`
```bash
./run-telegram-bot-api-native-vpn.sh [PORT]
./run-telegram-bot-api-native-vpn.sh 9082
```

**Это лучший способ! Запускает telegram-bot-api как native процесс (без Docker) прямо в vpnspace.**

Преимущества:
- ✅ 100% трафика через VPN туннель
- ✅ Нет Docker overhead
- ✅ Простая отладка с помощью стандартных инструментов

## Настройка и запуск (Рекомендуемый метод)

### Шаг 1: Подготовка
```bash
cd /home/cyberkitty/Projects/Cyberkitty119

# Убедитесь, что vpnspace активен
sudo ip netns exec vpnspace ping -c 1 8.8.8.8

# Проверьте переменные окружения
grep TELEGRAM_API_ .env
```

### Шаг 2: Запуск telegram-bot-api в VPN namespace
```bash
# Запуск на порту 9082 (по умолчанию)
./run-telegram-bot-api-native-vpn.sh

# Или указать другой порт
./run-telegram-bot-api-native-vpn.sh 9085
```

Скрипт:
1. ✅ Проверит наличие vpnspace и WireGuard
2. ✅ Подготовит данные директорию
3. ✅ Запустит telegram-bot-api внутри vpnspace
4. ✅ Покажет локальный IP в VPN

### Шаг 3: Проверка
```bash
# Проверить, что процесс запущен в vpnspace
sudo ip netns exec vpnspace ps aux | grep telegram-bot-api

# Проверить логи
tail -f /var/lib/telegram-bot-api-vpn/server.log

# Проверить через HTTP API
curl http://localhost:9082/test/getMe
```

## Переключение Bot конфигурации

После запуска telegram-bot-api в VPN, нужно обновить конфигурацию бота:

### Вариант A: Обновить docker-compose.yml
```yaml
bot:
  environment:
    - LOCAL_BOT_API_URL=http://localhost:9082  # вместо telegram-bot-api:8081
```

Затем перезагрузить бот:
```bash
docker-compose down bot
docker-compose up -d bot
```

### Вариант B: Через .env переменную
```bash
# Добавить в .env
LOCAL_BOT_API_URL=http://localhost:9082
```

Затем:
```bash
docker-compose restart bot
```

## Мониторинг

### Проверить статус VPN туннеля
```bash
# Проверить IP в VPN (должен быть из VPN провайдера)
sudo ip netms exec vpnspace curl https://checkip.amazonaws.com

# Сравнить с локальным IP
curl https://checkip.amazonaws.com
```

### Отследить трафик в VPN
```bash
# Прослушать WireGuard интерфейс
sudo ip netns exec vpnspace tcpdump -i wg0 'host telegram'

# Или через ethtool
sudo ip netns exec vpnspace ethtool -S wg0
```

### Статус процесса
```bash
# Просмотр процесса в namespace
ps aux | grep telegram-bot-api

# Или напрямую в namespace
sudo ip netns exec vpnspace ps aux | grep telegram-bot-api
```

## Остановка

```bash
# Убить процесс telegram-bot-api в vpnspace
pkill -f telegram-bot-api

# Или более жёсткий способ
sudo ip netns exec vpnspace pkill -9 telegram-bot-api

# Очистить данные (если нужно начать с нуля)
sudo rm -rf /var/lib/telegram-bot-api-vpn/*
```

## Отладка

### Если скрипт падает с ошибкой binary not found

```bash
# Проверить наличие telegram-bot-api в системе
which telegram-bot-api

# Если не найден, установить:
apt-get install telegram-bot-api

# Или скомпилировать из исходников
git clone https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api
mkdir build
cd build
cmake ..
make
sudo make install
```

### Если нет доступа в VPN

```bash
# Проверить WireGuard статус
sudo ip netns exec vpnspace wg show

# Проверить DNS
sudo ip netns exec vpnspace cat /etc/resolv.conf

# Попробовать пинг
sudo ip netns exec vpnspace ping -c 3 8.8.8.8
```

### Если telegram-bot-api не слушает порт

```bash
# Проверить слушающие порты
sudo ip netns exec vpnspace netstat -tlnp | grep telegram

# Проверить логи
cat /var/lib/telegram-bot-api-vpn/server.log

# Попробовать запустить с verbose флагом
./run-telegram-bot-api-native-vpn.sh 9082 -- --verbosity=2
```

## Архитектура

```
Telegram Servers
      ↓
 [WireGuard Tunnel] ← 10.8.0.1 gateway
      ↓
[vpnspace namespace]
      ↓
telegram-bot-api (native process)
      ↓
      :9082 (exposed to host)
      ↓
Docker Network (cyberkitty19-transkribator-network)
      ↓
[bot container]
```

## Примечания

- Данный подход работает только если у вас правильно настроен VPN туннель в vpnspace
- Убедитесь, что WireGuard интерфейс поднят перед запуском
- Если туннель падает, telegram-bot-api потеряет доступ к интернету
- Для production рекомендуется использовать systemd unit или supervisor для автозагрузки
- При перезагрузке системы vpnspace может быть уничтожен, нужна переинициализация
