#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv
import openai

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")

if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
    logger.error("Необходимо указать OPENROUTER_API_KEY и OPENROUTER_MODEL в .env файле!")
    sys.exit(1)

# Пути к директориям
VIDEOS_DIR = Path("videos")
TRANSCRIPTIONS_DIR = Path("transcriptions")

# Тестовый видеофайл
TEST_VIDEO_PATH = VIDEOS_DIR / "test_video.mp4"

# Словарь хранения транскрипций
user_transcriptions = {}
TEST_USER_ID = 123456789

# Для тестирования мы будем использовать небольшой фрагмент транскрипции
TEST_RAW_TRANSCRIPT = """
так пум пум делаем что-то такое create new avatar здесь вот он объясняет как это сделать ну ладно здесь рекорд new webcam Вот здесь Record your webcam. Разрешаем видео фото помпом и ставил так вот здесь мы значится записываем какое-то видео не очень понимаю что нужно Вот здесь мы, значит, записываем какое-то видео.
"""

async def format_transcript_chunk(client, chunk: str) -> str:
    """Обрабатывает один фрагмент транскрипции через OpenRouter API."""
    try:
        # Создаем запрос к модели
        prompt = f"""Твоя задача - отформатировать сырую транскрипцию видео, сделав её более читаемой. Требования:
1. НЕ МЕНЯЙ содержание и смысл.
2. Добавь правильную пунктуацию (точки, запятые, тире, знаки вопроса).
3. Раздели текст на логические абзацы там, где это уместно.
4. Исправь очевидные ошибки распознавания речи.
5. Убери лишние повторения слов и слова-паразиты (если это не меняет смысл).
6. Форматируй прямую речь с помощью кавычек или тире.

Вот сырая транскрипция, которую нужно отформатировать:

{chunk}"""

        # Отправляем запрос
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "Ты эксперт по обработке и форматированию транскрипций видео. Твоя задача - сделать сырую транскрипцию более читаемой, сохраняя при этом исходное содержание."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,  # Низкая температура для более детерминированных результатов
            max_tokens=4096
        )
        
        # Извлекаем ответ
        formatted_text = response.choices[0].message.content
        
        logger.info(f"Транскрипция успешно отформатирована (было {len(chunk)} символов, стало {len(formatted_text)} символов)")
        return formatted_text
        
    except Exception as e:
        logger.error(f"Ошибка при обработке части транскрипции: {e}")
        # В случае ошибки возвращаем исходный текст
        return chunk

async def format_transcript_with_llm(raw_transcript: str) -> str:
    """
    Форматирует сырую транскрипцию с помощью ЛЛМ через OpenRouter API.
    
    Преобразует сырой текст в более читаемый формат, добавляя пунктуацию и
    разделяя на абзацы, сохраняя при этом исходное содержание.
    
    Args:
        raw_transcript: Исходная сырая транскрипция от Whisper.
        
    Returns:
        Отформатированная транскрипция.
    """
    try:
        # Настраиваем клиент OpenAI для работы с OpenRouter
        client = openai.OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            # Добавляем необходимые заголовки для OpenRouter
            default_headers={
                "HTTP-Referer": "https://github.com/videlboga/cyberkitty119",  # Ваш домен
                "X-Title": "Transkribator Bot"  # Название вашего приложения
            }
        )
        
        # Если транскрипция слишком большая, разделим ее на части
        max_chunk_size = 15000
        if len(raw_transcript) > max_chunk_size:
            logger.info(f"Транскрипция слишком большая ({len(raw_transcript)} символов), разделяю на части")
            chunks = [raw_transcript[i:i+max_chunk_size] for i in range(0, len(raw_transcript), max_chunk_size)]
            formatted_chunks = []
            
            for i, chunk in enumerate(chunks):
                logger.info(f"Обрабатываю часть {i+1} из {len(chunks)}")
                formatted_chunk = await format_transcript_chunk(client, chunk)
                formatted_chunks.append(formatted_chunk)
                
            return "\n\n".join(formatted_chunks)
        else:
            return await format_transcript_chunk(client, raw_transcript)
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании транскрипции: {e}")
        # В случае ошибки возвращаем исходный текст
        return raw_transcript

