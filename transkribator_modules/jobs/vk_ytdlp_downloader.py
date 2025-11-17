"""Custom media downloader for VK/YouTube using yt-dlp, saving audio as mp3."""

import tempfile
from pathlib import Path
import yt_dlp

def download_vk_or_youtube_audio_mp3(url: str, workspace: str | Path = None) -> Path:
    """
    Download audio from VK/YouTube (or any yt-dlp supported) and save as mp3.
    Returns path to the resulting mp3 file.
    """
    if workspace is None:
        workspace = tempfile.mkdtemp(prefix="media_dl_")
    else:
        workspace = str(workspace)
    Path(workspace).mkdir(parents=True, exist_ok=True)
    output_template = str(Path(workspace) / "%(id)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
        # fallback: find any mp3 in workspace
        candidates = sorted(Path(workspace).glob(f"{info.get('id', '')}*.mp3"))
        if not candidates:
            raise FileNotFoundError("Не удалось скачать аудио (mp3) через yt-dlp")
        mp3_path = candidates[0]
    return mp3_path
