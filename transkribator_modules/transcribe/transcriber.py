import aiohttp
import json
import os
import asyncio
from pathlib import Path
from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL, DEEPINFRA_API_KEY
import io

async def compress_audio_for_api(audio_path):
    """Сжимает аудиофайл для отправки в API, уменьшая размер."""
    try:
        audio_path = Path(audio_path)
        compressed_path = audio_path.parent / f"{audio_path.stem}_compressed.mp3"
        
        logger.info(f"Сжимаю аудиофайл: {audio_path} -> {compressed_path}")
        
        # Команда для сжатия в MP3 с оптимизированными настройками
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-acodec', 'mp3',
            '-b:a', '32k',   # Минимальный битрейт, достаточный для распознавания речи
            '-ar', '16000',  # 16 кГц – достаточно для Whisper и меньше данных
            '-ac', '1',  # Моно канал
            '-af', 'highpass=f=80,lowpass=f=8000',  # Фильтр частот для речи
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
    """Транскрибирует аудио с помощью DeepInfra API. Сегментация только для видео длиннее 30 минут."""
    
    if not DEEPINFRA_API_KEY:
        logger.error("DeepInfra API ключ не настроен")
        return None
    
    try:
        # Получаем длительность аудио
        audio_path = Path(audio_path)
        logger.info(f"🎙️ Определяю длительность аудио: {audio_path}")
        
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0',
            str(audio_path)
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Ошибка при получении длительности: {stderr.decode()}")
            # Если не можем определить длительность, пробуем прямую транскрибацию
            logger.info("Пробую прямую транскрибацию без определения длительности...")
            return await transcribe_audio_direct(audio_path)
            
        total_duration = float(stdout.decode().strip())
        duration_minutes = total_duration / 60
        logger.info(f"⏱️ Длительность аудио: {duration_minutes:.1f} минут ({total_duration:.1f} секунд)")
        
        # Решаем стратегию обработки
        if duration_minutes <= 30:
            logger.info(f"📁 Видео до 30 минут - использую ПРЯМУЮ транскрибацию без сегментации")
            result = await transcribe_audio_direct(audio_path)
            if result:
                return result
            else:
                logger.warning("Прямая транскрибация не сработала, пробую сегментацию как fallback...")
                return await split_and_transcribe_audio(audio_path)
        else:
            logger.info(f"✂️ Видео больше 30 минут - использую СЕГМЕНТАЦИЮ")
            result = await split_and_transcribe_audio(audio_path)
            if result:
                return result
            else:
                logger.warning("Сегментация не сработала")
                return None
                
    except Exception as e:
        logger.error(f"Ошибка при определении стратегии транскрибации: {e}")
        # Fallback к прямой транскрибации
        logger.info("Ошибка при анализе, пробую прямую транскрибацию...")
        return await transcribe_audio_direct(audio_path)

DEEPINFRA_MODEL_CANDIDATES = [
    "openai/whisper-large-v3-turbo",  # быстрый но не всегда доступен
    "openai/whisper-large-v3",        # стандартный
    "openai/whisper-large-v2",        # предыдущая версия
]

