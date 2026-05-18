#!/bin/bash
echo "Устанавливаю socat-прокси между хостом 127.0.0.1 и vpnspace..."
# Убиваем старые
pkill -f "socat TCP-LISTEN:8000"
pkill -f "socat TCP-LISTEN:8081"
# Поднимаем новые
nohup socat TCP-LISTEN:8000,bind=127.0.0.1,reuseaddr,fork EXEC:"ip netns exec vpnspace socat STDIO TCP4-CONNECT:127.0.0.1:8000" > /dev/null 2>&1 &
nohup socat TCP-LISTEN:8081,bind=127.0.0.1,reuseaddr,fork EXEC:"ip netns exec vpnspace socat STDIO TCP4-CONNECT:127.0.0.1:8081" > /dev/null 2>&1 &
echo "Прокси TCP-LISTEN подняты."
