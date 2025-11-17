#!/bin/bash

# Запускаем WireGuard
wg-quick up /etc/wireguard/wg0.conf
sleep 5

# Настраиваем DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf

# Проверяем IP
echo "IP адрес:"
curl -s https://ipinfo.io/ip
echo

# Тестируем доступность DeepInfra API
echo "Тестируем DeepInfra API:"
curl -v -X POST https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo \
  -H "Authorization: Bearer $DEEPINFRA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}' \
  --max-time 30 