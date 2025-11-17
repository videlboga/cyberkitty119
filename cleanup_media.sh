#!/bin/bash

# Скрипт для удаления старых медиа-файлов из директорий audio и videos
# Удаляет файлы, которые старше 1 часа

# Установка переменных
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIO_DIR="${SCRIPT_DIR}/audio"
VIDEOS_DIR="${SCRIPT_DIR}/videos"
LOG_FILE="${SCRIPT_DIR}/cleanup_media.log"
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

# Функция логирования
log_message() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
    echo "[$TIMESTAMP] $1"
}

# Проверка существования директорий
if [ ! -d "$AUDIO_DIR" ]; then
    log_message "Директория аудио не найдена: $AUDIO_DIR"
    exit 1
fi

if [ ! -d "$VIDEOS_DIR" ]; then
    log_message "Директория видео не найдена: $VIDEOS_DIR"
    exit 1
fi

# Удаление старых файлов из директории аудио
log_message "Начало очистки директории аудио..."
OLD_AUDIO_FILES=$(find "$AUDIO_DIR" -type f -mmin +60 -not -path "*/\.*")
if [ -z "$OLD_AUDIO_FILES" ]; then
    log_message "Не найдено аудио-файлов старше 1 часа"
else
    AUDIO_COUNT=$(echo "$OLD_AUDIO_FILES" | wc -l)
    find "$AUDIO_DIR" -type f -mmin +60 -not -path "*/\.*" -delete
    log_message "Удалено $AUDIO_COUNT аудио-файлов старше 1 часа"
fi

# Удаление старых файлов из директории видео
log_message "Начало очистки директории видео..."
OLD_VIDEO_FILES=$(find "$VIDEOS_DIR" -type f -mmin +60 -not -path "*/\.*")
if [ -z "$OLD_VIDEO_FILES" ]; then
    log_message "Не найдено видео-файлов старше 1 часа"
else
    VIDEO_COUNT=$(echo "$OLD_VIDEO_FILES" | wc -l)
    find "$VIDEOS_DIR" -type f -mmin +60 -not -path "*/\.*" -delete
    log_message "Удалено $VIDEO_COUNT видео-файлов старше 1 часа"
fi

log_message "Очистка успешно завершена" 