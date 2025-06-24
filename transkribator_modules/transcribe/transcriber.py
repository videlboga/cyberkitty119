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
        
        # Команда для сжатия в MP3 с оптимизированными настройками
        cmd = [
            'ffmpeg',
            '-i', str(audio_path),
            '-acodec', 'mp3',
            '-b:a', '96k',  # Увеличенный битрейт для лучшего качества распознавания
            '-ar', '22050',  # Оптимальная частота для речи
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

    async with aiohttp.ClientSession(timeout=timeout) as session:
        form_data = aiohttp.FormData()
        form_data.add_field('audio', audio_fp, filename=file_name)

        for model in DEEPINFRA_MODEL_CANDIDATES:
            url = f"https://api.deepinfra.com/v1/inference/{model}"
            try:
                audio_fp.seek(0)
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
    """Общая функция для отправки запросов к LLM через OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        logger.warning(f"OPENROUTER_API_KEY exists: {bool(OPENROUTER_API_KEY)}")
        logger.warning(f"OPENROUTER_MODEL: {OPENROUTER_MODEL}")
        return None
        
    try:
        logger.info(f"Отправляю запрос к OpenRouter API, модель: {OPENROUTER_MODEL}")
        
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
        timeout = aiohttp.ClientTimeout(total=120)  # 2 минуты таймаут
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
            ) as response:
                logger.info(f"Получен ответ от OpenRouter API с кодом: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    result_text = data["choices"][0]["message"]["content"]
                    logger.info(f"Успешно получен ответ от LLM через OpenRouter API, длина: {len(result_text)} символов")
                    return result_text
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка от OpenRouter API: {response.status}, {error_text}")
                    return None
        
    except asyncio.TimeoutError:
        logger.error("Таймаут при запросе к OpenRouter API")
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
        
    import time
    start_time = time.time()
        
    try:
        audio_path = Path(audio_path)
        logger.info(f"🚀 НАЧИНАЮ ОБРАБОТКУ АУДИО: {audio_path}")
        logger.info(f"⏱️ Время старта: {time.strftime('%H:%M:%S', time.localtime(start_time))}")
        
        # Сначала сжимаем аудио
        compressed_audio_path = await compress_audio_for_api(audio_path)
        
        # Создаём папку для сегментов
        segments_dir = audio_path.parent / f"{audio_path.stem}_segments"
        segments_dir.mkdir(exist_ok=True)
        
        # Сегменты по 30 минут для длинных видео
        segment_duration = 1800  # секунд (30 минут)
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
        estimated_segments = int(total_duration / segment_duration) + 1
        logger.info(f"Общая длительность аудио: {total_duration:.2f} секунд")
        logger.info(f"Планируется создать {estimated_segments} сегментов по {segment_duration/60:.0f} минут")
        
        # Создаём сегменты
        segment_count = 0
        for start_time_sec in range(0, int(total_duration), segment_duration):
            segment_path = segments_dir / f"segment_{start_time_sec:04d}.mp3"
            
            cmd = [
                'ffmpeg',
                '-i', str(compressed_audio_path),
                '-ss', str(start_time_sec),
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
                segment_count += 1
                logger.info(f"✅ Создан сегмент {segment_count}/{estimated_segments}: {segment_path.name}")
            else:
                logger.warning(f"❌ Не удалось создать сегмент: {segment_path.name}")
            
        logger.info(f"📁 Создано {len(segment_files)} сегментов для транскрибации")
        
        # Транскрибируем сегменты ПОСЛЕДОВАТЕЛЬНО (не параллельно!) для стабильности
        logger.info(f"🎙️ Начинаю ПОСЛЕДОВАТЕЛЬНУЮ транскрибацию {len(segment_files)} сегментов...")
        
        all_transcripts = []
        failed_segments = []
        
        for i, segment_path in enumerate(segment_files):
            logger.info(f"📝 Транскрибирую сегмент {i+1}/{len(segment_files)}: {segment_path.name}")
            
            # Добавляем retry логику для каждого сегмента
            result = None
            for retry in range(3):  # До 3 попыток на сегмент
                try:
                    result = await transcribe_segment_with_deepinfra(segment_path)
                    if result:
                        break
                    else:
                        logger.warning(f"⚠️ Попытка {retry+1}/3 не дала результата для {segment_path.name}")
                except Exception as e:
                    logger.error(f"❌ Ошибка в попытке {retry+1}/3 для {segment_path.name}: {e}")
                    
                if retry < 2:  # Пауза между попытками
                    await asyncio.sleep(2)
            
            if result:
                all_transcripts.append(result)
                logger.info(f"✅ Сегмент {segment_path.name} успешно транскрибирован ({len(result)} символов)")
            else:
                failed_segments.append(segment_path.name)
                logger.error(f"❌ Не удалось транскрибировать сегмент {segment_path.name} после 3 попыток")
        
        # Проверяем результаты
        if failed_segments:
            logger.warning(f"⚠️ Не удалось транскрибировать {len(failed_segments)} сегментов: {failed_segments}")
        
        if not all_transcripts:
            logger.error("❌ Ни один сегмент не был успешно транскрибирован!")
            return None
        
        # Объединяем все транскрипции
        full_transcript = " ".join(all_transcripts)
        
        # Очищаем временные файлы
        try:
            for segment_path in segment_files:
                if segment_path.exists():
                    segment_path.unlink()
            if segments_dir.exists():
                segments_dir.rmdir()
            
            # Удаляем сжатый файл, если он отличается от оригинала
            if compressed_audio_path != str(audio_path):
                compressed_path = Path(compressed_audio_path)
                if compressed_path.exists():
                    compressed_path.unlink()
        except Exception as cleanup_error:
            logger.warning(f"Ошибка при очистке временных файлов: {cleanup_error}")
        
        end_time = time.time()
        processing_time = end_time - start_time
        logger.info(f"✅ ТРАНСКРИБАЦИЯ ЗАВЕРШЕНА!")
        logger.info(f"📊 Результат: {len(full_transcript)} символов")
        logger.info(f"📈 Успешно обработано: {len(all_transcripts)}/{len(segment_files)} сегментов")
        if failed_segments:
            logger.info(f"⚠️ Проваленные сегменты: {len(failed_segments)}")
        logger.info(f"⚡ Время обработки: {processing_time:.1f} секунд ({processing_time/60:.1f} минут)")
        logger.info(f"🎯 Скорость: {len(full_transcript)/processing_time:.1f} символов/сек")
        
        return full_transcript
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при разбивке и транскрибации аудио: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

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