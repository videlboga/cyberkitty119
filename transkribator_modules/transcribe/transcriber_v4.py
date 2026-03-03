from __future__ import annotations

import aiohttp
import json
import os
import asyncio
import re
from pathlib import Path
from typing import Any, Optional, Dict, List
from transkribator_modules.config import logger, OPENROUTER_API_KEY, OPENROUTER_MODEL, DEEPINFRA_API_KEY

# Параметры Gemini, согласованные по результатам экспериментального скрипта
GEMINI_MAX_CHUNK_DURATION = 10 * 60  # 10 минут — базовый размер чанка для стабильной транскрибации
GEMINI_MIN_CHUNK_DURATION = 5 * 60   # не дробим меньше 5 минут, чтобы не плодить лишние запросы
GEMINI_CHAR_RETRY_THRESHOLD = 18_000  # если в single-shot получили столько символов, почти уперлись в лимит
GEMINI_COMPLETION_TOKEN_LIMIT = 4000  # целевой лимит токенов для 10-минутного чанка

# Температуры, которые хорошо показали себя на 10-минутных чанках:
# базовый прогон с лёгкой стохастикой + два запасных варианта.
GEMINI_TEMPERATURE_SCHEDULE = [0.2, 0.0, 0.4]

CHUNK_RETRY_ATTEMPTS = 3
MIN_CHUNK_TEXT_LENGTH = 24  # минимальная длина текста чанка, иначе повторяем попытку
LLM_FORMAT_RETRY_ATTEMPTS = int(os.getenv("LLM_FORMAT_RETRY_ATTEMPTS", "3"))
TRANSCRIBE_CLIENT_ENABLED = os.getenv("TRANSCRIBE_CLIENT_ENABLED", "0").lower() in ("1", "true", "yes")
TRANSCRIBE_CLIENT_MODE = os.getenv("TRANSCRIBE_DEFAULT_MODE", "auto")
_SEGMENT_CACHE_SUFFIX = ".segments.json"


def _segments_cache_path(audio_path: Path) -> Path:
    """Возвращает путь для кэша сегментов рядом с аудиофайлом."""
    return audio_path.with_suffix(f"{audio_path.suffix}{_SEGMENT_CACHE_SUFFIX}")


