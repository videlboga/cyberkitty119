#!/usr/bin/env python3
import tempfile
from pathlib import Path
import yt_dlp

def test_variant(name: str, ydl_opts: dict, url: str):
    # print a separator line of '=' characters
    print("\n" + "=" * 60)
    print(f"🧪 {name}")
    print("="*60)
    try:
        workspace = tempfile.mkdtemp(prefix="test_yt_")
        output_template = str(Path(workspace) / "%(id)s.%(ext)s")
        ydl_opts["outtmpl"] = output_template
        ydl_opts["noplaylist"] = True
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        
        mp3_path = Path(filename).with_suffix(".mp3")
        if not mp3_path.exists():
            candidates = sorted(Path(workspace).glob(f"{info.get('id', '')}*.mp3"))
            if candidates:
                mp3_path = candidates[0]
        
        if mp3_path.exists():
            size_mb = mp3_path.stat().st_size / (1024*1024)
            print(f"✅ УСПЕХ: {size_mb:.2f} МБ")
            return True
        else:
            print("❌ ОШИБКА: файл не найден")
            return False
    except Exception as e:
        print(f"❌ ОШИБКА: {type(e).__name__}")
        return False

url = "https://www.youtube.com/watch?v=8HXgpPphnL4"

test_variant("Современный User-Agent", {
    "format": "bestaudio/best",
    "quiet": True,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
}, url)

test_variant("Extractor-args android", {
    "format": "bestaudio/best",
    "quiet": True,
    "extractor_args": {"youtube": {"player_client": ["android"]}},
    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
}, url)

test_variant("Extractor-args android+web", {
    "format": "bestaudio/best",
    "quiet": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
}, url)