async def _post_to_deepinfra(audio_fp, file_name: str, timeout: aiohttp.ClientTimeout):
    """Пробует отправить файл в DeepInfra на несколько моделей по очереди.

    Возвращает текст транскрипции или None.
    """
    headers = {"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}

    # Читать файл в память один раз, чтобы затем переиспользовать для каждой попытки
    audio_bytes = audio_fp.read()

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for model in DEEPINFRA_MODEL_CANDIDATES:
            url = f"https://api.deepinfra.com/v1/inference/{model}"
            try:
                form_data = aiohttp.FormData()
                # Создаём новый BytesIO каждый раз, иначе положение указателя собьётся
                form_data.add_field('audio', io.BytesIO(audio_bytes), filename=file_name)

                logger.info(f"📤 Отправляю {file_name} в DeepInfra, модель: {model}…")
                async with session.post(url, headers=headers, data=form_data) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('text', '')
                    else:
                        err = await resp.text()
                        logger.warning(f"⚠️ DeepInfra {model} ответ {resp.status}: {err}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(f"⚠️ Сбой запроса к DeepInfra модель {model}: {e}")

        return None

async def transcribe_audio_direct(audio_path):
    """Прямая транскрибация аудио через DeepInfra API без сегментации."""
    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен")
        return None
        
    try:
        logger.info(f"🚀 ПРЯМАЯ ТРАНСКРИБАЦИЯ: {audio_path}")
        
        # Сначала сжимаем аудио для API
        compressed_audio_path = await compress_audio_for_api(audio_path)
        
        file_name = Path(compressed_audio_path).name
        with open(compressed_audio_path, 'rb') as audio_file:
            timeout = aiohttp.ClientTimeout(total=600)  # 10-мин на файл
            transcript_text = await _post_to_deepinfra(audio_file, file_name, timeout)

        if transcript_text:
            logger.info("✅ ПРЯМАЯ ТРАНСКРИБАЦИЯ ЗАВЕРШЕНА!")
            logger.info(f"📊 Получено {len(transcript_text)} символов")
        else:
            logger.error("❌ Все кандидаты DeepInfra вернули ошибку")

        # Очистка временного файла
        if compressed_audio_path != str(audio_path):
            try:
                Path(compressed_audio_path).unlink()
            except Exception:
                pass

        return transcript_text
        
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут при прямой транскрибации файла {audio_path}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при прямой транскрибации: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
            # Если LLM вернул ощутимо короче (< 90 % исходного) — считаем, что обрезал и отдаем оригинал
            if formatted and len(formatted) >= len(raw_transcript) * 0.9:
                return formatted
            else:
                logger.warning("LLM сократил транскрипцию — возвращаю исходный текст без обрезки")
        
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
        Твоя задача — полностью преобразовать сырую необработанную транскрипцию аудио в идеально читабельный текст.
        Ты должен быть очень внимательным к исправлению ошибок, очистке текста от лишних слов и созданию
        правильной структуры текста. Не должно оставаться заполнителей речи и повторений.
        ВАЖНО: Сохраняй язык оригинального текста, НИКОГДА не переводишь содержание. 
        Не добавляй собственные мысли или информацию, которой нет в исходнике."""
        
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
            "temperature": 0.3,
            "max_tokens": 1024
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
            return "Мяу... Транскрипция слишком короткая для создания подробного саммари. *задумчиво смотрит на короткий текст*"
            
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
            
            result = await request_llm_response(system_prompt, user_prompt)
            if result:
                return result
            else:
                return "Мяу... Что-то не так с моими киберлапками! 🐾 Не получается создать подробное саммари. *грустно опускает ушки* Обратитесь к моему создателю @Like_a_duck - он точно поможет! 🚀"
        
        return "Мяу... У меня нет доступа к умным помощникам для создания саммари! 😿 Напишите @Like_a_duck - он настроит всё как надо! ⚙️"
            
    except Exception as e:
        logger.error(f"Ошибка при создании подробного саммари: {e}")
        return f"Ой-ой! Произошла киберошибка при создании подробного саммари! 🤖💥 Расскажите @Like_a_duck что случилось - он всё исправит! 🛠️\n\nТехническая информация: {str(e)}"

async def generate_brief_summary(transcript: str) -> str:
    """Генерирует краткое саммари транскрипции с использованием языковой модели."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для создания краткого саммари")
            return "Мяу... Транскрипция слишком короткая для создания краткого саммари. *с любопытством изучает короткий текст*"
            
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
            
            result = await request_llm_response(system_prompt, user_prompt)
            if result:
                return result
            else:
                return "Мяу... Мои киберлапки сегодня не слушаются! 🐾 Не получается создать краткое саммари. *виновато мяукает* Сообщите @Like_a_duck - он всё наладит! 💫"
        
        return "Мяу... У меня нет доступа к умным помощникам для создания саммари! 😿 Пишите @Like_a_duck - он подключит нужные сервисы! 🔌"
            
    except Exception as e:
        logger.error(f"Ошибка при создании краткого саммари: {e}")
        return f"Ай-ай! Киберошибка в моих схемах! 🤖⚡ Краткое саммари не получилось создать. Расскажите @Like_a_duck - он разберётся! 🔧\n\nДетали ошибки: {str(e)}"

async def request_llm_response(system_prompt: str, user_prompt: str) -> str:
    """Отправляет запрос к LLM-провайдеру.

    1. Если настроен OpenRouter — пробуем его первым.
    2. При любой ошибке (таймаут, HTTP ≠ 200) или отсутствии ключа переходим на DeepInfra
       и перебираем список моделей.

    Возвращает сгенерированный текст либо None, если все попытки не удались.
    """

    # 1) OpenRouter
    if OPENROUTER_API_KEY and OPENROUTER_MODEL:
        try:
            logger.info(f"Отправляю запрос к OpenRouter API, модель: {OPENROUTER_MODEL}")

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
                "max_tokens": 1024
            }

            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    logger.info(f"Ответ OpenRouter API: {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        result = data["choices"][0]["message"]["content"]
                        logger.info(f"✅ Ответ LLM (OpenRouter), {len(result)} символов")
                        return result
                    else:
                        err = await resp.text()
                        logger.error(f"Ошибка OpenRouter API: {resp.status}, {err}")
        except asyncio.TimeoutError:
            logger.error("⏰ Таймаут OpenRouter API")
        except Exception as e:
            logger.error(f"Сбой при обращении к OpenRouter API: {e}")
            import traceback; logger.debug(traceback.format_exc())

    else:
        logger.warning("OpenRouter API не настроен или отсутствует модель — используем DeepInfra")

    # 2) DeepInfra
    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен, возвращаю None")
        return None

    candidates = [
        "mistralai/Mistral-7B-Instruct-v0.2",
        "mistralai/Mistral-Small-24B-Instruct-2501",
        "meta-llama/Meta-Llama-3-8B-Instruct",
        "google/gemma-7b-it"
    ]

    headers = {
        "Authorization": f"Bearer {DEEPINFRA_API_KEY}",
        "Content-Type": "application/json"
    }

    for model in candidates:
        try:
            logger.info(f"Пробую DeepInfra модель: {model}")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1024
            }

            timeout = aiohttp.ClientTimeout(total=120)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.deepinfra.com/v1/openai/chat/completions",
                    headers=headers,
                    json=payload
                ) as resp:
                    logger.info(f"Ответ DeepInfra ({model}): {resp.status}")
                    if resp.status == 200:
                        data = await resp.json()
                        result = data["choices"][0]["message"]["content"]
                        logger.info(f"✅ Ответ LLM (DeepInfra {model}), {len(result)} символов")
                        return result
                    else:
                        err = await resp.text()
                        logger.warning(f"⚠️ DeepInfra ошибка {resp.status}: {err}")
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Таймаут DeepInfra для модели {model}")
        except Exception as e:
            logger.warning(f"Ошибка DeepInfra модели {model}: {e}")
            import traceback; logger.debug(traceback.format_exc())

    logger.error("Все попытки обращения к LLM провайдерам завершились неудачей")
    return None

