#!/bin/bash
# Запустить как root!
pkill -f "socat TCP-LISTEN:8000" || true
pkill -f "socat TCP-LISTEN:8081" || true
pkill -f "socat TCP-LISTEN:11900" || true
pkill -f "socat TCP-LISTEN:11981" || true

echo "Стартует прокси 11900 (API) из vpnspace на локалхост..."
nohup socat TCP-LISTEN:11900,bind=127.0.0.1,reuseaddr,fork EXEC:"ip netns exec vpnspace socat STDIO TCP4-CONNECT:127.0.0.1:8000" > /dev/null 2>&1 &

echo "Стартует прокси 11981 (Telegram Bot API) из vpnspace на локалхост..."
nohup socat TCP-LISTEN:11981,bind=127.0.0.1,reuseaddr,fork EXEC:"ip netns exec vpnspace socat STDIO TCP4-CONNECT:127.0.0.1:8081" > /dev/null 2>&1 &

echo "Прокси подняты!"
echo "Core API теперь доступно с хоста по адресу: http://127.0.0.1:11900"
echo "Telegram Bot API доступен по адресу: http://127.0.0.1:11981"
