#!/usr/bin/env python3
"""Wrapper: prepare audio with di_worker container, transcribe with local Whisper HTTP, aggregate.

Usage:
  tools/run_prepare_and_transcribe.py <input_path> [--out-dir OUT]

Behavior:
  - Runs di_worker: `prepare_audio` inside the `cyberkitty119-di_worker:latest` image
    (must be available locally). It mounts the input parent dir as /input (ro) and
    the out-dir as /out (writable).
  - Looks for prepared artifacts in out-dir: chunk_*.wav or *_compressed.wav
  - Posts each chunk (or the single compressed file) to local Whisper HTTP at
    http://127.0.0.1:8001/transcribe and saves per-file JSONs and an aggregated
    `result_whisper.json` and `transcript.txt` in the out-dir.

This script is intended for developer integration testing and should be safe to
run repeatedly. It will print progress and errors.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import glob
import requests
from pathlib import Path


def run_prepare(input_path: Path, out_dir: Path, image: str = "cyberkitty119-di_worker:latest", fmt: str = "wav", bitrate: str = "64k") -> None:
    input_path = input_path.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # mount input parent as /input and out_dir as /out
    parent = input_path.parent
    container_input = f"/input/{input_path.name}"
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{str(parent)}:/input:ro",
        "-v",
        f"{str(out_dir)}:/out",
        image,
        "prepare_audio",
        container_input,
        "--out-dir",
        "/out",
        "--format",
        fmt,
        "--bitrate",
        bitrate,
    ]
    print("Running prepare_audio in container:", " ".join(shlex.quote(p) for p in cmd))
    subprocess.run(cmd, check=True)


def find_prepared(out_dir: Path) -> list[Path]:
    # chunks first
    chunks = sorted(out_dir.glob("chunk_*.wav"))
    if chunks:
        return chunks
    # fallback to compressed file
    compressed = list(out_dir.glob("*_compressed.*"))
    if compressed:
        return compressed
    # fallback to any wav
    anywav = sorted(out_dir.glob("*.wav"))
    return anywav


def post_to_whisper(file_path: Path, url: str = "http://127.0.0.1:8001/transcribe", timeout: int = 600) -> dict:
    payload = {"file_uri": str(file_path)}
    print(f"POST {file_path} -> {url}")
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def aggregate_results(results: list[dict], out_dir: Path) -> None:
    texts = []
    for r in results:
        t = r.get("text") if isinstance(r, dict) else None
        if t:
            texts.append(t.strip())
    combined = {"results": results, "text": "\n".join(texts)}
    out_file = out_dir / "result_whisper.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(combined, fh, ensure_ascii=False, indent=2)
    # also write plain transcript
    txt = out_dir / "transcript.txt"
    with open(txt, "w", encoding="utf-8") as fh:
        fh.write(combined["text"])
    print("Wrote:", out_file, txt)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--out-dir", default="/tmp/prepare_and_transcribe_out")
    p.add_argument("--image", default="cyberkitty119-di_worker:latest")
    p.add_argument("--format", default="wav")
    p.add_argument("--bitrate", default="64k")
    p.add_argument("--whisper-url", default=os.environ.get("WHISPER_SERVICE_URL", "http://127.0.0.1:8001/transcribe"))
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args(argv)

    inp = Path(args.input)
    out = Path(args.out_dir)
    # Normalize whisper URL: ensure it ends with '/transcribe'
    try:
        whisper_url = args.whisper_url.rstrip('/')
    except Exception:
        whisper_url = str(args.whisper_url)
    if not whisper_url.endswith('/transcribe'):
        whisper_url = whisper_url + '/transcribe'
    args.whisper_url = whisper_url
    try:
        run_prepare(inp, out, image=args.image, fmt=args.format, bitrate=args.bitrate)
    except subprocess.CalledProcessError as e:
        print("prepare_audio failed:", e)
        return 2

    prepared = find_prepared(out)
    if not prepared:
        print("No prepared files found in out-dir", out)
        return 3
    results = []
    for pth in prepared:
        try:
            r = post_to_whisper(pth, url=args.whisper_url, timeout=args.timeout)
            results.append(r)
            # save per-file json
            fname = out / (pth.stem + ".json")
            with open(fname, "w", encoding="utf-8") as fh:
                json.dump(r, fh, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Error transcribing", pth, e)
            results.append({"error": str(e)})

    aggregate_results(results, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