async def split_and_transcribe_audio(audio_path):
    """Пробует разные размеры сегментов (1–30 мин) и транскрибирует через DeepInfra.

    Стратегия:
    1. Берём список длительностей [60, 300, 600, 900, 1200, 1500, 1800] сек.
    2. Для каждой длительности режем аудио, отправляем сегменты.
    3. Если удалось расшифровать ≥80 % сегментов, считаем успехом и возвращаем текст.
    4. Иначе пробуем следующую (меньшую) длительность.
    """

    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен")
        return None

    import time
    audio_path = Path(audio_path)
    logger.info(f"🚀 НАЧИНАЮ ОБРАБОТКУ АУДИО: {audio_path}")

    SEGMENT_DURATION_CANDIDATES = [60, 300, 600, 900, 1200, 1500, 1800]

    for segment_duration in SEGMENT_DURATION_CANDIDATES:
        start_time_overall = time.time()
        logger.info("==============================")
        logger.info(f"🔪 Пробую длительность сегмента {segment_duration/60:.1f} мин ({segment_duration} сек)")
        try:
            # Сжимаем аудио один раз перед первой итерацией и переиспользуем файл
            compressed_audio_path = await compress_audio_for_api(audio_path)

            # Папка для текущего размера сегментов
            segments_dir = audio_path.parent / f"{audio_path.stem}_segments_{segment_duration}"
            segments_dir.mkdir(exist_ok=True)

            # 1) Узнаём длительность
            cmd_duration = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(compressed_audio_path)
            ]
            proc = await asyncio.create_subprocess_exec(*cmd_duration, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            total_duration = float(stdout.decode().strip()) if proc.returncode == 0 else 0

            # 2) Нарезаем сегменты
            segment_files, created = [], 0
            for start_sec in range(0, int(total_duration), segment_duration):
                seg_path = segments_dir / f"segment_{start_sec:04d}.mp3"
                cmd_cut = [
                    'ffmpeg', '-loglevel', 'quiet', '-i', str(compressed_audio_path),
                    '-ss', str(start_sec), '-t', str(segment_duration), '-c', 'copy', '-y', str(seg_path)
                ]
                cut_proc = await asyncio.create_subprocess_exec(*cmd_cut)
                await cut_proc.communicate()
                if cut_proc.returncode == 0 and seg_path.exists() and seg_path.stat().st_size > 1024:
                    segment_files.append(seg_path)
                    created += 1

            logger.info(f"📁 Создано {created} сегментов по {segment_duration/60:.1f} мин")

            # 3) Транскрибируем последовательно
            ok, fail, transcripts = 0, 0, []
            for idx, seg in enumerate(segment_files, 1):
                logger.info(f"📝 [{idx}/{len(segment_files)}] {seg.name}")
                res, attempt = None, 0
                while attempt < 3 and not res:
                    attempt += 1
                    try:
                        res = await transcribe_segment_with_deepinfra(seg)
                        if not res:
                            logger.warning(f"⚠️ {seg.name} попытка {attempt}/3 без результата")
                    except Exception as e:
                        logger.warning(f"❌ {seg.name} ошибка в попытке {attempt}: {e}")
                    if not res and attempt < 3:
                        await asyncio.sleep(2)
                if res:
                    transcripts.append(res)
                    ok += 1
                else:
                    fail += 1

            success_ratio = ok / len(segment_files) if segment_files else 0
            logger.info(f"✅ Успешно {ok}/{len(segment_files)} сегментов (ratio {success_ratio:.2f})")

            # 4) Проверяем успех
            if success_ratio >= 0.8 and transcripts:
                full_text = " ".join(transcripts)
                dur = time.time() - start_time_overall
                logger.info(f"🎉 Длительность {segment_duration/60:.1f} мин сработала ⇒ возврат результата")
                logger.info(f"⏱️ Время обработки: {dur/60:.1f} мин, длина текста {len(full_text)} симв.")
                # Чистим и выходим
                await _cleanup_temp_files([compressed_audio_path], segment_files, segments_dir)
                return full_text
            else:
                logger.warning("🔄 Недостаточно успешно, пробуем меньший сегмент…")
                await _cleanup_temp_files([], segment_files, segments_dir)
        except Exception as e:
            logger.error(f"❌ Ошибка на длительности {segment_duration}: {e}")
            import traceback; logger.debug(traceback.format_exc())

    logger.error("Все размеры сегментов исчерпаны, транскрибация не удалась")
    return None

# --- helper for cleanup ----------------------------------------------------

async def _cleanup_temp_files(extra_paths, segment_files, segments_dir):
    try:
        for p in segment_files:
            if p.exists():
                p.unlink()
        if segments_dir.exists():
            segments_dir.rmdir()
        for ep in extra_paths:
            if isinstance(ep, (str, Path)) and Path(ep).exists():
                Path(ep).unlink()
    except Exception as ce:
        logger.debug(f"Ошибка очистки временных файлов: {ce}")

async def transcribe_segment_with_deepinfra(segment_path):
    """Транскрибирует один сегмент аудио через DeepInfra API."""
    if not DEEPINFRA_API_KEY:
        return None
        
    try:
        file_name = Path(segment_path).name
        with open(segment_path, 'rb') as audio_file:
            timeout = aiohttp.ClientTimeout(total=900)  # 15-мин на сегмент
            transcript_text = await _post_to_deepinfra(audio_file, file_name, timeout)

        if transcript_text:
            logger.info(f"📥 Сегмент {file_name} получен, {len(transcript_text)} символов")
        return transcript_text
        
    except asyncio.TimeoutError:
        logger.error(f"⏰ Таймаут при транскрибации сегмента {segment_path}")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при транскрибации сегмента {segment_path}: {e}")
        return None 