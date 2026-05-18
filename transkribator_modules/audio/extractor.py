import asyncio
from pathlib import Path

from transkribator_modules.config import logger


async def extract_audio_from_video(video_path, audio_path):
    """Извлекает аудио из видео с использованием ffmpeg."""
    video_path = Path(video_path)
    audio_path = Path(audio_path)

    try:
        audio_path.parent.mkdir(parents=True, exist_ok=True)

        # Проверяем, существует ли файл видео и его размер
        if not video_path.exists():
            logger.error(
                "Видео файл не найден",
                extra={"video": str(video_path)},
            )
            return False

        video_size_mb = video_path.stat().st_size / (1024 * 1024)

        logger.info(
            "Извлечение аудио",
            extra={"video": str(video_path), "audio": str(audio_path), "video_size_mb": video_size_mb},
        )

        # Сначала проверяем, есть ли аудио поток в видео
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1:nokey=1",
            str(video_path),
        ]

        try:
            probe_process = await asyncio.create_subprocess_exec(
                *probe_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            probe_stdout, probe_stderr = await asyncio.wait_for(probe_process.communicate(), timeout=5)
            probe_output = probe_stdout.decode(errors="ignore").strip()

            logger.info(
                "ffprobe результат",
                extra={"probe_output": probe_output, "return_code": probe_process.returncode},
            )

            if probe_process.returncode != 0 or not probe_output or "audio" not in probe_output.lower():
                logger.warning(
                    "Видео не содержит аудио потока",
                    extra={
                        "video": str(video_path),
                        "probe_stdout": probe_output,
                        "probe_stderr": probe_stderr.decode(errors="ignore"),
                    },
                )
                return False
        except asyncio.TimeoutError:
            logger.warning(
                "ffprobe timeout при проверке аудио потока",
                extra={"video": str(video_path)},
            )
        except Exception as probe_exc:
            logger.warning(
                "Ошибка при проверке аудио потока ffprobe",
                extra={"video": str(video_path), "error": str(probe_exc)},
            )

        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-y",
            str(audio_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            stderr_text = stderr.decode(errors="ignore")
            logger.error(
                "Ошибка при извлечении аудио ffmpeg",
                extra={
                    "video": str(video_path),
                    "return_code": process.returncode,
                    "stderr": stderr_text[:1000],  # Первые 1000 символов ошибки
                    "stdout": stdout.decode(errors="ignore")[:500],
                },
            )
            return False

        if audio_path.exists() and audio_path.stat().st_size > 0:
            audio_size_mb = audio_path.stat().st_size / (1024 * 1024)
            logger.info(
                "Аудио успешно извлечено",
                extra={"audio": str(audio_path), "size_mb": audio_size_mb, "original_video_mb": video_size_mb},
            )
            return True

        logger.error(
            "Извлеченный аудиофайл не создан или пустой",
            extra={"audio": str(audio_path), "exists": audio_path.exists()},
        )
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Ошибка при извлечении аудио",
            extra={"video": str(video_path), "error": str(exc), "error_type": type(exc).__name__},
        )
        return False


async def compress_audio_for_api(audio_path):
    """Сжатие аудио перед отправкой в API."""
    from transkribator_modules.transcribe.transcriber_v4 import (
        compress_audio_for_api as _compress_audio_for_api,
    )
    return await _compress_audio_for_api(audio_path)
