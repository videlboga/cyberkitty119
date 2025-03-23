import whisper
import aiohttp
import json
from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL

async def transcribe_audio(audio_path, model_name="base"):
    """Транскрибирует аудио с помощью Whisper."""
    try:
        logger.info(f"Загрузка модели Whisper '{model_name}'...")
        model = whisper.load_model(model_name)
        
        logger.info(f"Транскрибация аудиофайла: {audio_path}")
        result = model.transcribe(str(audio_path))
        
        logger.info(f"Транскрипция завершена, получено {len(result['text'])} символов")
        return result["text"]
        
    except Exception as e:
        logger.error(f"Ошибка при транскрибации аудио: {e}")
        return None

async def format_transcript_with_llm(raw_transcript: str) -> str:
    """Форматирует транскрипцию с использованием языковой модели."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not raw_transcript or len(raw_transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для форматирования")
            return raw_transcript
            
        # Используем OpenRouter API для форматирования
        if OPENROUTER_API_KEY:
            formatted = await format_transcript_with_openrouter(raw_transcript)
            if formatted:
                return formatted
        
        # Формальное форматирование, если не удалось использовать LLM
        return raw_transcript
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании транскрипции: {e}")
        return raw_transcript

async def format_transcript_with_openrouter(raw_transcript: str) -> str:
    """Форматирует сырую транскрипцию с помощью OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        return None
        
    try:
        logger.info(f"Форматирование транскрипции с помощью OpenRouter API, модель: {OPENROUTER_MODEL}")
        
        # Создаем промпт для модели с более строгими инструкциями
        system_prompt = """Ты профессиональный редактор сырых транскрипций. 
        Твоя задача - полностью преобразовать сырую необработанную транскрипцию аудио в идеально читабельный текст.
        Ты должен быть очень внимательным к исправлению ошибок, очистке текста от лишних слов и созданию
        правильной структуры текста. Не должно оставаться заполнителей речи и повторений.
        Не добавляй собственные мысли или содержание, которого нет в исходном тексте."""
        
        user_prompt = f"""Вот сырая транскрипция аудио. Пожалуйста, отформатируй ее в идеально читабельный текст:

{raw_transcript}

Правила форматирования:
1. Тщательно исправь все ошибки распознавания, где они очевидны
2. Добавь правильную пунктуацию (точки, запятые, вопросительные и восклицательные знаки)
3. Разбей текст на логические предложения и абзацы
4. Полностью удали все повторы, заполнители речи (эээ, ммм, и т.д.) и слова-паразиты
5. Исправь грамматические ошибки и неправильные обороты речи
6. Сделай текст идеально читаемым, как будто это расшифровка профессионального интервью
7. Возвращай только отформатированный текст без дополнительных комментариев"""
        
        # Формируем запрос к API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1,  # Низкая температура для более детерминированных результатов
            "max_tokens": 4096
        }
        
        # Отправляем запрос
        async with aiohttp.ClientSession() as session:
            async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    formatted_text = data["choices"][0]["message"]["content"]
                    logger.info("Транскрипция успешно отформатирована с помощью OpenRouter API")
                    return formatted_text
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка от OpenRouter API: {response.status}, {error_text}")
                    return None
        
    except Exception as e:
        logger.error(f"Ошибка при форматировании транскрипции через OpenRouter API: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None 

async def generate_detailed_summary(transcript: str) -> str:
    """Генерирует подробное саммари транскрипции с использованием языковой модели."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для создания подробного саммари")
            return "Транскрипция слишком короткая для создания подробного саммари."
            
        # Используем OpenRouter API для генерации саммари
        if OPENROUTER_API_KEY:
            system_prompt = """Ты профессиональный аналитик, который создает подробные саммари на основе транскрипций разговоров, интервью и встреч.
            Твоя задача - внимательно проанализировать содержание текста и составить структурированное подробное резюме, 
            которое включает в себя основные темы обсуждения, ключевые точки зрения, принятые решения и план дальнейших действий."""
            
            user_prompt = f"""Вот транскрипция встречи/разговора. Пожалуйста, создай подробное саммари:

{transcript}

В твоем саммари обязательно должны быть следующие разделы:
1. Основные обсуждаемые темы (с деталями по каждой теме)
2. Ключевые точки зрения и аргументы участников
3. Принятые решения (если таковые имеются)
4. Дальнейшие шаги и задачи (если таковые обсуждались)

Саммари должно быть содержательным, информативным, но при этом структурированным и понятным."""
            
            return await request_llm_response(system_prompt, user_prompt)
        
        return "Не удалось создать подробное саммари. Проверьте настройки API для языковой модели."
            
    except Exception as e:
        logger.error(f"Ошибка при создании подробного саммари: {e}")
        return f"Произошла ошибка при создании подробного саммари: {str(e)}"

async def generate_brief_summary(transcript: str) -> str:
    """Генерирует краткое саммари транскрипции с использованием языковой модели."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для создания краткого саммари")
            return "Транскрипция слишком короткая для создания краткого саммари."
            
        # Используем OpenRouter API для генерации саммари
        if OPENROUTER_API_KEY:
            system_prompt = """Ты профессиональный аналитик, который создает краткие, лаконичные саммари на основе транскрипций разговоров.
            Твоя задача - вычленить самую важную информацию и представить ее в максимально сжатом виде, сохраняя все 
            ключевые моменты, решения и дальнейшие шаги."""
            
            user_prompt = f"""Вот транскрипция встречи/разговора. Пожалуйста, создай очень краткое саммари (не более 300 слов):

{transcript}

В твоем кратком саммари обязательно должны быть указаны:
1. Главные обсуждаемые темы (очень кратко)
2. Принятые решения (если таковые имеются)
3. Дальнейшие шаги (если таковые обсуждались)

Саммари должно быть максимально коротким, но при этом информативным."""
            
            return await request_llm_response(system_prompt, user_prompt)
        
        return "Не удалось создать краткое саммари. Проверьте настройки API для языковой модели."
            
    except Exception as e:
        logger.error(f"Ошибка при создании краткого саммари: {e}")
        return f"Произошла ошибка при создании краткого саммари: {str(e)}"

async def request_llm_response(system_prompt: str, user_prompt: str) -> str:
    """Общая функция для отправки запросов к LLM через OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        return None
        
    try:
        # Формируем запрос к API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4096
        }
        
        # Отправляем запрос
        async with aiohttp.ClientSession() as session:
            async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    result_text = data["choices"][0]["message"]["content"]
                    logger.info("Успешно получен ответ от LLM через OpenRouter API")
                    return result_text
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка от OpenRouter API: {response.status}, {error_text}")
                    return None
        
    except Exception as e:
        logger.error(f"Ошибка при запросе к OpenRouter API: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None 