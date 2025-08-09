#!/bin/bash

# Скрипт для запуска транскрибатора с WireGuard VPN

set -e

# Проверяем наличие WireGuard конфигурации
WG_CONFIG_PATH="./wg0.conf"
if [ ! -f "$WG_CONFIG_PATH" ]; then
    echo "Ошибка: WireGuard конфигурация не найдена по пути $WG_CONFIG_PATH"
    echo "Пожалуйста, поместите ваш WireGuard конфиг в файл wg0.conf в текущей директории"
    exit 1
fi

# Проверяем аргументы
if [ $# -eq 0 ]; then
    echo "Использование: $0 <путь_к_видеофайлу>"
    echo "Пример: $0 /home/cyberkitty/Videos/video1254700787.mp4"
    exit 1
fi

VIDEO_PATH="$1"

# Проверяем существование видеофайла
if [ ! -f "$VIDEO_PATH" ]; then
    echo "Ошибка: Видеофайл не найден: $VIDEO_PATH"
    exit 1
fi

echo "Собираем Docker образ с WireGuard..."
docker build -f Dockerfile.wireguard -t transkribator-wireguard .

echo "Запускаем контейнер с WireGuard VPN..."
echo "Видеофайл: $VIDEO_PATH"

# Запускаем контейнер с привилегиями для WireGuard
docker run --rm -it \
    --privileged \
    --cap-add=NET_ADMIN \
    --cap-add=SYS_MODULE \
    -v "$VIDEO_PATH:/input/video.mp4:ro" \
    -v "$(pwd)/wg0.conf:/etc/wireguard/wg0.conf:ro" \
    -v "$(pwd):/app/output" \
    transkribator-wireguard "/input/video.mp4"

echo "Готово! Результаты сохранены в текущей директории." 