#!/bin/bash

# Скрипт для запуска API сервера транскрибатора с WireGuard VPN

set -e

# Проверяем наличие WireGuard конфигурации
WG_CONFIG_PATH="./wg0.conf"
if [ ! -f "$WG_CONFIG_PATH" ]; then
    echo "Предупреждение: WireGuard конфигурация не найдена по пути $WG_CONFIG_PATH"
    echo "API будет работать без VPN"
fi

echo "Собираем Docker образ API сервера с WireGuard..."
docker build -f Dockerfile.api_new -t transkribator-api .

echo "Запускаем API сервер..."
echo "API будет доступен по адресу: http://localhost:8000"
echo "Документация API: http://localhost:8000/docs"

# Запускаем контейнер с привилегиями для WireGuard
if [ -f "$WG_CONFIG_PATH" ]; then
    echo "Запускаем с WireGuard VPN..."
    docker run --rm -it \
        --privileged \
        --cap-add=NET_ADMIN \
        --cap-add=SYS_MODULE \
        -p 8000:8000 \
        -v "$(pwd)/wg0.conf:/etc/wireguard/wg0.conf:ro" \
        transkribator-api
else
    echo "Запускаем без VPN..."
    docker run --rm -it \
        -p 8000:8000 \
        transkribator-api
fi 