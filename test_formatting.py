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

# Тестовая сырая транскрипция
TEST_TRANSCRIPT = """
так пум пум делаем что-то такое create new avatar здесь вот он объясняет как это сделать ну ладно здесь рекорд new webcam Вот здесь Record your webcam. Разрешаем видео фото помпом и ставил так вот здесь мы значится записываем какое-то видео не очень понимаю что нужно Вот здесь мы, значит, записываем какое-то видео. Не очень понимаю, что нужно говорить, но давайте будем что-то говорить. Можно, наверное, махать руками, потому что он будет еще и жесты использовать
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

async def main():
    print("Тестирование форматирования транскрипций через OpenRouter API")
    print("=" * 70)
    print("Исходная транскрипция:")
    print("-" * 70)
    print(TEST_TRANSCRIPT)
    print("-" * 70)
    
    print("\nФорматирую транскрипцию...")
    formatted = await format_transcript_with_llm(TEST_TRANSCRIPT)
    
    print("\nОтформатированная транскрипция:")
    print("-" * 70)
    print(formatted)
    print("-" * 70)
    
    print("\nТестирование завершено!")

if __name__ == "__main__":
    asyncio.run(main()) 