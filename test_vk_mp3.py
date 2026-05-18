#!/usr/bin/env python3
"""Тест скачивания mp3 с VK через yt-dlp"""
import tempfile
from pathlib import Path
import yt_dlp

def download_audio_mp3(url: str) -> Path:
    workspace = tempfile.mkdtemp(prefix="test_ytdlp_")
    output_template = str(Path(workspace) / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
    
    mp3_path = Path(filename).with_suffix(".mp3")
    if not mp3_path.exists():
        candidates = sorted(Path(workspace).glob(f"{info.get('id', '')}*.mp3"))
        if candidates:
            mp3_path = candidates[0]
        else:
            raise FileNotFoundError("Не удалось скачать аудио (mp3) через yt-dlp")
    
    return mp3_path

if __name__ == "__main__":
    url = "https://vkvideo.ru/video-5225_456241671"
    print(f"🔄 Скачиваю mp3 с {url}")
    result = download_audio_mp3(url)
    print(f"✅ Скачано: {result}")
    print(f"📊 Размер: {result.stat().st_size / (1024*1024):.2f} МБ")
