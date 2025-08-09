import asyncio
from pathlib import Path
import sys
import os

# Добавляем корневую директорию проекта в sys.path
current_dir = Path(__file__).parent.resolve()
sys.path.append(str(current_dir))

try:
    from transkribator_modules.transcribe.transcriber import split_and_transcribe_audio, format_transcript_with_llm
    from transkribator_modules.audio.extractor import extract_audio_from_video
    from transkribator_modules.config import TRANSCRIPTIONS_DIR, AUDIO_DIR, logger
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Убедитесь, что скрипт находится в корневой директории проекта"
          " и все зависимости установлены.")
    sys.exit(1)

async def transcribe_video_with_segments(video_file_path_str):
    """Транскрибирует видео, разбивая аудио на сегменты для обработки через DeepInfra API."""
    video_file_path = Path(video_file_path_str)

    if not video_file_path.exists():
        print(f"Ошибка: Видеофайл не найден: {video_file_path}")
        return

    # Убедимся, что директории существуют
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPTIONS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Начинаю обработку видео: {video_file_path}")
    
    # Шаг 1: Извлекаем аудио из видео
    print("Шаг 1: Извлечение аудио из видео...")
    audio_path = AUDIO_DIR / f"{video_file_path.stem}.wav"
    
    try:
        await extract_audio_from_video(video_file_path, audio_path)
        print(f"Аудио извлечено: {audio_path}")
    except Exception as e:
        print(f"Ошибка при извлечении аудио: {e}")
        return

    # Шаг 2: Транскрибируем аудио с разбивкой на сегменты
    print("Шаг 2: Транскрибация аудио через DeepInfra API (сегментированный подход)...")
    
    try:
        raw_transcript = await split_and_transcribe_audio(audio_path)
        
        if not raw_transcript:
            print("Ошибка: Не удалось получить транскрипцию")
            return
            
        print(f"Получена сырая транскрипция длиной {len(raw_transcript)} символов")
        
        # Сохраняем сырую транскрипцию
        raw_transcript_path = TRANSCRIPTIONS_DIR / f"{video_file_path.stem}_raw.txt"
        with open(raw_transcript_path, 'w', encoding='utf-8') as f:
            f.write(raw_transcript)
        print(f"Сырая транскрипция сохранена: {raw_transcript_path}")
        
    except Exception as e:
        print(f"Ошибка при транскрибации: {e}")
        return

    # Шаг 3: Форматируем транскрипцию с помощью LLM
    print("Шаг 3: Форматирование транскрипции с помощью LLM...")
    
    try:
        formatted_transcript = await format_transcript_with_llm(raw_transcript)
        
        if formatted_transcript and formatted_transcript != raw_transcript:
            # Сохраняем отформатированную транскрипцию
            formatted_transcript_path = TRANSCRIPTIONS_DIR / f"{video_file_path.stem}_formatted.txt"
            with open(formatted_transcript_path, 'w', encoding='utf-8') as f:
                f.write(formatted_transcript)
            print(f"Отформатированная транскрипция сохранена: {formatted_transcript_path}")
        else:
            print("Форматирование не удалось или не требуется, используем сырую транскрипцию")
            formatted_transcript_path = raw_transcript_path
            
    except Exception as e:
        print(f"Ошибка при форматировании: {e}")
        formatted_transcript_path = raw_transcript_path

    # Шаг 4: Очистка временных файлов
    print("Шаг 4: Очистка временных файлов...")
    try:
        if audio_path.exists():
            audio_path.unlink()
            print("Временный аудиофайл удален")
    except Exception as e:
        print(f"Предупреждение: Не удалось удалить временный файл {audio_path}: {e}")

    print("\n=== ТРАНСКРИБАЦИЯ ЗАВЕРШЕНА ===")
    print(f"Сырая транскрипция: {raw_transcript_path}")
    print(f"Финальная транскрипция: {formatted_transcript_path}")
    
    # Показываем превью результата
    try:
        with open(formatted_transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
            preview = content[:500] + "..." if len(content) > 500 else content
            print(f"\nПревью результата:\n{preview}")
    except Exception as e:
        print(f"Не удалось показать превью: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python manual_transcribe_segments.py <путь_к_видеофайлу>")
        print("Пример: python manual_transcribe_segments.py /home/cyberkitty/Videos/video1254700787.mp4")
        sys.exit(1)
    
    video_path_arg = sys.argv[1]
    asyncio.run(transcribe_video_with_segments(video_path_arg)) 