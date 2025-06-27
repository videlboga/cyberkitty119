#!/usr/bin/env python3
"""Тестовый скрипт: поочерёдно отправляет в DeepInfra сегменты
разной длины (1–30 мин с шагом 5 мин) из одного аудиофайла.

Usage:
    python scripts/test_deepinfra_segments.py /path/to/audio.wav [MODEL_NAME]

Требует переменную окружения DEEPINFRA_API_KEY.
"""
import os
import sys
import time
import tempfile
import subprocess
import requests
from pathlib import Path

DURATIONS = [60, 300, 600, 900, 1200, 1500, 1800]  # 1,5,10,15,20,25,30 мин
DEFAULT_MODEL = "openai/whisper-large-v3-turbo"
API_URL_TEMPLATE = "https://api.deepinfra.com/v1/inference/{model}"


def cut_segment(src: Path, duration: int) -> Path:
    """Вырезает из начала файла отрезок <duration> секунд во временный mp3."""
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f"_{duration}s.mp3")
    os.close(tmp_fd)  # закрываем сразу, ffmpeg сам запишет
    cmd = [
        "ffmpeg", "-loglevel", "quiet",
        "-i", str(src),
        "-ss", "0", "-t", str(duration),
        "-c", "copy", "-y", tmp_path
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error (code {result.returncode})")
    return Path(tmp_path)


def send_to_deepinfra(audio_path: Path, token: str, model: str) -> requests.Response:
    with audio_path.open("rb") as f:
        files = {"audio": (audio_path.name, f, "audio/mpeg")}
        headers = {"Authorization": f"Bearer {token}"}
        url = API_URL_TEMPLATE.format(model=model)
        return requests.post(url, headers=headers, files=files, timeout=600)


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_deepinfra_segments.py <audio_file> [model]")
        sys.exit(1)

    audio_file = Path(sys.argv[1]).expanduser().resolve()
    if not audio_file.exists():
        print("Audio file not found:", audio_file)
        sys.exit(1)

    model = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_MODEL
    token = os.getenv("DEEPINFRA_API_KEY")
    if not token:
        print("DEEPINFRA_API_KEY env var not set")
        sys.exit(1)

    print(f"Testing DeepInfra model {model} on {audio_file}")
    for dur in DURATIONS:
        print("\n===", f"{dur//60} мин ({dur} сек)", "===")
        try:
            seg_path = cut_segment(audio_file, dur)
            start = time.time()
            resp = send_to_deepinfra(seg_path, token, model)
            elapsed = time.time() - start
            if resp.status_code == 200:
                txt = resp.json().get("text", "")
                print(f"✅ {resp.status_code} | {elapsed:.1f}s | text {len(txt)} chars")
                preview = txt[:120].replace("\n", " ")
                print("   preview:", preview)
            else:
                print(f"❌ {resp.status_code} | {elapsed:.1f}s | {resp.text[:100]}")
        except Exception as e:
            print(f"💥 Error for {dur}s: {e}")
        finally:
            if 'seg_path' in locals() and seg_path.exists():
                seg_path.unlink()

    print("\nDone.")


if __name__ == "__main__":
    main() 