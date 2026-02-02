import argparse
import asyncio
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from dotenv import load_dotenv


def _log(msg: str) -> None:
    print(msg, flush=True)


async def call_gemini_with_audio(
    audio_path: Path,
    *,
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 8000,
) -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    audio_bytes = audio_path.read_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    ext = audio_path.suffix.lower()
    audio_formats = {
        ".mp3": "mp3",
        ".wav": "wav",
        ".ogg": "ogg",
        ".oga": "ogg",
        ".m4a": "mp4",
        ".flac": "flac",
    }
    audio_format = audio_formats.get(ext, "mp3")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_REFERER", "https://transkribator.local"),
        "X-Title": os.getenv("OPENROUTER_APP_NAME", "Transkribator"),
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_b64, "format": audio_format},
                    },
                ],
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "max_output_tokens": max_tokens,
    }

    timeout = httpx.Timeout(180.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
    text = resp.text
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {text[:400]}")
    data = json.loads(text)
    choice0 = (data.get("choices") or [{}])[0] or {}
    msg = choice0.get("message") or {}
    content = (msg.get("content") or "").strip()
    if not content:
        content = (choice0.get("text") or "").strip()
    return content


def split_audio(input_path: Path, chunk_seconds: int) -> list[Path]:
    tmpdir = Path(tempfile.mkdtemp(prefix="gemini_chunks_"))
    pattern = tmpdir / f"chunk_%03d{input_path.suffix}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        "-reset_timestamps",
        "1",
        str(pattern),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chunks = sorted(tmpdir.glob("chunk_*" + input_path.suffix))
    return chunks


async def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Run local OpenRouter ASR experiments on a single audio file."
    )
    parser.add_argument("audio", type=str, help="Path to compressed audio file (mp3/wav)")
    parser.add_argument(
        "--chunk-seconds",
        type=int,
        default=15 * 60,
        help="Chunk size in seconds for experiments (default: 900 = 15min)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Explicit OpenRouter model name (overrides OPENROUTER_MODEL).",
    )
    parser.add_argument(
        "--temp-base",
        type=float,
        default=0.0,
        help="Temperature for base prompt variant (default: 0.0).",
    )
    parser.add_argument(
        "--temp-strict",
        type=float,
        default=0.0,
        help="Temperature for strict prompt variant (default: 0.0).",
    )
    parser.add_argument(
        "--temp-small",
        type=float,
        default=0.1,
        help="Temperature for strict+small-chunk variant (default: 0.1).",
    )
    args = parser.parse_args()

    audio_path = Path(args.audio).resolve()
    if not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")

    model = args.model or os.getenv(
        "OPENROUTER_MODEL", "google/gemini-2.5-flash-lite-preview-09-2025"
    )

    _log(f"Using model: {model}")
    _log(f"Input audio: {audio_path}")

    # Каталог для экспериментов (чтобы не путать с боевыми файлами)
    model_slug = model.replace("/", "_")
    experiments_dir = audio_path.parent / f"experiments_{model_slug}"
    experiments_dir.mkdir(parents=True, exist_ok=True)

    # 1) Разбиваем на чанки меньшего размера
    _log(f"Splitting into chunks of {args.chunk_seconds} seconds...")
    chunks = split_audio(audio_path, args.chunk_seconds)
    _log(f"Created {len(chunks)} chunks in total.")

    # Берём один репрезентативный чанк для быстрых экспериментов
    if not chunks:
        raise SystemExit("No chunks produced")
    sample_chunk = chunks[0]
    _log(f"Sample chunk for experiments: {sample_chunk}")

    # Вариант A: текущий промпт из прод-кода
    prompt_base = (
        "Транскрибируй это аудио на русском. Верни чистый текст без разметки, времени и комментариев. "
        "Сохрани все детали, имена, цифры. Не повторяй слова и фразы, не дублируй предложения."
    )

    # Вариант B: усиленный запрет на повторы
    prompt_strict = (
        prompt_base
        + " ВАЖНО: если ты начинаешь повторять одно и то же слово или фразу подряд, НЕМЕДЛЕННО остановись "
          "и заверши ответ. Текст не должен содержать длинных последовательностей повторяющихся слов."
    )

    # 2) Базовый вызов
    _log(f"\n=== Variant A: base prompt, chunk={args.chunk_seconds}s, T={args.temp_base} ===")
    text_a = await call_gemini_with_audio(
        sample_chunk,
        prompt=prompt_base,
        model=model,
        temperature=args.temp_base,
        max_tokens=8000,
    )
    out_a = experiments_dir / f"{audio_path.stem}.gemini_A.txt"
    out_a.write_text(text_a, encoding="utf-8")
    _log(f"Saved Variant A transcript to: {out_a}")

    # 3) Усиленный промпт + чуть меньшие токены
    _log(f"\n=== Variant B: strict anti-repeat prompt, chunk={args.chunk_seconds}s, T={args.temp_strict} ===")
    text_b = await call_gemini_with_audio(
        sample_chunk,
        prompt=prompt_strict,
        model=model,
        temperature=args.temp_strict,
        max_tokens=6000,
    )
    out_b = experiments_dir / f"{audio_path.stem}.gemini_B_strict.txt"
    out_b.write_text(text_b, encoding="utf-8")
    _log(f"Saved Variant B transcript to: {out_b}")

    # 4) Тот же строгий промпт + лёгкая стохастика
    _log(f"\n=== Variant C: strict prompt, shorter chunk (5min), T={args.temp_small} ===")
    small_chunks = split_audio(audio_path, 5 * 60)
    if small_chunks:
        text_c = await call_gemini_with_audio(
            small_chunks[0],
            prompt=prompt_strict,
            model=model,
            temperature=args.temp_small,
            max_tokens=4000,
        )
        out_c = experiments_dir / f"{audio_path.stem}.gemini_C_strict_5min.txt"
        out_c.write_text(text_c, encoding="utf-8")
        _log(f"Saved Variant C transcript to: {out_c}")
    else:
        _log("No 5-minute chunks produced; skipping Variant C.")

    # Дополнительный эксперимент: несколько 10-минутных чанков с разной температурой
    sweep_chunk_sec = 600
    prod_temps = [0.2, 0.0, 0.4]
    repeats = 3
    _log(
        f"\n=== 10min sweep (production-like): "
        f"chunk={sweep_chunk_sec}s, temps={prod_temps}, repeats={repeats} ==="
    )
    sweep_chunks = split_audio(audio_path, sweep_chunk_sec)
    if not sweep_chunks:
        _log("No 10-minute chunks produced; skipping sweep.")
    else:
        for idx, chunk_path in enumerate(sweep_chunks):
            for t in prod_temps:
                for run in range(1, repeats + 1):
                    _log(f" -> chunk #{idx} ({chunk_path.name}), T={t}, run={run}")
                    try:
                        text = await call_gemini_with_audio(
                            chunk_path,
                            prompt=prompt_strict,
                            model=model,
                            temperature=t,
                            max_tokens=4000,
                        )
                    except Exception as e:  # noqa: BLE001
                        err_prefix = f"ERROR {type(e).__name__}: "
                        text = err_prefix + str(e)
                        _log(
                            f" !! Failed chunk #{idx}, T={t}, run={run}: "
                            f"{type(e).__name__}: {e}"
                        )

                    out_path = (
                        experiments_dir
                        / f"{audio_path.stem}.gemini_chunk{sweep_chunk_sec}"
                          f"_{idx:02d}_T{t:.1f}_R{run}.txt"
                    )
                    out_path.write_text(text, encoding="utf-8")
                    _log(f"Saved sweep transcript to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
