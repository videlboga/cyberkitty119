#!/usr/bin/env python3
"""Prepare audio for transcription: download (yt-dlp/http), extract audio, compress and chunk.

Usage:
  prepare_audio.py <input> --out-dir /tmp/out --format mp3 --bitrate 64k --chunk-seconds 30

The input can be a local file path or a URL (YouTube, VK, Google Drive, Yandex, http(s)).
This script prefers yt-dlp when available for URL handling (supports many hosts).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
import sys
import os
import math


def _download_with_ytdlp(url: str, workspace: Path) -> Path:
    # Prefer python package, but fall back to system 'yt-dlp' CLI when not present.
    workspace.mkdir(parents=True, exist_ok=True)
    template = workspace / "%(id)s.%(ext)s"
    # Try python API first
    try:
        import yt_dlp  # type: ignore

        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(template),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        proxy = os.getenv("YTDLP_PROXY", "").strip()
        if proxy:
            opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        path = Path(filename)
        if not path.exists():
            candidates = sorted(workspace.glob(f"{info.get('id','')}.*"))
            if not candidates:
                raise FileNotFoundError("yt-dlp failed to download media")
            path = candidates[0]
        return path
    except Exception:
        # Fallback to system yt-dlp CLI
        ytdlp_bin = shutil.which("yt-dlp") or shutil.which("youtube-dl")
        if not ytdlp_bin:
            raise RuntimeError("yt-dlp not available (neither python package nor system binary)")
        outtmpl = str(template)
        cmd = [ytdlp_bin, "-f", "bestaudio/best", "-o", outtmpl, "--no-playlist", url]
        proxy = os.getenv("YTDLP_PROXY", "").strip()
        if proxy:
            cmd = [ytdlp_bin, "-f", "bestaudio/best", "-o", outtmpl, "--no-playlist", "--proxy", proxy, url]
        subprocess.run(cmd, check=True)
        # find downloaded file
        # yt-dlp writes with template id.ext; try to pick any file in workspace
        candidates = sorted(workspace.glob("*"))
        if not candidates:
            raise FileNotFoundError("yt-dlp CLI reported success but no file found in workspace")
        return candidates[-1]


def _download_http(url: str, dest: Path) -> Path:
    # Simple HTTP downloader using curl if available, otherwise requests.
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("curl"):
        cmd = ["curl", "-L", "-o", str(dest), url]
        subprocess.run(cmd, check=True)
        return dest
    try:
        import requests

        with requests.get(url, stream=True, allow_redirects=True) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
        return dest
    except Exception:
        raise


def extract_audio(input_path: Path, out_path: Path, *, fmt: str = "mp3", bitrate: str = "64k") -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "mp3":
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            bitrate,
            str(out_path),
        ]
    elif fmt == "wav":
        # produce PCM signed 16-bit little endian WAV (mono 16k) which OpenAI accepts
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ]
    elif fmt in ("opus", "ogg"):
        # produce Ogg Opus
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libopus",
            "-b:a",
            bitrate,
            str(out_path),
        ]
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return out_path


def split_audio_into_chunks(input_path: Path, chunk_seconds: int) -> list[Path]:
    # Reuse ffmpeg segment muxer, copy codec to avoid re-encode when possible
    tmpdir = Path(tempfile.mkdtemp(prefix="prep_chunks_"))
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


def prepare_audio(input_spec: str, out_dir: Path, *, fmt: str = "mp3", bitrate: str = "64k", chunk_seconds: int | None = None) -> dict:
    """Prepare audio: returns dict with keys: compressed, chunks (list)
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="prep_workspace_"))
    try:
        if Path(input_spec).exists():
            source = Path(input_spec).resolve()
        else:
            # assume URL: prefer yt-dlp but fallback to HTTP
            try:
                source = _download_with_ytdlp(input_spec, workspace)
            except Exception:
                dest = workspace / "downloaded_media"
                source = _download_http(input_spec, dest)

        stem = source.stem
        compressed_name = f"{stem}_compressed.{fmt if fmt != 'opus' else 'opus'}"
        compressed_path = out_dir / compressed_name
        extract_audio(source, compressed_path, fmt=fmt, bitrate=bitrate)
        chunks = []
        # If chunk_seconds is not provided, compute it from OpenAI upload limit (bytes)
        # Assumptions: for 'wav' (pcm_s16le 16k mono) bytes_per_sec = 16000 samples * 2 bytes = 32000
        # For compressed formats (mp3/opus) approximate bytes_per_sec from bitrate (e.g. '64k' -> 64000 bits/s -> 8000 B/s)
        if (not chunk_seconds or chunk_seconds <= 0):
            try:
                max_bytes = int(os.getenv("OPENAI_MAX_UPLOAD_BYTES", "26214400"))
            except Exception:
                max_bytes = 26214400
            fmt_l = fmt.lower()
            if fmt_l == "wav":
                bytes_per_sec = 16000 * 2
            else:
                # parse bitrate like '64k', '128k'
                b = bitrate.lower().strip()
                if b.endswith("k") and b[:-1].isdigit():
                    bits_per_sec = int(b[:-1]) * 1000
                else:
                    # fallback to 64 kbps
                    try:
                        bits_per_sec = int(b)
                    except Exception:
                        bits_per_sec = 64000
                bytes_per_sec = max(1, bits_per_sec // 8)
            # apply an upload margin to avoid hitting exact limit (default 10%)
            try:
                margin = float(os.getenv("OPENAI_UPLOAD_MARGIN", "0.1"))
            except Exception:
                margin = 0.1
            effective_max = max(1, int(max_bytes * (1.0 - margin)))
            # compute seconds we can fit into effective_max bytes
            computed = max(1, math.floor(effective_max / bytes_per_sec))
            # sanity clamp: avoid extremely long chunks, cap at 5 minutes (300s)
            chunk_seconds = min(computed, 300)
            # also set a reasonable lower bound (10s)
            chunk_seconds = max(chunk_seconds, 10)
            print(f"[prepare_audio] computed chunk_seconds={chunk_seconds} (fmt={fmt_l}, bitrate={bitrate}, bytes_per_sec={bytes_per_sec}, OPENAI_MAX_UPLOAD_BYTES={max_bytes}, margin={margin}, effective_max={effective_max})")
            print(f"[prepare_audio] computed chunk_seconds={chunk_seconds} (fmt={fmt_l}, bitrate={bitrate}, bytes_per_sec={bytes_per_sec}, OPENAI_MAX_UPLOAD_BYTES={max_bytes})")
        if chunk_seconds and chunk_seconds > 0:
            chunks = split_audio_into_chunks(compressed_path, int(chunk_seconds))
            # move chunks into out_dir
            moved = []
            for c in chunks:
                dest = out_dir / c.name
                shutil.move(str(c), str(dest))
                moved.append(dest)
            chunks = moved
        return {"compressed": compressed_path, "chunks": chunks, "workspace": workspace}
    except Exception:
        # cleanup in error case
        shutil.rmtree(workspace, ignore_errors=True)
        raise


def _cli() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--out-dir", default="/tmp/prep_out")
    p.add_argument("--format", default="wav", choices=["mp3", "opus", "wav"]) 
    p.add_argument("--bitrate", default="64k")
    p.add_argument("--chunk-seconds", type=int, default=0)
    args = p.parse_args()
    res = prepare_audio(args.input, Path(args.out_dir), fmt=args.format, bitrate=args.bitrate, chunk_seconds=(args.chunk_seconds or None))
    print("COMPRESSED:", res["compressed"])
    print("CHUNKS:", res["chunks"]) 


if __name__ == "__main__":
    _cli()
