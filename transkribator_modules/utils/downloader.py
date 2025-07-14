#!/usr/bin/env python3
"""Скачивает видео/аудио из URL или YouTube.

Использование из других модулей:
    path = await download_media(url, target_dir)
Возвращает Path скачанного файла либо None.
"""
import asyncio
import re
import os
from pathlib import Path
from typing import Optional

from yt_dlp import YoutubeDL
import aiohttp

from transkribator_modules.config import logger

YOUTUBE_RE = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be)/")


async def _download_youtube(url: str, target_dir: Path) -> Optional[Path]:
    """Скачивает YouTube-ролик (только аудио) и возвращает путь к файлу .mp3"""
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(target_dir / "yt_%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    loop = asyncio.get_running_loop()
    try:
        def _sync():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return Path(ydl.prepare_filename(info)).with_suffix(".mp3")

        result: Path = await loop.run_in_executor(None, _sync)
        logger.info(f"YouTube файл скачан: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания YouTube: {e}")
        return None


async def _download_direct(url: str, target_dir: Path) -> Optional[Path]:
    """Скачивает файл по прямой ссылке"""
    filename = url.split("/")[-1].split("?")[0] or "download.bin"
    local_path = target_dir / filename
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                if resp.status != 200:
                    logger.error(f"HTTP {resp.status} при скачивании {url}")
                    return None
                with open(local_path, "wb") as f:
                    while True:
                        chunk = await resp.content.read(4096)
                        if not chunk:
                            break
                        f.write(chunk)
        logger.info(f"Файл скачан по URL: {local_path}")
        return local_path
    except Exception as e:
        logger.error(f"❌ Ошибка скачивания {url}: {e}")
        return None


async def download_media(url: str, target_dir: Path) -> Optional[Path]:
    """Определяет тип URL и скачивает медиаконтент. Возвращает Path к файлу."""
    target_dir.mkdir(exist_ok=True, parents=True)
    if YOUTUBE_RE.match(url):
        return await _download_youtube(url, target_dir)
    else:
        return await _download_direct(url, target_dir) 