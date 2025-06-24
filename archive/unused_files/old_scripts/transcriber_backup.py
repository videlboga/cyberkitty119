try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    whisper = None

import aiohttp
import json
import os
import asyncio
from pathlib import Path
from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL, DEEPINFRA_API_KEY

async def compress_audio_for_api(audio_path):
    """Сжимает аудиофайл для отправки в API, уменьшая размер."""
    try:
        audio_path = Path(audio_path)
        compressed_path = audio_path.parent / f"{audio_path.stem}_compressed.mp3"
        
        logger.info(f"Сжимаю аудиофайл: {audio_path} -> {compressed_path}")
        
        # Команда для сжатия в MP3 с очень низким битрейтом
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-acodec', 'mp3',
            '-b:a', '32k',  # Очень низкий битрейт для максимального сжатия
            '-ar', '8000',  # Еще больше уменьшаем частоту дискретизации
            '-ac', '1',  # Моно канал
            '-y',
            str(compressed_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Ошибка при сжатии аудио: {stderr.decode()}")
            return str(audio_path)  # Возвращаем оригинальный файл при ошибке
        
        if compressed_path.exists() and compressed_path.stat().st_size > 0:
            original_size = audio_path.stat().st_size
            compressed_size = compressed_path.stat().st_size
            compression_ratio = (1 - compressed_size / original_size) * 100
            logger.info(f"Аудио сжато: {original_size} -> {compressed_size} байт (сжатие {compression_ratio:.1f}%)")
            return str(compressed_path)
        else:
            logger.warning("Сжатый файл не создался, используем оригинал")
            return str(audio_path)
            
    except Exception as e:
        logger.error(f"Ошибка при сжатии аудио: {e}")
        return str(audio_path)  # Возвращаем оригинальный файл при ошибке

async def transcribe_audio_with_deepinfra(audio_path):
    """Транскрибирует аудио с помощью DeepInfra Whisper API."""
    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен")
        return None
        
    try:
        logger.info(f"Транскрибация аудиофайла через DeepInfra API: {audio_path}")
        
        # Сначала сжимаем аудио для уменьшения размера
        compressed_audio_path = await compress_audio_for_api(audio_path)
        
        # DeepInfra API для Whisper
        url = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"
        
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
        }
        
        # Читаем сжатый аудио файл
        with open(compressed_audio_path, 'rb') as audio_file:
            # Увеличиваем таймаут для больших файлов
            timeout = aiohttp.ClientTimeout(total=600)  # 10 минут таймаут
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Формируем multipart/form-data запрос согласно документации DeepInfra
                form_data = aiohttp.FormData()
                file_name = Path(compressed_audio_path).name
                form_data.add_field('audio', audio_file, filename=file_name)
                
                async with session.post(url, headers=headers, data=form_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcript_text = result.get('text', '')
                        logger.info(f"Транскрибация через DeepInfra завершена, получено {len(transcript_text)} символов")
                        
                        # Удаляем сжатый файл, если он отличается от оригинала
                        if compressed_audio_path != audio_path:
                            try:
                                os.remove(compressed_audio_path)
                                logger.info("Сжатый временный файл удален")
                            except:
                                pass
                        
                        return transcript_text
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка от DeepInfra API: {response.status}, {error_text}")
                        return None
        
    except Exception as e:
        logger.error(f"Ошибка при транскрибации аудио через DeepInfra API: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def transcribe_audio(audio_path, model_name="base"):
    """Транскрибирует аудио с помощью DeepInfra API или локальным Whisper."""
    
    # Сначала пробуем DeepInfra API, если ключ доступен
    if DEEPINFRA_API_KEY:
        logger.info("Использую DeepInfra API для транскрибации...")
        result = await transcribe_audio_with_deepinfra(audio_path)
        if result:
            return result
        else:
            logger.warning("DeepInfra API не сработал, пробую локальный Whisper...")
    
    # Fallback на локальный Whisper, если он доступен
    if WHISPER_AVAILABLE:
        logger.info(f"Использую локальный Whisper модель: {model_name}")
        try:
            model = whisper.load_model(model_name)
            result = model.transcribe(str(audio_path), language="ru")
            transcript_text = result["text"]
            logger.info(f"Локальная транскрибация завершена, получено {len(transcript_text)} символов")
            return transcript_text
        except Exception as e:
            logger.error(f"Ошибка при локальной транскрибации: {e}")
            return None
    else:
        logger.error("Whisper не установлен и DeepInfra API недоступен. Транскрибация невозможна.")
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

async def split_and_transcribe_audio(audio_path):
    """Разбивает длинное аудио на сегменты и транскрибирует каждый через DeepInfra API."""
    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен")
        return None
        
    try:
        audio_path = Path(audio_path)
        logger.info(f"Разбиваю аудио на сегменты для обработки: {audio_path}")
        
        # Сначала сжимаем аудио
        compressed_audio_path = await compress_audio_for_api(audio_path)
        
        # Создаём папку для сегментов
        segments_dir = audio_path.parent / f"{audio_path.stem}_segments"
        segments_dir.mkdir(exist_ok=True)
        
        # Разбиваем на 30-секундные сегменты
        segment_duration = 30  # секунд
        segment_files = []
        
        # Получаем длительность аудио
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            str(compressed_audio_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Ошибка при получении длительности: {stderr.decode()}")
            return None
            
        total_duration = float(stdout.decode().strip())
        logger.info(f"Общая длительность аудио: {total_duration:.2f} секунд")
        
        # Создаём сегменты
        for start_time in range(0, int(total_duration), segment_duration):
            segment_path = segments_dir / f"segment_{start_time:04d}.mp3"
            
            cmd = [
                'ffmpeg',
                '-i', str(compressed_audio_path),
                '-ss', str(start_time),
                '-t', str(segment_duration),
                '-c', 'copy',
                '-y',
                str(segment_path)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 and segment_path.exists() and segment_path.stat().st_size > 1000:
                segment_files.append(segment_path)
                logger.info(f"Создан сегмент: {segment_path.name}")
            
        logger.info(f"Создано {len(segment_files)} сегментов")
        
        # Транскрибируем каждый сегмент
        all_transcripts = []
        
        for i, segment_path in enumerate(segment_files):
            logger.info(f"Транскрибирую сегмент {i+1}/{len(segment_files)}: {segment_path.name}")
            
            try:
                # Транскрибируем сегмент через DeepInfra API
                transcript = await transcribe_segment_with_deepinfra(segment_path)
                if transcript:
                    all_transcripts.append(transcript)
                else:
                    logger.warning(f"Не удалось транскрибировать сегмент {segment_path.name}")
                
                # Небольшая пауза между запросами
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Ошибка при транскрибации сегмента {segment_path.name}: {e}")
                continue
        
        # Объединяем все транскрипции
        full_transcript = " ".join(all_transcripts)
        
        # Очищаем временные файлы
        try:
            for segment_path in segment_files:
                segment_path.unlink()
            segments_dir.rmdir()
            
            # Удаляем сжатый файл, если он отличается от оригинала
            if compressed_audio_path != str(audio_path):
                Path(compressed_audio_path).unlink()
        except:
            pass
        
        logger.info(f"Транскрибация завершена, получено {len(full_transcript)} символов")
        return full_transcript
        
    except Exception as e:
        logger.error(f"Ошибка при разбивке и транскрибации аудио: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

async def transcribe_segment_with_deepinfra(segment_path):
    """Транскрибирует один сегмент аудио через DeepInfra API."""
    if not DEEPINFRA_API_KEY:
        return None
        
    try:
        # DeepInfra API для Whisper
        url = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"
        
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
        }
        
        # Читаем аудио файл
        with open(segment_path, 'rb') as audio_file:
            # Короткий таймаут для небольших сегментов
            timeout = aiohttp.ClientTimeout(total=60)  # 1 минута для сегмента
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Формируем multipart/form-data запрос
                form_data = aiohttp.FormData()
                file_name = Path(segment_path).name
                form_data.add_field('audio', audio_file, filename=file_name)
                
                async with session.post(url, headers=headers, data=form_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcript_text = result.get('text', '')
                        logger.info(f"Сегмент {file_name} транскрибирован, получено {len(transcript_text)} символов")
                        return transcript_text
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка от DeepInfra API для сегмента {file_name}: {response.status}, {error_text}")
                        return None
        
    except Exception as e:
        logger.error(f"Ошибка при транскрибации сегмента {segment_path}: {e}")
        return None 