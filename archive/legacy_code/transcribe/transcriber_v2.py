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
        
        # Команда для сжатия в MP3 с низким битрейтом
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-acodec', 'mp3',
            '-b:a', '64k',  # Низкий битрейт для уменьшения размера
            '-ar', '16000',  # Уменьшаем частоту дискретизации
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

async def transcribe_audio(audio_path, model_name="base"):
    """Транскрибирует аудио с помощью DeepInfra API через разбивку на сегменты."""
    
    # Используем DeepInfra API для транскрибации с разбивкой на сегменты
    if DEEPINFRA_API_KEY:
        logger.info("Использую DeepInfra API для транскрибации с разбивкой на сегменты...")
        result = await split_and_transcribe_audio(audio_path)
        if result:
            return result
        else:
            logger.warning("DeepInfra API не сработал")
            return None
    else:
        logger.error("DeepInfra API ключ не настроен")
        return None

def _basic_local_format(raw_transcript: str) -> str:
    """Простое локальное форматирование: чистка пробелов, разбиение на предложения и абзацы."""
    text = (raw_transcript or "").strip()
    if not text:
        return text
    # Нормализуем пробелы и переводы строк
    import re
    text = re.sub(r"[ \t\u00A0]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    # Разбиваем на предложения по пунктуации
    sentences = re.split(r"(?<=[\.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    # Собираем абзацы по 3-4 предложения
    paragraphs = []
    paragraph = []
    for s in sentences:
        paragraph.append(s)
        if len(paragraph) >= 4:
            paragraphs.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        paragraphs.append(" ".join(paragraph))
    return "\n\n".join(paragraphs)

async def format_transcript_with_llm(raw_transcript: str) -> str | None:
    """Форматирует транскрипцию с использованием языковой модели.
    Возвращает строку при успехе, None при неуспехе (чтобы вызывать локальный fallback)."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not raw_transcript or len(raw_transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для форматирования")
            return None
            
        # Используем OpenRouter API для форматирования
        if OPENROUTER_API_KEY:
            logger.info("Пробую форматировать через OpenRouter/DeepSeek")
            formatted = await format_transcript_with_openrouter(raw_transcript)
            if formatted:
                return formatted
        
        # Не удалось отформатировать через LLM
        return None
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании транскрипции: {e}")
        return None

async def format_transcript_with_openrouter(raw_transcript: str) -> str | None:
    """Форматирует сырую транскрипцию с помощью OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        return None
        
    try:
        logger.info(f"Форматирование транскрипции с помощью OpenRouter API, модель: {OPENROUTER_MODEL}")
        
        # Мягкий промт: бережное форматирование без изменения смысла
        system_prompt = (
            "Ты помощник-редактор транскрипций. Форматируй аккуратно: добавляй пунктуацию, исправляй явные опечатки, "
            "сохраняй лексику, порядок фраз и смысл. Ничего не выдумывай и не сокращай содержание. "
            "Запрещено добавлять факты/мысли от себя. Отвечай только чистым текстом без пояснений."
        )

        user_prompt = f"""Отформатируй следующую сырую транскрипцию: проставь пунктуацию, 
сделай переносы строк/абзацев, исправь только очевидные ошибки. Не перефразируй, 
не меняй порядок фраз и не убирай важное содержание. Верни только очищенный текст.

Транскрипция:
{raw_transcript}
"""
        
        # Формируем запрос к API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://transkribator.local"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Transkribator"),
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.15,  # чуть мягче, но детерминированно
            "max_tokens": 8192  # Увеличиваем лимит токенов для длинных транскрипций
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

async def request_llm_response(system_prompt: str, user_prompt: str) -> str | None:
    """Общая функция для отправки запросов к LLM через OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        return None
        
    try:
        # Формируем запрос к API
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://transkribator.local"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Transkribator"),
        }
        
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 8192  # Увеличиваем лимит токенов для длинных саммари
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
    """Разбивает длинное аудио на сегменты и транскрибирует каждый через DeepInfra API.
    Делает транскрибацию параллельно с ограничением по количеству одновременных запросов.
    Параметры управляются переменными окружения:
    - DEEPINFRA_SEGMENT_SEC (int, по умолчанию 45)
    - DEEPINFRA_CONCURRENCY (int, по умолчанию 4)
    """
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
        
        # Длительность сегмента (можно настроить через env)
        # По умолчанию 6 минут (360 секунд) для снижения вероятности сбоев сети
        segment_duration = int(os.getenv('DEEPINFRA_SEGMENT_SEC', '360'))
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
        
        # Транскрибируем сегменты параллельно с ограничением по числу одновременных запросов
        # По умолчанию бережно: 1
        concurrency = max(1, int(os.getenv('DEEPINFRA_CONCURRENCY', '1')))
        logger.info(f"Начинаю параллельную транскрибацию {len(segment_files)} сегментов, параллелизм: {concurrency}")

        semaphore = asyncio.Semaphore(concurrency)
        
        async def transcribe_one(index: int, path: Path):
            async with semaphore:
                logger.info(f"Транскрибирую сегмент {index+1}/{len(segment_files)}: {path.name}")
                try:
                    text = await transcribe_segment_with_deepinfra(path)
                    if not text:
                        logger.warning(f"Не удалось транскрибировать сегмент {path.name}")
                    return index, text or ""
                except Exception as e:
                    logger.error(f"Ошибка при транскрибации сегмента {path.name}: {e}")
                    return index, ""

        tasks = [transcribe_one(i, p) for i, p in enumerate(segment_files)]
        results = await asyncio.gather(*tasks)
        # Собираем в словарь результатов: индекс -> текст
        index_to_text: dict[int, str] = {idx: text for idx, text in results}

        # Внешние ретраи: если какие-то сегменты вернулись пустыми — пробуем ещё раз
        max_segment_retries = max(0, int(os.getenv('DEEPINFRA_MAX_SEGMENT_RETRIES', '3')))  # Увеличиваем количество ретраев
        if max_segment_retries > 0:
            for attempt in range(1, max_segment_retries + 1):
                failed_indices = [i for i, t in index_to_text.items() if not t or len(t.strip()) < 10]
                if not failed_indices:
                    break

                # Экспоненциальная пауза перед повтором (2, 4, 8 ... сек), ограничим 15 сек
                backoff_seconds = min(15, 2 ** attempt)
                logger.info(
                    f"Повторная транскрибация {len(failed_indices)} сегментов (попытка {attempt}/{max_segment_retries}), "
                    f"ожидание перед стартом {backoff_seconds}с"
                )
                await asyncio.sleep(backoff_seconds)

                # Запускаем ретрай только для проваленных сегментов, соблюдая тот же параллелизм
                retry_tasks = [
                    transcribe_one(i, segment_files[i])
                    for i in failed_indices
                ]
                retry_results = await asyncio.gather(*retry_tasks)
                recovered_count = 0
                for idx, text in retry_results:
                    if text and len(text.strip()) >= 10:  # Проверяем, что текст не пустой и не слишком короткий
                        recovered_count += 1
                        index_to_text[idx] = text
                logger.info(
                    f"Результат попытки {attempt}: восстановлено {recovered_count} из {len(failed_indices)} сегментов"
                )

        # Собираем тексты в правильном порядке
        all_transcripts = [index_to_text[i] for i in sorted(index_to_text.keys())]
        
        # Проверяем, что все сегменты обработаны
        missing_segments = [i for i in range(len(segment_files)) if i not in index_to_text or not index_to_text[i] or len(index_to_text[i].strip()) < 10]
        if missing_segments:
            logger.warning(f"ВНИМАНИЕ: {len(missing_segments)} сегментов не были обработаны: {missing_segments}")
            logger.warning("Транскрипция может быть неполной!")
        
        # Объединяем все транскрипции
        full_transcript = " ".join(all_transcripts)
        
        # Дополнительная проверка на обрыв в конце
        if full_transcript and not full_transcript.rstrip().endswith(('.', '!', '?', '...')):
            logger.warning("ВНИМАНИЕ: Транскрипция может быть обрезана - не заканчивается знаками препинания")
        
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
    """Транскрибирует один сегмент аудио через DeepInfra API (как было ранее)."""
    if not DEEPINFRA_API_KEY:
        return None
        
    try:
        # Предыдущий используемый эндпоинт
        url = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"
        
        headers = {
            "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
        }
        
        # Читаем аудио файл
        with open(segment_path, 'rb') as audio_file:
            # Таймаут запроса управляется через env, по умолчанию 300с (5 минут)
            request_timeout_sec = max(60, int(os.getenv('DEEPINFRA_REQUEST_TIMEOUT_SEC', '300')))
            timeout = aiohttp.ClientTimeout(total=request_timeout_sec)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Формируем multipart/form-data запрос
                form_data = aiohttp.FormData()
                file_name = Path(segment_path).name
                form_data.add_field('audio', audio_file, filename=file_name)
                logger.info(f"DeepInfra API POST start: {url} file={file_name}, timeout={request_timeout_sec}s")
                async with session.post(url, headers=headers, data=form_data) as response:
                    if response.status == 200:
                        result = await response.json()
                        transcript_text = result.get('text', '')
                        logger.info(f"Сегмент {file_name} транскрибирован, получено {len(transcript_text)} символов")
                        return transcript_text
                    elif response.status in (429, 500, 502, 503, 504):
                        # Пробуем один ретрай с задержкой
                        error_text = await response.text()
                        logger.warning(f"Временная ошибка DeepInfra ({response.status}) для {file_name}: {error_text[:300]}. Повтор через 2с")
                        await asyncio.sleep(2)
                        # Переоткрываем файл и пересобираем форму для повтора
                        with open(segment_path, 'rb') as audio_file_retry:
                            form_data_retry = aiohttp.FormData()
                            form_data_retry.add_field('audio', audio_file_retry, filename=file_name)
                            logger.info(f"DeepInfra API POST retry: {url} file={file_name}, timeout={request_timeout_sec + 30}s")
                            retry_timeout = aiohttp.ClientTimeout(total=request_timeout_sec + 30)
                            async with aiohttp.ClientSession(timeout=retry_timeout) as retry_session:
                                async with retry_session.post(url, headers=headers, data=form_data_retry) as resp2:
                                    if resp2.status == 200:
                                        data2 = await resp2.json()
                                        return data2.get('text', '')
                                    else:
                                        err2 = await resp2.text()
                                        logger.error(f"Повтор тоже неудачен ({resp2.status}) для {file_name}: {err2[:300]}")
                                        return None
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка от DeepInfra API для сегмента {file_name}: {response.status}, {error_text[:300]}")
                        return None
    except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionResetError, OSError) as e:
        # Ретрай при сетевых исключениях (single retry)
        try:
            await asyncio.sleep(2)
            request_timeout_sec = max(60, int(os.getenv('DEEPINFRA_REQUEST_TIMEOUT_SEC', '300')))
            timeout = aiohttp.ClientTimeout(total=request_timeout_sec + 30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                with open(segment_path, 'rb') as audio_file:
                    form_data = aiohttp.FormData()
                    file_name = Path(segment_path).name
                    form_data.add_field('audio', audio_file, filename=file_name)
                    logger.info(f"DeepInfra API POST retry (network): {url} file={file_name}, timeout={request_timeout_sec + 30}s, err={type(e).__name__}: {str(e)[:200]}")
                    resp = await session.post(url, headers=headers, data=form_data)
                    if resp.status == 200:
                        data = await resp.json()
                        text = data.get('text', '')
                        logger.info(f"Сегмент {file_name} транскрибирован после ретрая, получено {len(text)} символов")
                        return text
                    err_txt = await resp.text()
                    logger.error(f"Ретрай завершился ошибкой ({resp.status}) для {file_name}: {err_txt[:300]}")
                    return None
        except Exception as e2:
            logger.error(f"Ошибка ретрая при транскрибации сегмента {segment_path}: {e2}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при транскрибации сегмента {segment_path}: {e}")
        return None