def _save_segments_cache(audio_path: Path, segments: List[Dict[str, Any]], transcript: Optional[str]) -> None:
    try:
        cache_path = _segments_cache_path(audio_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "segments": segments or [],
                    "text": transcript or "",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось записать кэш сегментов", extra={"error": str(exc)})


def _load_segments_cache(audio_path: Path) -> Optional[tuple[List[Dict[str, Any]], Optional[str]]]:
    try:
        cache_path = _segments_cache_path(audio_path)
        if not cache_path.exists():
            return None
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        text = data.get("text")
        return segments, text
    except Exception as exc:  # noqa: BLE001
        logger.debug("Не удалось прочитать кэш сегментов", extra={"error": str(exc)})
        return None

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


def _extract_text_from_client_result(result):
    if not isinstance(result, dict):
        return None

    status = result.get("status")
    if isinstance(status, str) and status.lower() not in ("ok", "success", "done", ""):
        logger.warning(
            "Transcribe client returned non-OK status",
            extra={"status": status, "meta": result.get("meta")},
        )

    text = result.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    segments = result.get("segments")
    if isinstance(segments, (list, tuple)):
        pieces = []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            snippet = segment.get("text")
            if isinstance(snippet, str) and snippet.strip():
                pieces.append(snippet.strip())
        if pieces:
            return " ".join(pieces)

    for key in ("results", "choices"):
        items = result.get(key)
        if isinstance(items, (list, tuple)):
            for entry in items:
                extracted = _extract_text_from_client_result(entry)
                if extracted:
                    return extracted

    return None


async def _try_transcribe_with_client(audio_path):
    if not TRANSCRIBE_CLIENT_ENABLED:
        return None

    cached = _load_segments_cache(Path(audio_path))
    if cached and cached[1]:
        logger.info("Использую кэш транскрипции из transcribe_client")
        return cached[1]

    try:
        from transcribe_client import TranscribeClient
    except ImportError:
        logger.warning("TRANSCRIBE_CLIENT_ENABLED set but transcribe_client package missing")
        return None

    client = TranscribeClient(default_mode=TRANSCRIBE_CLIENT_MODE)
    try:
        result = await asyncio.to_thread(client.transcribe, str(audio_path), TRANSCRIBE_CLIENT_MODE)
    except Exception as exc:
        logger.warning(
            "Transcribe client invocation failed",
            extra={"error": str(exc), "mode": TRANSCRIBE_CLIENT_MODE},
        )
        return None

    extracted = _extract_text_from_client_result(result)
    segments = result.get("segments") or []
    transcript = extracted
    if transcript or segments:
        _save_segments_cache(Path(audio_path), segments, transcript)

    if transcript:
        logger.info(
            "Transcription produced by transcribe_client",
            extra={"chars": len(transcript), "mode": TRANSCRIBE_CLIENT_MODE},
        )
        return transcript

    logger.warning(
        "Transcribe client returned no usable text",
        extra={"meta": result.get("meta") if isinstance(result, dict) else None},
    )
    return None

async def transcribe_audio(audio_path, model_name="base"):
    """Транскрибирует аудио с помощью OpenRouter Gemini через чанки до 10 минут."""

    client_result = await _try_transcribe_with_client(audio_path)
    if client_result:
        return client_result

    # Временно закомментирована логика DeepInfra - используем Gemini как основной метод
        if DEEPINFRA_API_KEY:
            logger.info("Использую DeepInfra API для транскрибации целиком...")
            try:
                result = await transcribe_whole_audio_with_deepinfra(audio_path)
                if result:
                    return result
                else:
                    logger.warning("DeepInfra API не вернул результат")
            except Exception as exc:
                logger.warning("DeepInfra transcription failed", extra={"error": str(exc)})
        else:
            logger.debug("DEEPINFRA_API_KEY не настроен — пропускаем DeepInfra")

    # Используем Gemini через OpenRouter как основной метод
    if OPENROUTER_API_KEY:
        logger.info("Использую OpenRouter Gemini для транскрибации...")
        result = await transcribe_whole_audio_with_gemini(audio_path)
        if result:
            return result
        else:
            logger.warning("OpenRouter Gemini не сработал")
            return None
    else:
        logger.error("OpenRouter API ключ не настроен")
        return None

def _basic_local_format(raw_transcript: str) -> str:
    """Улучшенное локальное форматирование: сохраняет весь текст, добавляет структуру."""
    text = (raw_transcript or "").strip()
    if not text:
        return text

    # Нормализуем пробелы, но сохраняем весь текст
    import re
    text = re.sub(r"[ \t\u00A0]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)

    # Разбиваем на предложения по пунктуации
    sentences = re.split(r"(?<=[\.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # Если предложения не найдены, разбиваем по длинным паузам
    if len(sentences) <= 1:
        sentences = re.split(r"(?<=[.!?])\s+(?=[А-ЯЁ])", text)
        sentences = [s.strip() for s in sentences if s.strip()]

    # Собираем абзацы по 3-4 предложения для лучшей читаемости
    paragraphs = []
    paragraph = []
    for s in sentences:
        paragraph.append(s)
        if len(paragraph) >= 4:
            paragraphs.append(" ".join(paragraph))
            paragraph = []
    if paragraph:
        paragraphs.append(" ".join(paragraph))

    # Если абзацы не получились, возвращаем исходный текст с базовой очисткой
    if not paragraphs:
        return text

    return "\n\n".join(paragraphs)


def _ensure_paragraphs(text: str) -> str:
    """Гарантируем, что в тексте есть абзацы/переносы. Если LLM вернул сплошной блок, разбиваем локально."""
    if not text:
        return text
    if "\n" in text:
        return text
    return _basic_local_format(text)


def _tokenize_for_quality(text: str) -> list[str]:
    """Преобразует текст в список слов, учитывая кириллицу, для оценки качества."""
    if not text:
        return []
    return re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", text.lower())


def _detect_repeating_phrase(text: str) -> str | None:
    """Находит короткую фразу (до 4 слов), которая повторяется слишком часто подряд."""
    if not text:
        return None

    # First, try to detect hyphenated repeating tokens (e.g. "та-та-та")
    # without normalizing away hyphens — tests sometimes expect hyphen form.
    try:
        hyphen_match = re.search(r"(\b\w+(?:-\w+){1,3}\b)(?:\s+\1\b){5,}", text, re.IGNORECASE)
        if hyphen_match:
            return hyphen_match.group(1).strip()
    except Exception:
        # ignore regex issues and fall back to general detection
        pass

    # Нормализуем текст: понижаем регистр, убираем пунктуацию (включая дефисы),
    # чтобы паттерны вида "та-та-та" или "та-та, та-та" тоже сворачивались.
    normalized = text.lower()
    normalized = re.sub(r"[^\w\s]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if len(normalized) < 30:
        return None

    match = re.search(r"(\b\w+(?:\s+\w+){0,3})\b(?:\s+\1\b){5,}", normalized)
    if match:
        return match.group(1).strip()
    return None


def _is_formatted_transcript_valid(raw_text: str, formatted_text: str) -> tuple[bool, str | None]:
    """Проверяет, что LLM-результат достаточно близок к исходному тексту и не деградировал."""
    raw_tokens = _tokenize_for_quality(raw_text)
    formatted_tokens = _tokenize_for_quality(formatted_text)

    if not formatted_tokens:
        return False, "formatted transcript is empty after tokenization"

    # Если исходный текст короткий, дополнительные проверки не требуются
    if len(raw_tokens) < 40:
        return True, None

    token_ratio = len(formatted_tokens) / len(raw_tokens) if raw_tokens else 1.0
    if token_ratio < 0.6:
        return False, f"formatted transcript lost too many tokens ({token_ratio:.0%})"

    unique_raw = set(raw_tokens)
    unique_formatted = set(formatted_tokens)
    raw_diversity = 0.0
    if unique_raw:
        coverage = len(unique_raw & unique_formatted) / len(unique_raw)
        if coverage < 0.5:
            return False, f"word coverage too low ({coverage:.0%})"
        raw_diversity = len(unique_raw) / len(raw_tokens)

    if len(formatted_tokens) >= 80:
        diversity = len(unique_formatted) / len(formatted_tokens)
        diversity_threshold = max(0.05, raw_diversity * 0.5) if raw_diversity else 0.1
        if diversity < diversity_threshold:
            return False, f"word diversity too low ({diversity:.0%})"

        repeated_phrase = _detect_repeating_phrase(formatted_text)
        if repeated_phrase:
            return False, f"detected repeating phrase '{repeated_phrase}'"

    return True, None


_TECHNICAL_MARKER_RE = re.compile(r"^\s*\[(?:Чанк|Ошибка транскрибации).+\]\s*$", re.IGNORECASE)


def _strip_technical_markers(text: str) -> str:
    """Удаляет строки вида [Чанк N ...] и аналогичные тех. пометки."""
    if not text:
        return ""
    cleaned_lines = [
        line for line in text.splitlines()
        if not _TECHNICAL_MARKER_RE.match(line.strip())
    ]
    cleaned = "\n".join(cleaned_lines).strip()
    return cleaned


def _dedupe_transcript_text(text: str) -> str:
    """Убирает явные повторы в транскрипции, сохраняя структуру.
    - Удаляет подряд идущие идентичные строки (с учётом нормализации пробелов/регистра)
    - Сворачивает «заедающие» короткие фразы, повторённые много раз подряд
    - Удаляет повторяющиеся длинные абзацы и предложения, которые появились из‑за склейки чанков или сбоев LLM
    """
    if not text:
        return text

    # 1) Удаляем подряд идущие дубликаты строк
    out_lines: list[str] = []
    prev_key: str | None = None
    for line in (text.splitlines()):
        norm = re.sub(r"\s+", " ", line).strip().casefold()
        if norm and norm == prev_key:
            continue
        out_lines.append(line.rstrip())
        prev_key = norm if norm else None

    deduped = "\n".join(out_lines)

    # 2) Сворачиваем повторяющуюся короткую фразу (если найдена)
    phrase = _detect_repeating_phrase(deduped)
    if phrase:
        try:
            logger.warning(
                "Postprocess: collapsing repeating phrase in formatted transcript",
                extra={"repeating_phrase": phrase},
            )
        except Exception:
        # Логирование не должно ломать постобработку, если extra не сериализуется
            logger.warning("Postprocess: collapsing repeating phrase in formatted transcript")
        # Заменяем длинные последовательности повторов этой фразы на один экземпляр
        safe_phrase = re.escape(phrase)
        pattern = re.compile(rf"(?:\b{safe_phrase}\b[\s,.;:!\-–—]*){3,}", re.IGNORECASE)
        deduped = pattern.sub(phrase, deduped)

    # 3) Удаляем повторяющиеся длинные абзацы (часто появляются при склейке чанков)
    paragraphs = deduped.split("\n\n")
    seen_para_keys: set[str] = set()
    unique_paragraphs: list[str] = []
    for para in paragraphs:
        para_stripped = para.strip()
        if not para_stripped:
            unique_paragraphs.append(para)
            continue

        key = re.sub(r"\s+", " ", para_stripped).casefold()

        # Считаем только достаточно длинные абзацы, чтобы не трогать короткие реплики
        if len(key) >= 120:
            if key in seen_para_keys:
                # Повторный длинный абзац — считаем артефактом и пропускаем
                continue
            seen_para_keys.add(key)

        unique_paragraphs.append(para)

    deduped = "\n\n".join(unique_paragraphs)

    # 4) Дополнительно убираем повторяющиеся длинные предложения внутри текста
    sentences = re.split(r"(?<=[\.!?])\s+", deduped)
    seen_sent_keys: dict[str, int] = {}
    filtered_sentences: list[str] = []
    for sent in sentences:
        s = sent.strip()
        if not s:
            continue
        key = re.sub(r"\s+", " ", s).casefold()
        if len(key) >= 80:
            count = seen_sent_keys.get(key, 0)
            seen_sent_keys[key] = count + 1
            # Первые два появления оставляем, начиная с третьего — считаем шумом
            if count >= 2:
                continue
        filtered_sentences.append(s)

    return " ".join(filtered_sentences)


async def _postprocess_full_transcript(text: str) -> str:
    """Удаляет тех. строки и форматирует транскрипт через LLM/локальный fallback."""
    cleaned = _strip_technical_markers(text)
    formatted = await format_transcript_with_llm(cleaned)
    if formatted:
        return _dedupe_transcript_text(formatted)
    return _dedupe_transcript_text(_basic_local_format(cleaned))

_FORMAT_CACHE: dict[str, tuple[float, str]] = {}
_FORMAT_CACHE_TTL = 30 * 60  # 30 минут


def _now_ts() -> float:
    import time as _t
    return _t.time()


def _cleanup_format_cache() -> None:
    now = _now_ts()
    stale = [k for k, (ts, _) in _FORMAT_CACHE.items() if now - ts > _FORMAT_CACHE_TTL]
    for k in stale:
        _FORMAT_CACHE.pop(k, None)


def _hash_text(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def format_transcript_with_llm(raw_transcript: str) -> str | None:
    """Форматирует транскрипцию без обращения к LLM.

    Исторически здесь вызывался OpenRouter для «умного» форматирования текста,
    но это приводило к артефактам вроде бесконечных повторов фраз.
    Сейчас шаг LLM полностью отключён: мы применяем только локальное
    базовое форматирование, сохраняя API функции для совместимости.
    """
    text = raw_transcript or ""
    stripped = text.strip()
    if not stripped:
        logger.warning("format_transcript_with_llm: пустая транскрипция, возвращаю как есть")
        return text

    logger.info(
        "format_transcript_with_llm: LLM форматирование отключено, использую только локальное форматирование"
    )
    try:
        return _basic_local_format(text)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка локального форматирования транскрипции: {e}")
        return text

async def format_transcript_with_openrouter(raw_transcript: str) -> str | None:
    """Форматирует сырую транскрипцию с помощью OpenRouter API."""
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("OpenRouter API ключ или модель не настроены")
        return None
    logger.info(
        "Форматирование транскрипции с помощью OpenRouter API, модель: %s",
        OPENROUTER_MODEL,
    )

    system_prompt = (
        "Ты редактор транскрипций. ТВОЯ ГЛАВНАЯ ЗАДАЧА - СОХРАНИТЬ ВЕСЬ ТЕКСТ БЕЗ ПОТЕРИ ИНФОРМАЦИИ. "
        "КРИТИЧЕСКИ ВАЖНО: НЕ УБИРАЙ НИ ОДНОГО СЛОВА из оригинального текста. "
        "Только добавляй пунктуацию, исправляй очевидные опечатки и делай переносы строк. "
        "НЕ СОКРАЩАЙ, НЕ ПЕРЕФРАЗИРУЙ, НЕ УПРОЩАЙ текст. "
        "Если исходный текст длинный - верни его полностью, только с улучшенным форматированием. "
        "Отвечай ТОЛЬКО отформатированным текстом без дополнительных комментариев."
    )

    user_prompt = (
        "Пожалуйста, отформатируй эту транскрипцию, сохранив ВЕСЬ текст:\n\n"
        "ВАЖНО:\n"
        "- Сохрани каждое слово из оригинала\n"
        "- Добавь только пунктуацию и переносы строк\n"
        "- Исправь только явные опечатки\n"
        "- НЕ сокращай и НЕ убирай никакую информацию\n"
        "- Верни текст той же длины или длиннее\n\n"
        f"Транскрипция для форматирования:\n{raw_transcript}\n\nОтформатированный текст:"
    )

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
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 32768,
    }

    transient_statuses = {408, 409, 429, 500, 502, 503, 504}
    last_error: str | None = None

    for attempt in range(1, LLM_FORMAT_RETRY_ATTEMPTS + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=180),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        choices = data.get("choices") or []
                        if not choices:
                            raise ValueError("OpenRouter вернул пустой список choices")
                        message = choices[0].get("message") or {}
                        formatted_text = (message.get("content") or "").strip()
                        if not formatted_text:
                            raise ValueError("OpenRouter вернул пустой content")

                        if formatted_text.strip() == raw_transcript.strip():
                            logger.info(
                                "LLM вернул текст без изменений — отклоняю как неуспешное форматирование"
                            )
                            return None

                        original_length = len(raw_transcript)
                        formatted_length = len(formatted_text)
                        length_ratio = (
                            formatted_length / original_length if original_length > 0 else 1
                        )

                        if length_ratio > 1.2:
                            logger.warning(
                                "⚠️ Модель добавила много лишнего: %.1fx от оригинала",
                                length_ratio,
                            )
                            is_valid, reason = _is_formatted_transcript_valid(
                                raw_transcript, formatted_text
                            )
                            if not is_valid:
                                logger.error("❌ Отклоняю форматирование: %s", reason)
                                return None
                            return _ensure_paragraphs(formatted_text)

                        if length_ratio < 0.7:
                            logger.error(
                                "❌ Модель КРИТИЧЕСКИ сократила текст: %.1fx от оригинала - ОТКЛОНЯЕМ",
                                length_ratio,
                            )
                            return None

                        if length_ratio < 0.8:
                            logger.warning(
                                "⚠️ Модель сократила текст: %.1fx от оригинала - принимаем с предупреждением",
                                length_ratio,
                            )
                            is_valid, reason = _is_formatted_transcript_valid(
                                raw_transcript, formatted_text
                            )
                            if not is_valid:
                                logger.error("❌ Отклоняю форматирование: %s", reason)
                                return None
                            return _ensure_paragraphs(formatted_text)

                        logger.info(
                            "✅ Форматирование прошло успешно: %.1fx от оригинала",
                            length_ratio,
                        )
                        is_valid, reason = _is_formatted_transcript_valid(
                            raw_transcript, formatted_text
                        )
                        if not is_valid:
                            logger.error("❌ Отклоняю форматирование: %s", reason)
                            return None
                        return _ensure_paragraphs(formatted_text)

                    error_text = await response.text()
                    last_error = f"HTTP {response.status}: {error_text[:200]}"
                    if response.status in transient_statuses:
                        logger.warning(
                            "⚠️ Временная ошибка OpenRouter (%s), попытка %s/%s",
                            last_error,
                            attempt,
                            LLM_FORMAT_RETRY_ATTEMPTS,
                        )
                    else:
                        logger.error("Ошибка от OpenRouter API: %s", last_error)
                        return None

        except asyncio.TimeoutError:
            last_error = "timeout"
            logger.warning(
                "⏱️ Таймаут OpenRouter при форматировании, попытка %s/%s",
                attempt,
                LLM_FORMAT_RETRY_ATTEMPTS,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Ошибка при форматировании транскрипции через OpenRouter API (попытка %s/%s): %s",
                attempt,
                LLM_FORMAT_RETRY_ATTEMPTS,
                last_error,
            )

        if attempt < LLM_FORMAT_RETRY_ATTEMPTS:
            delay = min(10, 2 ** attempt)
            await asyncio.sleep(delay)

    logger.error(
        "OpenRouter форматирование не удалось после %s попыток. Последняя ошибка: %s",
        LLM_FORMAT_RETRY_ATTEMPTS,
        last_error or "unknown",
    )
    return None

async def generate_title_with_llm(transcript: str) -> str | None:
    """Генерирует краткое умное название для транскрипции с помощью LLM.
    
    Args:
        transcript: Текст транскрипции
        
    Returns:
        Краткое название (2-5 слов) или None если не удалось сгенерировать
    """
    if not OPENROUTER_API_KEY or not OPENROUTER_MODEL:
        logger.warning("generate_title_with_llm: OpenRouter API ключ или модель не настроены")
        return None

    try:
        # Берём только начало транскрипции для экономии токенов
        sample = transcript[:1000] if len(transcript) > 1000 else transcript
        logger.debug(
            "generate_title_with_llm: sample length=%s, sample preview=%r",
            len(sample),
            sample[:500],
        )
        
        system_prompt = (
            "Ты эксперт по созданию кратких и ёмких заголовков. "
            "Твоя задача - создать понятное название из 5-6 слов, которое точно отражает СУТЬ содержания. "
            "ВАЖНО: Название должно быть КОНКРЕТНЫМ и ИНФОРМАТИВНЫМ, не общим. "
            "Отвечай ТОЛЬКО названием, без кавычек и дополнительных слов."
        )
        
        user_prompt = f"""На основе этого текста создай краткое название (5-6 слов), которое ёмко отражает суть содержимого:

{sample}

Требования:
- Название должно быть КОНКРЕТНЫМ (например: "Обсуждение интеграции платёжной системы", а не просто "Встреча про проект")
- Название должно отражать ГЛАВНУЮ ТЕМУ или ЦЕЛЬ разговора максимально точно
- Используй ровно 5-6 слов (можно сокращать предлоги)
- Без кавычек, пояснений и дополнительного текста
- На русском языке

Название:"""

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/transkribator",
            "X-Title": "CyberKitty Transkribator"
        }

        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
            ],
            "temperature": 0.2,
            "max_tokens": 60
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    raw_content = data["choices"][0]["message"]["content"]
                    logger.debug(
                        "generate_title_with_llm: raw LLM title response (len=%s): %r",
                        len(raw_content or ""),
                        raw_content,
                    )
                    title = (raw_content or "").strip()
                    
                    # Очищаем название от лишних символов и маркеров
                    title = title.strip('"\'«»""''').replace('Название:', '').strip()
                    
                    # Убираем переносы строк
                    title = ' '.join(title.split())
                    
                    # Проверяем что название не пустое и не слишком короткое
                    if len(title) < 3:
                        logger.warning(f"Сгенерированное название слишком короткое: '{title}'")
                        return None
                    
                    # Проверяем что название не слишком длинное
                    if len(title) > 60:
                        title = title[:57] + "..."
                    
                    logger.info(f"✅ Сгенерировано умное название: {title}")
                    return title
                else:
                    error_text = await response.text()
                    logger.warning(f"OpenRouter API вернул ошибку: {response.status}, {error_text[:200]}")
                    return None
                    
    except asyncio.TimeoutError:
        logger.warning("Таймаут при генерации названия")
        return None
    except Exception as e:
        logger.debug(f"Ошибка при генерации названия: {e}")
        return None

# Функция разбиения на чанки для форматирования удалена - теперь форматируем целиком

async def generate_detailed_summary(transcript: str) -> str:
    """Генерирует подробное саммари транскрипции с использованием языковой модели."""
    try:
        # Проверяем, не пустая ли транскрипция
        if not transcript or len(transcript.strip()) < 10:
            logger.warning("Транскрипция слишком короткая для создания подробного саммари")
            return "Транскрипция слишком короткая для создания подробного саммари."

        # Используем OpenRouter API для генерации саммари
        if OPENROUTER_API_KEY:
            system_prompt = (
                "Ты опытный аналитик, который превращает транскрипции встреч и звонков "
                "в ясные, структурированные и читаемые саммари. Уважай факты, имена и цифры, "
                "делай текст живым и аккуратным."
            )

            user_prompt = f"""Вот транскрипция. Сформулируй подробное, но компактное саммари (~200–280 слов).

{transcript}

Требования к оформлению:
- Сначала определи главные блоки смысла (темы, выводы, решения, действия, эмоции и т.п.) и расположи их логично один за другим.
- Для каждого блока сделай короткий заголовок. Допускается использовать эмодзи, если они уместны и помогают ориентироваться.
- Внутри блоков комбинируй небольшие абзацы и списки: маркированные — для перечислений, нумерованные — если важен порядок.
- Избегай пустых разделов. Если какой-то тип информации в тексте отсутствует, пропусти его.

Общие правила:
- Пиши живым, понятным языком, без воды и спойлеров.
- Сохраняй конкретику: имена, цифры, даты, условия, эмоции, ключевые формулировки.
- Не добавляй информацию, которой нет в транскрипции, и не выводи мораль.
- Верни только готовое саммари без пояснений со стороны аналитика."""

            result = await request_llm_response(system_prompt, user_prompt)
            return result if result else "Не удалось создать подробное саммари. Проверьте настройки API для языковой модели."

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

            result = await request_llm_response(system_prompt, user_prompt)
            return result if result else "Не удалось создать краткое саммари. Проверьте настройки API для языковой модели."

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
            "max_tokens": 32768  # Увеличиваем лимит токенов для длинных саммари
        }

        logger.debug(
            "request_llm_response: system_prompt=%r, user_prompt_preview=%r",
            system_prompt,
            (user_prompt[:1000] + "…") if len(user_prompt) > 1000 else user_prompt,
        )

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
                    logger.debug(
                        "request_llm_response: raw LLM response length=%s, content=%r",
                        len(result_text or ""),
                        result_text,
                    )
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

async def format_and_summarize_with_llm(raw_transcript: str):
    """Один вызов LLM: вернуть JSON {formatted, summary}. Возврат кортежа (formatted, summary).
    При ошибке парсинга — fallback на существующие format_transcript_with_llm + generate_brief_summary.
    """
    cleaned = (raw_transcript or '').strip()
    if not cleaned:
        return None, None

    if OPENROUTER_API_KEY and OPENROUTER_MODEL:
        system_prompt = (
            'Ты редактор транскриптов. Преобразуй текст в читаемый вид (абзацы, предложения, базовая пунктуация)'
            ' и подготовь краткое саммари. Верни ТОЛЬКО JSON строго вида {"formatted": <string>, "summary": <string>}'
        )
        user_prompt = (
            "Исходный текст:\n\n" + cleaned + "\n\n"
            "Требования:\n"
            "- formatted: тот же контент, но с аккуратными абзацами; без избыточных вставок.\n"
            "- summary: 2–3 предложения, кратко и по делу.\n"
            "- Строго JSON, без пояснений."
        )
        raw = await request_llm_response(system_prompt, user_prompt)
        if raw:
            try:
                data = json.loads(raw)
                formatted = data.get('formatted') if isinstance(data, dict) else None
                summary = data.get('summary') if isinstance(data, dict) else None
                if isinstance(formatted, str) and formatted.strip():
                    try:
                        key = _hash_text(cleaned)
                        _cleanup_format_cache()
                        _FORMAT_CACHE[key] = (_now_ts(), formatted)
                    except Exception:
                        pass
                    formatted = _ensure_paragraphs(formatted)
                    return formatted, (summary.strip() if isinstance(summary, str) else None)
            except json.JSONDecodeError:
                logger.debug('format_and_summarize_with_llm: JSON parse failed, fallback to two-step')

    # Fallback на двухшаговый вариант
    formatted_only = await format_transcript_with_llm(cleaned)
    brief = None
    try:
        brief = await generate_brief_summary(formatted_only or cleaned)
    except Exception:
        brief = None
    return _ensure_paragraphs(formatted_only or cleaned), brief

async def transcribe_whole_audio_with_gemini(audio_path):
    """Транскрибирует аудио через OpenRouter Gemini API. 
    Для больших файлов (>30 мин) разбивает на чанки и обрабатывает параллельно."""
    if not OPENROUTER_API_KEY:
        logger.warning("OpenRouter API ключ не настроен")
        return None

    try:
        audio_path = Path(audio_path)
        logger.info(f"Транскрибирую аудио: {audio_path}")

        # Сначала сжимаем аудио
        compressed_audio_path = await compress_audio_for_api(audio_path)

        # Получаем длительность аудио
        duration = await get_audio_duration(compressed_audio_path)
        logger.info(f"Длительность аудио: {duration:.1f} секунд ({duration/60:.1f} минут)")

        chunk_duration = GEMINI_MAX_CHUNK_DURATION

        if duration <= chunk_duration:
            # Короткий файл — транскрибируем целиком, но контролируем лимит символов
            logger.info("Файл короткий, транскрибируем целиком через Gemini")
            transcript_text = await transcribe_segment_with_openrouter_gemini(compressed_audio_path)
            if (
                transcript_text
                and len(transcript_text) >= GEMINI_CHAR_RETRY_THRESHOLD
                and duration > GEMINI_MIN_CHUNK_DURATION
            ):
                logger.warning(
                    "Gemini single-shot ответ достиг %s символов (%.1f мин) — переразбиваю на более короткие чанки",
                    len(transcript_text),
                    duration / 60,
                )
                smaller_chunk = max(int(duration / 2), GEMINI_MIN_CHUNK_DURATION)
                chunked = await transcribe_long_audio_parallel_gemini(
                    compressed_audio_path,
                    duration,
                    smaller_chunk,
                )
                if chunked:
                    transcript_text = chunked
        else:
            # Длинный файл - разбиваем на чанки и обрабатываем параллельно
            logger.info(
                "Файл длинный (%.1f мин), разбиваю на чанки по %.1f минут",
                duration / 60,
                chunk_duration / 60,
            )
            transcript_text = await transcribe_long_audio_parallel_gemini(
                compressed_audio_path,
                duration,
                chunk_duration,
            )

        if transcript_text:
            logger.info(f"Транскрибация завершена, получено {len(transcript_text)} символов")

            # Очищаем временные файлы
            try:
                if compressed_audio_path != str(audio_path):
                    Path(compressed_audio_path).unlink()
            except:
                pass
            
            # Всегда прогоняем через общий постпроцессинг:
            # - убираем тех. метки
            # - локально форматируем текст
            # - сворачиваем заедающие повторы фраз
            transcript_text = await _postprocess_full_transcript(transcript_text)
            return transcript_text
        else:
            logger.error("Не удалось транскрибировать аудио")
            return None

    except Exception as e:
        logger.error(f"Ошибка при транскрибации аудио: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def _transcribe_chunk_with_retry_gemini(chunk_path: Path, chunk_num: int, max_attempts: int = CHUNK_RETRY_ATTEMPTS) -> str | None:
    """Повторяет транскрибацию чанка до получения непустого текста."""
    # Быстрая защита от заведомо пустых/почти пустых чанков (длительная тишина).
    try:
        non_silence = _estimate_non_silence_duration(chunk_path)
        if non_silence < 5.0:
            logger.info(
                "Чанк %s (%s) содержит менее 5 секунд звучащего сигнала (%.1fs), "
                "пропускаю отправку в OpenRouter",
                chunk_num,
                chunk_path.name,
                non_silence,
            )
            return None
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Не удалось оценить тишину для чанка %s (%s): %s: %s",
            chunk_num,
            chunk_path,
            type(exc).__name__,
            exc,
        )

    last_issue = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await transcribe_segment_with_openrouter_gemini(str(chunk_path))
        except Exception as exc:  # noqa: BLE001
            last_issue = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.error(
                f"❌ Ошибка Gemini для чанка {chunk_num}, попытка {attempt}/{max_attempts}: {last_issue}"
            )
            result = None

        if result and result.strip():
            cleaned = result.strip()

            # 1) Слишком короткий ответ для 10‑минутного чанка — считаем неудачной попыткой
            if len(cleaned) < MIN_CHUNK_TEXT_LENGTH and attempt < max_attempts:
                last_issue = f"too_short({len(cleaned)})"
                logger.warning(
                    f"⚠️ Чанк {chunk_num} дал подозрительно короткий текст ({len(cleaned)} симв.). "
                    f"Повторяю попытку {attempt + 1}/{max_attempts}"
                )

            else:
                # 2) Фильтрация «битых» ответов: зацикленные фразы, очень низкое разнообразие слов
                bad_reason: str | None = None
                lower = cleaned.lower()
                if "аудиофайл пуст" in lower or "не могу выполнить этот запрос" in lower:
                    bad_reason = "llm_declared_empty_audio"
                else:
                    rep_phrase = _detect_repeating_phrase(cleaned)
                    if rep_phrase:
                        bad_reason = f"repeating_phrase:{rep_phrase}"
                    else:
                        tokens = _tokenize_for_quality(cleaned)
                        if len(tokens) >= 80:
                            unique_tokens = set(tokens)
                            diversity = len(unique_tokens) / len(tokens)
                            # Для реального разговора ожидаем куда большую вариативность,
                            # чем для «та-та-та» и похожих паттернов.
                            if diversity < 0.15:
                                bad_reason = f"low_diversity({diversity:.3f})"

                if bad_reason:
                    last_issue = bad_reason
                    if attempt < max_attempts:
                        logger.warning(
                            "⚠️ Чанк %s: отбрасываю ответ Gemini как некачественный (%s), "
                            "повторяю попытку %s/%s",
                            chunk_num,
                            bad_reason,
                            attempt + 1,
                            max_attempts,
                        )
                    else:
                        logger.error(
                            "❌ Чанк %s: все попытки дали некачественный текст "
                            "(последняя причина: %s)",
                            chunk_num,
                            bad_reason,
                        )
                        return None
                else:
                    logger.debug(
                        "Gemini chunk %s transcript accepted (len=%s): %r",
                        chunk_num,
                        len(cleaned),
                        cleaned,
                    )
                    return cleaned
        else:
            last_issue = "empty"
            logger.warning(
                f"⚠️ Gemini вернул пустой текст для чанка {chunk_num} (попытка {attempt}/{max_attempts})"
            )

        if attempt < max_attempts:
            delay = min(2 ** attempt, 8)
            await asyncio.sleep(delay)

    logger.error(
        f"❌ Чанк {chunk_num} не распознан после {max_attempts} попыток (последняя проблема: {last_issue})"
    )
    return None


async def _transcribe_chunk_with_retry_deepinfra(chunk_path: Path, chunk_num: int, max_attempts: int = CHUNK_RETRY_ATTEMPTS) -> str | None:
    """Повторяет транскрибацию чанка через DeepInfra, пока не получим текст."""
    last_issue = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await transcribe_segment_with_deepinfra(str(chunk_path))
        except Exception as exc:  # noqa: BLE001
            last_issue = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.error(
                f"❌ Ошибка DeepInfra для чанка {chunk_num}, попытка {attempt}/{max_attempts}: {last_issue}"
            )
            result = None

        if result and result.strip():
            cleaned = result.strip()
            if len(cleaned) < MIN_CHUNK_TEXT_LENGTH and attempt < max_attempts:
                last_issue = f"too_short({len(cleaned)})"
                logger.warning(
                    f"⚠️ DeepInfra вернул короткий текст для чанка {chunk_num} ({len(cleaned)} симв.). "
                    f"Повторяю попытку {attempt + 1}/{max_attempts}"
                )
            else:
                return cleaned
        else:
            last_issue = "empty"
            logger.warning(
                f"⚠️ DeepInfra вернул пустой текст для чанка {chunk_num} (попытка {attempt}/{max_attempts})"
            )

        if attempt < max_attempts:
            delay = min(2 ** attempt, 8)
            await asyncio.sleep(delay)

    logger.error(
        f"❌ Чанк {chunk_num} не распознан DeepInfra после {max_attempts} попыток (последняя проблема: {last_issue})"
    )
    return None


async def transcribe_long_audio_parallel_gemini(audio_path, duration, chunk_duration):
    """Транскрибирует длинное аудио через Gemini, разбивая на чанки и обрабатывая параллельно"""
    try:
        # Разбиваем на чанки
        chunks = await split_audio_into_chunks(audio_path, chunk_duration)
        
        if not chunks:
            logger.error("Не удалось разбить аудио на чанки, пробую транскрибировать целиком")
            return await transcribe_segment_with_openrouter_gemini(audio_path)
        
        logger.info(
            "Начинаю параллельную транскрибацию %s чанков через Gemini (длительность чанка %.1f мин)",
            len(chunks),
            chunk_duration / 60,
        )
        
        # Ограничиваем параллелизм (максимум 3 одновременно)
        MAX_PARALLEL = 3
        
        # Создаём задачи для транскрибации
        transcripts = []
        failed_chunks = []
        
        for i in range(0, len(chunks), MAX_PARALLEL):
            batch = chunks[i:i + MAX_PARALLEL]
            batch_start = i + 1
            batch_end = min(i + MAX_PARALLEL, len(chunks))
            logger.info(f"📦 Обрабатываю батч {i//MAX_PARALLEL + 1}: чанки {batch_start}-{batch_end} из {len(chunks)} через Gemini")
            
            # Запускаем батч параллельно
            tasks = [
                _transcribe_chunk_with_retry_gemini(chunk, i + idx + 1)
                for idx, chunk in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                chunk_num = i + j + 1
                if isinstance(result, Exception):
                    logger.error(f"❌ Исключение при транскрибации чанка {chunk_num}/{len(chunks)}: {type(result).__name__}: {str(result)[:200]}")
                    failed_chunks.append(chunk_num)
                elif result:
                    logger.info(f"✅ Чанк {chunk_num}/{len(chunks)} готов: {len(result)} символов")
                    transcripts.append(result)
                else:
                    logger.warning(f"⚠️ Чанк {chunk_num}/{len(chunks)} вернул пустой результат")
                    failed_chunks.append(chunk_num)
        
        # Логируем итоговую статистику
        if failed_chunks:
            logger.error(
                f"❌ Транскрибация завершена с ошибками: {len(failed_chunks)}/{len(chunks)} чанков упали. "
                f"Неудачные чанки: {failed_chunks}"
            )
        else:
            logger.info(f"✅ Все {len(chunks)} чанков транскрибированы успешно через Gemini")
        
        # Очищаем временные чанки
        try:
            chunk_dir = chunks[0].parent
            for chunk in chunks:
                chunk.unlink(missing_ok=True)
            chunk_dir.rmdir()
            logger.info("🧹 Временные чанки удалены")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить временные чанки: {e}")
        
        # Объединяем транскрипты
        full_transcript = "\n\n".join(transcripts)
        logger.info(f"📝 Все чанки объединены, общая длина: {len(full_transcript)} символов")

        if not full_transcript.strip():
            return None

        processed = await _postprocess_full_transcript(full_transcript)
        return processed
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при параллельной транскрибации через Gemini: {type(e).__name__}: {str(e)[:300]}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return None


async def transcribe_whole_audio_with_deepinfra(audio_path):
    """Транскрибирует аудио через DeepInfra API. 
    Для больших файлов (>30 мин) разбивает на чанки и обрабатывает параллельно."""
    if not DEEPINFRA_API_KEY:
        logger.warning("DeepInfra API ключ не настроен")
        return None

    try:
        audio_path = Path(audio_path)
        logger.info(f"Транскрибирую аудио: {audio_path}")

        # Сначала сжимаем аудио
        compressed_audio_path = await compress_audio_for_api(audio_path)

        # Получаем длительность аудио
        duration = await get_audio_duration(compressed_audio_path)
        logger.info(f"Длительность аудио: {duration:.1f} секунд ({duration/60:.1f} минут)")

        # Определяем, нужно ли разбивать на чанки
        MAX_CHUNK_DURATION = 30 * 60  # 30 минут в секундах
        
        used_chunk_mode = False

        if duration <= MAX_CHUNK_DURATION:
            # Короткий файл - транскрибируем целиком
            logger.info("Файл короткий, транскрибируем целиком")
            transcript_text = await transcribe_segment_with_deepinfra(compressed_audio_path)
        else:
            # Длинный файл - разбиваем на чанки и обрабатываем параллельно
            logger.info(f"Файл длинный ({duration/60:.1f} мин), разбиваю на чанки по {MAX_CHUNK_DURATION/60} минут")
            transcript_text = await transcribe_long_audio_parallel(compressed_audio_path, duration, MAX_CHUNK_DURATION)
            used_chunk_mode = True

        if transcript_text:
            logger.info(f"Транскрибация завершена, получено {len(transcript_text)} символов")

            # Очищаем временные файлы
            try:
                if compressed_audio_path != str(audio_path):
                    Path(compressed_audio_path).unlink()
            except:
                pass

            if not used_chunk_mode:
                transcript_text = await _postprocess_full_transcript(transcript_text)
            return transcript_text
        else:
            logger.error("Не удалось транскрибировать аудио")
            return None

    except Exception as e:
        logger.error(f"Ошибка при транскрибации аудио: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def get_audio_duration(audio_path):
    """Получает длительность аудио файла в секундах"""
    try:
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(audio_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
        else:
            logger.warning(f"Не удалось получить длительность аудио: {result.stderr}")
            return 0
    except Exception as e:
        logger.error(f"Ошибка при получении длительности: {e}")
        return 0


def _estimate_non_silence_duration(audio_path, *, silence_threshold_db: float = -40.0, min_silence_sec: float = 0.5) -> float:
    """Оценивает длительность звучащих (не тишина) участков аудио в секундах.

    Использует ffmpeg с фильтром silencedetect. При ошибке осторожно
    возвращает 0, чтобы не ломать основной пайплайн.
    """
    import subprocess
    import re

    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={silence_threshold_db}dB:d={min_silence_sec}",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Не удалось оценить тишину в аудио {audio_path}: {type(exc).__name__}: {exc}")
        return 0.0

    stderr = result.stderr or ""

    # Собираем интервалы тишины по сообщениям вида:
    # silence_start: 0
    # silence_end: 5.3 | silence_duration: 5.3
    start_re = re.compile(r"silence_start:\s*([0-9.]+)")
    end_re = re.compile(r"silence_end:\s*([0-9.]+)")

    starts: list[float] = [float(m.group(1)) for m in start_re.finditer(stderr)]
    ends: list[float] = [float(m.group(1)) for m in end_re.finditer(stderr)]

    # Грубая оценка: суммируем пары (start, end); если их число не совпадает,
    # просто обрезаем по минимальной длине списков.
    silence_total = 0.0
    for s, e in zip(starts, ends):
        if e > s:
            silence_total += e - s

    # Получаем общую длительность файла отдельным ffprobe-вызовом,
    # чтобы не зависеть от асинхронной get_audio_duration.
    duration = 0.0
    try:
        dur_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        dur_res = subprocess.run(
            dur_cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if dur_res.returncode == 0:
            duration = float((dur_res.stdout or "0").strip() or "0")
        else:
            logger.warning(
                "Не удалось получить длительность аудио через ffprobe: %s",
                dur_res.stderr,
            )
            duration = 0.0
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Ошибка при получении длительности аудио в _estimate_non_silence_duration: %s: %s",
            type(exc).__name__,
            exc,
        )
        duration = 0.0

    if duration <= 0:
        return 0.0

    non_silence = max(0.0, duration - silence_total)
    return non_silence


async def split_audio_into_chunks(audio_path, chunk_duration):
    """Разбивает аудио на чанки заданной длительности"""
    import subprocess
    import tempfile
    
    try:
        audio_path = Path(audio_path)
        chunk_dir = Path(tempfile.mkdtemp(prefix='audio_chunks_'))
        logger.info(f"Разбиваю аудио на чанки в {chunk_dir}")
        
        # Используем ffmpeg для разбивки
        # -f segment - разбивает на сегменты
        # -segment_time - длительность каждого сегмента
        chunk_pattern = str(chunk_dir / f"chunk_%03d{audio_path.suffix}")
        
        cmd = [
            'ffmpeg', '-i', str(audio_path),
            '-f', 'segment',
            '-segment_time', str(chunk_duration),
            '-c', 'copy',  # Копируем без перекодирования
            '-reset_timestamps', '1',
            chunk_pattern,
            '-y'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f"Ошибка разбивки аудио: {result.stderr}")
            return []
        
        # Получаем список созданных чанков
        chunks = sorted(chunk_dir.glob(f"chunk_*{audio_path.suffix}"))
        logger.info(f"Создано {len(chunks)} чанков")
        
        return chunks
        
    except Exception as e:
        logger.error(f"Ошибка при разбивке аудио: {e}")
        return []


async def transcribe_long_audio_parallel(audio_path, duration, chunk_duration):
    """Транскрибирует длинное аудио, разбивая на чанки и обрабатывая параллельно"""
    try:
        # Разбиваем на чанки
        chunks = await split_audio_into_chunks(audio_path, chunk_duration)
        
        if not chunks:
            logger.error("Не удалось разбить аудио на чанки, пробую транскрибировать целиком")
            return await transcribe_segment_with_deepinfra(audio_path)
        
        logger.info(f"Начинаю параллельную транскрибацию {len(chunks)} чанков")
        
        # Ограничиваем параллелизм (максимум 3 одновременно)
        MAX_PARALLEL = 3
        
        # Создаём задачи для транскрибации
        transcripts = []
        failed_chunks = []  # Отслеживаем упавшие чанки
        
        for i in range(0, len(chunks), MAX_PARALLEL):
            batch = chunks[i:i + MAX_PARALLEL]
            batch_start = i + 1
            batch_end = min(i + MAX_PARALLEL, len(chunks))
            logger.info(f"📦 Обрабатываю батч {i//MAX_PARALLEL + 1}: чанки {batch_start}-{batch_end} из {len(chunks)}")
            
            # Запускаем батч параллельно
            tasks = [
                _transcribe_chunk_with_retry_deepinfra(chunk, i + idx + 1)
                for idx, chunk in enumerate(batch)
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            for j, result in enumerate(batch_results):
                chunk_num = i + j + 1
                if isinstance(result, Exception):
                    logger.error(f"❌ Исключение при транскрибации чанка {chunk_num}/{len(chunks)}: {type(result).__name__}: {str(result)[:200]}")
                    failed_chunks.append(chunk_num)
                elif result:
                    logger.info(f"✅ Чанк {chunk_num}/{len(chunks)} готов: {len(result)} символов")
                    transcripts.append(result)
                else:
                    logger.warning(f"⚠️ Чанк {chunk_num}/{len(chunks)} вернул пустой результат (все попытки исчерпаны)")
                    failed_chunks.append(chunk_num)
        
        # Логируем итоговую статистику
        if failed_chunks:
            logger.error(
                f"❌ Транскрибация завершена с ошибками: {len(failed_chunks)}/{len(chunks)} чанков упали. "
                f"Неудачные чанки: {failed_chunks}"
            )
        else:
            logger.info(f"✅ Все {len(chunks)} чанков транскрибированы успешно")
        
        # Очищаем временные чанки
        try:
            chunk_dir = chunks[0].parent
            for chunk in chunks:
                chunk.unlink(missing_ok=True)
            chunk_dir.rmdir()
            logger.info("🧹 Временные чанки удалены")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось удалить временные чанки: {e}")
        
        # Объединяем транскрипты
        full_transcript = "\n\n".join(transcripts)
        logger.info(f"📝 Все чанки объединены, общая длина: {len(full_transcript)} символов")

        if not full_transcript.strip():
            return None

        processed = await _postprocess_full_transcript(full_transcript)
        return processed
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при параллельной транскрибации: {type(e).__name__}: {str(e)[:300]}")
        import traceback
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        return None

# Старая функция разбиения на сегменты удалена - теперь транскрибируем целиком

async def transcribe_segment_with_deepinfra(segment_path, max_retries=5):
    """
    Транскрибирует один сегмент аудио через DeepInfra API с улучшенной retry-логикой.
    
    Args:
        segment_path: путь к аудио файлу
        max_retries: максимальное количество попыток (по умолчанию 5)
    
    Returns:
        str: транскрибированный текст или None в случае ошибки
    """
    if not DEEPINFRA_API_KEY:
        logger.error("DEEPINFRA_API_KEY не установлен")
        return None

    url = "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo"
    headers = {"Authorization": f"Bearer {DEEPINFRA_API_KEY}"}
    file_name = Path(segment_path).name
    request_timeout_sec = max(60, int(os.getenv('DEEPINFRA_REQUEST_TIMEOUT_SEC', '300')))
    
    # Проверяем существование файла
    if not Path(segment_path).exists():
        logger.error(f"Файл {file_name} не найден: {segment_path}")
        return None
    
    file_size = Path(segment_path).stat().st_size
    logger.info(f"DeepInfra транскрипция начата: {file_name}, размер={file_size} байт, timeout={request_timeout_sec}s")
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Экспоненциальный backoff: 2^attempt секунд (0, 2, 4, 8, 16)
            if attempt > 0:
                backoff_delay = min(2 ** attempt, 30)  # максимум 30 секунд
                logger.info(f"Попытка {attempt + 1}/{max_retries} для {file_name} через {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)
            
            # Увеличиваем таймаут для повторных попыток
            current_timeout = request_timeout_sec + (attempt * 30)
            timeout = aiohttp.ClientTimeout(total=current_timeout)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                with open(segment_path, 'rb') as audio_file:
                    form_data = aiohttp.FormData()
                    form_data.add_field('language', os.getenv('WHISPER_LANGUAGE', 'ru'))
                    form_data.add_field('audio', audio_file, filename=file_name)
                    
                    async with session.post(url, headers=headers, data=form_data) as response:
                        if response.status == 200:
                            result = await response.json()
                            transcript_text = result.get('text', '').strip()
                            
                            if transcript_text:
                                logger.info(
                                    f"✅ Сегмент {file_name} транскрибирован успешно "
                                    f"(попытка {attempt + 1}/{max_retries}): {len(transcript_text)} символов"
                                )
                                return transcript_text
                            else:
                                logger.warning(f"⚠️ API вернул пустой текст для {file_name}, попытка {attempt + 1}/{max_retries}")
                                last_error = "empty_response"
                                continue
                        
                        # Временные ошибки - повторяем
                        elif response.status in (429, 500, 502, 503, 504):
                            error_text = await response.text()
                            logger.warning(
                                f"⚠️ Временная ошибка DeepInfra (статус {response.status}) для {file_name}, "
                                f"попытка {attempt + 1}/{max_retries}: {error_text[:200]}"
                            )
                            last_error = f"http_{response.status}"
                            continue
                        
                        # Постоянные ошибки - не повторяем
                        else:
                            error_text = await response.text()
                            logger.error(
                                f"❌ Критическая ошибка DeepInfra (статус {response.status}) для {file_name}: "
                                f"{error_text[:300]}"
                            )
                            return None
                            
        except asyncio.TimeoutError:
            logger.warning(
                f"⏱️ Таймаут при транскрибации {file_name}, "
                f"попытка {attempt + 1}/{max_retries}, timeout={current_timeout}s"
            )
            last_error = "timeout"
            continue
            
        except (aiohttp.ClientError, ConnectionResetError, OSError) as e:
            logger.warning(
                f"🌐 Сетевая ошибка при транскрибации {file_name}, "
                f"попытка {attempt + 1}/{max_retries}: {type(e).__name__}: {str(e)[:200]}"
            )
            last_error = f"network_{type(e).__name__}"
            
            # При первой же сетевой ошибке пробуем Gemini как fallback
            if attempt == 0 and OPENROUTER_API_KEY:
                logger.info(f"🔄 Первая сетевая ошибка DeepInfra - пробую OpenRouter Gemini для {file_name}")
                gemini_result = await transcribe_segment_with_openrouter_gemini(segment_path, max_retries=2)
                if gemini_result:
                    logger.info(f"✅ Gemini успешно обработал {file_name} после сбоя DeepInfra")
                    return gemini_result
                else:
                    logger.warning(f"⚠️ Gemini тоже не смог обработать {file_name}, продолжаю DeepInfra retry")
            
            continue
            
        except Exception as e:
            logger.error(
                f"❌ Неожиданная ошибка при транскрибации {file_name}, "
                f"попытка {attempt + 1}/{max_retries}: {type(e).__name__}: {str(e)[:300]}"
            )
            last_error = f"unexpected_{type(e).__name__}"
            # Для неожиданных ошибок не повторяем
            return None
    
    # Все попытки исчерпаны
    logger.error(
        f"❌ Не удалось транскрибировать {file_name} после {max_retries} попыток. "
        f"Последняя ошибка: {last_error}"
    )
    return None


async def transcribe_segment_with_openrouter_gemini(segment_path, max_retries=3):
    """
    Транскрибирует один сегмент аудио через OpenRouter API с Gemini 2.5 Flash Lite.
    Используется как fallback при сбоях DeepInfra.
    
    Args:
        segment_path: путь к аудио файлу
        max_retries: максимальное количество попыток (по умолчанию 3)
    
    Returns:
        str: транскрибированный текст или None в случае ошибки
    """
    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY не установлен")
        return None

    file_name = Path(segment_path).name
    
    # Проверяем существование файла
    if not Path(segment_path).exists():
        logger.error(f"Файл {file_name} не найден: {segment_path}")
        return None
    
    file_size = Path(segment_path).stat().st_size
    
    # Gemini имеет лимит ~15MB для аудио, проверяем
    if file_size > 15 * 1024 * 1024:
        logger.warning(f"Файл {file_name} слишком большой для Gemini ({file_size / 1024 / 1024:.1f}MB > 15MB)")
        return None
    
    logger.info(f"OpenRouter Gemini транскрипция начата: {file_name}, размер={file_size} байт")
    
    url = "https://openrouter.ai/api/v1/chat/completions"

    # Prefer an explicitly configured OpenRouter model if it looks like a Gemini model;
    # otherwise fall back to a known-good audio-capable Gemini variant.
    configured_model = (OPENROUTER_MODEL or "").strip()
    model_candidates = []
    if configured_model and "gemini" in configured_model.lower():
        model_candidates.append(configured_model)
    model_candidates.append("google/gemini-2.5-flash-lite-preview-09-2025")

    # A second candidate helps when the primary model intermittently returns empty content.
    # (Kept conservative to avoid unexpected costs.)
    if "google/gemini-2.5-flash" not in " ".join(model_candidates):
        model_candidates.append("google/gemini-2.5-flash")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://transkribator.local"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "Transkribator"),
    }
    
    last_error = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                backoff_delay = min(2 ** attempt, 10)
                logger.info(f"Попытка {attempt + 1}/{max_retries} для {file_name} через {backoff_delay}s...")
                await asyncio.sleep(backoff_delay)
            
            # Читаем аудио и конвертируем в base64
            import base64
            with open(segment_path, 'rb') as audio_file:
                audio_data = audio_file.read()
                audio_base64 = base64.b64encode(audio_data).decode('utf-8')
            
            # Определяем формат аудио для Gemini (не MIME type, а расширение)
            file_ext = Path(segment_path).suffix.lower()
            audio_formats = {
                '.mp3': 'mp3',
                '.wav': 'wav',
                '.ogg': 'ogg',
                '.oga': 'ogg',
                '.m4a': 'mp4',
                '.flac': 'flac',
            }
            audio_format = audio_formats.get(file_ext, 'mp3')
            
            model_to_use = model_candidates[min(attempt, len(model_candidates) - 1)]
            # Базовый промпт + явный запрет на длинные повторы
            base_prompt = (
                "Транскрибируй это аудио на русском. Верни чистый текст без разметки, времени и комментариев. "
                "Сохрани все детали, имена, цифры. Не повторяй слова и фразы, не дублируй предложения."
            )
            strict_suffix = (
                " ВАЖНО: если ты начинаешь повторять одно и то же слово или фразу подряд много раз, "
                "немедленно остановись и заверши ответ. Текст не должен содержать длинных последовательностей "
                "одинаковых слов или фраз."
            )
            prompt_text = base_prompt + strict_suffix

            temperature = GEMINI_TEMPERATURE_SCHEDULE[min(attempt, len(GEMINI_TEMPERATURE_SCHEDULE) - 1)]

            payload = {
                "model": model_to_use,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt_text,
                            },
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_base64,
                                    "format": audio_format
                                }
                            }
                        ]
                    }
                ],
                "temperature": temperature,
                "max_tokens": GEMINI_COMPLETION_TOKEN_LIMIT,
                "max_output_tokens": GEMINI_COMPLETION_TOKEN_LIMIT,
            }
            
            timeout = aiohttp.ClientTimeout(total=120)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()

                        # OpenRouter providers sometimes return text in different shapes.
                        choice0 = (result.get("choices") or [{}])[0] or {}
                        msg = choice0.get("message") or {}
                        transcript_text = (msg.get("content") or "").strip()

                        if not transcript_text:
                            # Some backends use `text` instead of `message.content`.
                            transcript_text = (choice0.get("text") or "").strip()
                        
                        if transcript_text:
                            logger.info(
                                f"✅ Сегмент {file_name} транскрибирован через Gemini "
                                f"(модель: {model_to_use}, попытка {attempt + 1}/{max_retries}): {len(transcript_text)} символов"
                            )
                            logger.debug(
                                "Gemini segment %s transcript (len=%s): %r",
                                file_name,
                                len(transcript_text),
                                transcript_text,
                            )
                            return transcript_text
                        else:
                            logger.warning(f"⚠️ Gemini вернул пустой текст для {file_name}")
                            last_error = "empty_response"
                            continue
                    
                    elif response.status in (429, 500, 502, 503, 504):
                        error_text = await response.text()
                        logger.warning(
                            f"⚠️ Временная ошибка OpenRouter (статус {response.status}) для {file_name}: "
                            f"{error_text[:200]}"
                        )
                        last_error = f"http_{response.status}"
                        continue
                    
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"❌ Ошибка OpenRouter (статус {response.status}) для {file_name}: "
                            f"{error_text[:300]}"
                        )
                        return None
                        
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Таймаут OpenRouter для {file_name}, попытка {attempt + 1}/{max_retries}")
            last_error = "timeout"
            continue
            
        except Exception as e:
            logger.error(
                f"❌ Ошибка OpenRouter для {file_name}, "
                f"попытка {attempt + 1}/{max_retries}: {type(e).__name__}: {str(e)[:300]}"
            )
            last_error = f"error_{type(e).__name__}"
            continue
    
    logger.error(
        f"❌ OpenRouter Gemini не смог транскрибировать {file_name} после {max_retries} попыток. "
        f"Последняя ошибка: {last_error}"
    )
    return None