async def simulate_process_video():
    """
    Симулирует процесс обработки видео и сохранения транскрипций.
    """
    print("Симуляция обработки видео...")
    print(f"Видеофайл: {TEST_VIDEO_PATH}")
    
    # Предполагаем, что транскрибация уже выполнена и у нас есть сырая транскрипция
    print("\nСимуляция получения сырой транскрипции...")
    raw_transcript = TEST_RAW_TRANSCRIPT
    print(f"Получена сырая транскрипция длиной {len(raw_transcript)} символов")
    
    # Форматируем транскрипцию с помощью ЛЛМ
    print("\nФорматирование транскрипции с помощью ЛЛМ...")
    formatted_transcript = await format_transcript_with_llm(raw_transcript)
    print(f"Получена форматированная транскрипция длиной {len(formatted_transcript)} символов")
    
    # Сохраняем форматированную транскрипцию
    transcript_path = TRANSCRIPTIONS_DIR / f"{TEST_VIDEO_PATH.stem}.txt"
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(formatted_transcript)
    print(f"Сохранена форматированная транскрипция в файл: {transcript_path}")
    
    # Сохраняем исходную транскрипцию для сравнения
    raw_transcript_path = TRANSCRIPTIONS_DIR / f"{TEST_VIDEO_PATH.stem}_raw.txt"
    with open(raw_transcript_path, "w", encoding="utf-8") as f:
        f.write(raw_transcript)
    print(f"Сохранена сырая транскрипция в файл: {raw_transcript_path}")
    
    # Сохраняем данные в словарь
    user_transcriptions[TEST_USER_ID] = {
        'raw': raw_transcript,
        'formatted': formatted_transcript,
        'path': str(transcript_path),
        'raw_path': str(raw_transcript_path),
        'timestamp': asyncio.get_event_loop().time()
    }
    print(f"Данные о транскрипциях сохранены в словарь для пользователя {TEST_USER_ID}")
    
    # Проверяем, что файлы созданы
    if transcript_path.exists():
        print(f"Файл с форматированной транскрипцией успешно создан.")
    else:
        print(f"Ошибка: файл с форматированной транскрипцией не создан!")
    
    if raw_transcript_path.exists():
        print(f"Файл с сырой транскрипцией успешно создан.")
    else:
        print(f"Ошибка: файл с сырой транскрипцией не создан!")
    
    # Симулируем получение сырой транскрипции через команду /rawtranscript
    print("\nСимуляция выполнения команды /rawtranscript...")
    
    if TEST_USER_ID not in user_transcriptions or 'raw' not in user_transcriptions[TEST_USER_ID]:
        print("Ошибка: транскрипция для пользователя не найдена")
    else:
        transcript_data = user_transcriptions[TEST_USER_ID]
        raw_transcript_from_dict = transcript_data['raw']
        print(f"Получена сырая транскрипция из словаря для пользователя {TEST_USER_ID}")
        
        if len(raw_transcript_from_dict) > 4000:
            # Если текст слишком длинный, в реальном боте отправляем файлом
            print("Сырая транскрипция слишком длинная, отправляем файлом...")
            # Проверяем наличие файла сырой транскрипции
            if 'raw_path' in transcript_data and Path(transcript_data['raw_path']).exists():
                raw_file_path = transcript_data['raw_path']
                print(f"Файл с сырой транскрипцией найден: {raw_file_path}")
            else:
                print("Файл с сырой транскрипцией не найден или не существует.")
        else:
            # Если текст короткий, просто выводим первые 100 символов
            print(f"Сырая транскрипция:\n{raw_transcript_from_dict[:100]}...")
    
    return transcript_path, raw_transcript_path

async def main():
    print("Тестирование процесса обработки видео и сохранения транскрипций")
    print("=" * 70)
    
    try:
        transcript_path, raw_transcript_path = await simulate_process_video()
        
        print("\nТестирование завершено! Очистка тестовых файлов...")
        
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
        
    except Exception as e:
        print(f"Ошибка при тестировании: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 