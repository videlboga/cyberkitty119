#!/bin/bash

# Проверка количества аргументов
if [ $# -ne 2 ]; then
    echo "Использование: $0 <путь_к_видео> <путь_к_аудио>"
    exit 1
fi

VIDEO_PATH="$1"
AUDIO_PATH="$2"
LOG_FILE="extract_audio_simple.log"

# Проверка наличия файла
if [ ! -f "$VIDEO_PATH" ]; then
    echo "$(date) - Ошибка: Видеофайл не найден: $VIDEO_PATH" >> "$LOG_FILE"
    exit 1
fi

# Создание директории для аудио, если не существует
mkdir -p "$(dirname "$AUDIO_PATH")"

echo "$(date) - Начинаю извлечение аудио из $VIDEO_PATH в $AUDIO_PATH" >> "$LOG_FILE"

# Запускаем ffmpeg напрямую
ffmpeg -i "$VIDEO_PATH" -vn -acodec pcm_s16le -ar 44100 -ac 2 -y "$AUDIO_PATH" 2>> "$LOG_FILE"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    if [ -f "$AUDIO_PATH" ] && [ -s "$AUDIO_PATH" ]; then
        SIZE=$(stat -c%s "$AUDIO_PATH")
        echo "$(date) - Аудио успешно извлечено. Размер файла: $SIZE байт" >> "$LOG_FILE"
        echo "SUCCESS" # Вывод для родительского процесса
        exit 0
    else
        echo "$(date) - Ошибка: Аудиофайл не создан или пуст" >> "$LOG_FILE"
        echo "FAIL" # Вывод для родительского процесса
        exit 1
    fi
else
    echo "$(date) - Ошибка: Процесс ffmpeg завершился с кодом $EXIT_CODE" >> "$LOG_FILE"
    echo "FAIL" # Вывод для родительского процесса
    exit 1
fi 