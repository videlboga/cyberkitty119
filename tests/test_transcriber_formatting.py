import textwrap

from transkribator_modules.transcribe.transcriber_v4 import (
    _detect_repeating_phrase,
    _dedupe_transcript_text,
    _is_formatted_transcript_valid,
)


def test_detect_repeating_phrase_simple_repetition() -> None:
    base = "та-та-та"
    # Строим строку с заведомо заедающей фразой
    noisy = ("префикс " + (" " + base) * 8 + " суффикс").strip()

    phrase = _detect_repeating_phrase(noisy)

    assert phrase is not None
    assert "та-та" in phrase


def test_dedupe_transcript_text_removes_repeated_lines() -> None:
    lines = [
        "Это нормальная строка.",
        "Повторяющаяся строка.",
        "Повторяющаяся строка.",
        "Повторяющаяся строка.",
        "Финальная строка.",
    ]
    text = "\n".join(lines)

    deduped = _dedupe_transcript_text(text)

    # Дубликаты подряд идущей строки должны быть схлопнуты
    assert "Повторяющаяся строка.\nПовторяющаяся строка." not in deduped
    assert deduped.count("Повторяющаяся строка.") == 1


def test_is_formatted_transcript_valid_accepts_similar_text() -> None:
    raw = textwrap.dedent(
        """
        Это очень длинный текст встречи без пунктуации который
        содержит много слов и фраз но при этом смысл сохраняется
        достаточно хорошо чтобы можно было понять о чем именно идет речь
        участники обсуждают планы задачи и результаты прошлых действий
        """
    ).strip()

    formatted = textwrap.dedent(
        """
        Это очень длинный текст встречи, без пунктуации, который
        содержит много слов и фраз, но при этом смысл сохраняется
        достаточно хорошо, чтобы можно было понять, о чём именно идёт речь.
        Участники обсуждают планы, задачи и результаты прошлых действий.
        """
    ).strip()

    is_valid, reason = _is_formatted_transcript_valid(raw, formatted)

    assert is_valid is True
    assert reason is None


def test_is_formatted_transcript_valid_rejects_aggressively_shortened_text() -> None:
    # Строим исходный текст с большим количеством токенов
    raw = " ".join(["слово"] * 120)
    # "Модель" вернула только один короткий абзац
    formatted = "короткое саммари без деталей"

    is_valid, reason = _is_formatted_transcript_valid(raw, formatted)

    assert is_valid is False
    assert reason is not None

