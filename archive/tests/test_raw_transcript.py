#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Путь к директории с транскрипциями
TRANSCRIPTIONS_DIR = Path("transcriptions")

# Пример словаря хранения транскрипций
user_transcriptions = {}

# Тестовые данные
TEST_USER_ID = 123456789
TEST_RAW_TRANSCRIPT = """
так пум пум делаем что-то такое create new avatar здесь вот он объясняет как это сделать ну ладно здесь рекорд new webcam Вот здесь Record your webcam. Разрешаем видео фото помпом и ставил так вот здесь мы значится записываем какое-то видео не очень понимаю что нужно Вот здесь мы, значит, записываем какое-то видео. Не очень понимаю, что нужно говорить, но давайте будем что-то говорить. Можно, наверное, махать руками, потому что он будет еще и жесты использовать
"""
TEST_FORMATTED_TRANSCRIPT = """
Создаем новый аватар. Вот здесь объясняется, как это сделать. Ну ладно, здесь выбираем "Record new webcam".

Появилось сообщение: "Record your webcam". Разрешаем доступ к видео и фото, нажимаем "ОК". 

Теперь мы записываем какое-то видео. Не очень понимаю, что нужно говорить, но давайте будем что-то говорить. Можно, наверное, махать руками, потому что программа будет использовать жесты.
"""

def test_save_raw_transcript():
    """Тестирует сохранение сырой транскрипции на диск."""
    # Генерируем имена файлов
    video_filename = f"test_video_{TEST_USER_ID}"
    transcript_path = TRANSCRIPTIONS_DIR / f"{video_filename}.txt"
    raw_transcript_path = TRANSCRIPTIONS_DIR / f"{video_filename}_raw.txt"
    
    # Сохраняем форматированную транскрипцию
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(TEST_FORMATTED_TRANSCRIPT)
    
    print(f"Сохранена форматированная транскрипция в файл: {transcript_path}")
    
    # Сохраняем исходную транскрипцию для сравнения
    with open(raw_transcript_path, "w", encoding="utf-8") as f:
        f.write(TEST_RAW_TRANSCRIPT)
    
    print(f"Сохранена сырая транскрипция в файл: {raw_transcript_path}")
    
    # Сохраняем транскрипции для пользователя в словарь
    user_transcriptions[TEST_USER_ID] = {
        'raw': TEST_RAW_TRANSCRIPT,
        'formatted': TEST_FORMATTED_TRANSCRIPT,
        'path': str(transcript_path),
        'raw_path': str(raw_transcript_path),
        'timestamp': asyncio.get_event_loop().time()
    }
    
    print(f"Данные о транскрипциях сохранены в словарь для пользователя {TEST_USER_ID}")
    return transcript_path, raw_transcript_path

def test_retrieve_raw_transcript():
    """Тестирует получение сырой транскрипции из словаря."""
    if TEST_USER_ID not in user_transcriptions or 'raw' not in user_transcriptions[TEST_USER_ID]:
        print("Ошибка: транскрипция для пользователя не найдена")
        return None
    
    transcript_data = user_transcriptions[TEST_USER_ID]
    raw_transcript = transcript_data['raw']
    
    print(f"Получена сырая транскрипция из словаря для пользователя {TEST_USER_ID}")
    
    # Проверяем наличие файла сырой транскрипции
    if 'raw_path' in transcript_data and Path(transcript_data['raw_path']).exists():
        file_path = transcript_data['raw_path']
        print(f"Найден файл с сырой транскрипцией: {file_path}")
        
        # Читаем содержимое для проверки
        with open(file_path, "r", encoding="utf-8") as f:
            file_content = f.read()
        
        # Проверяем, совпадает ли содержимое файла с данными в словаре
        if file_content == raw_transcript:
            print("Содержимое файла совпадает с данными в словаре.")
        else:
            print("Содержимое файла НЕ совпадает с данными в словаре!")
    else:
        print("Файл с сырой транскрипцией не найден или не существует.")
    
    return raw_transcript

def main():
    print("Тестирование сохранения и извлечения сырых транскрипций")
    print("=" * 70)
    
    print("\n1. Сохранение транскрипций:")
    print("-" * 70)
    transcript_path, raw_transcript_path = test_save_raw_transcript()
    
    print("\n2. Извлечение сырой транскрипции:")
    print("-" * 70)
    raw_transcript = test_retrieve_raw_transcript()
    
    print("\n3. Очистка тестовых файлов:")
    print("-" * 70)
    # Удаляем тестовые файлы
    try:
        os.remove(transcript_path)
        print(f"Удален файл: {transcript_path}")
    except Exception as e:
        print(f"Не удалось удалить файл {transcript_path}: {e}")
    
    try:
        os.remove(raw_transcript_path)
        print(f"Удален файл: {raw_transcript_path}")
    except Exception as e:
        print(f"Не удалось удалить файл {raw_transcript_path}: {e}")
    
    print("\nТестирование завершено!")

if __name__ == "__main__":
    main() 