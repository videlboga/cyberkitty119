#!/usr/bin/env python3
import sys
import subprocess
import json
import os
import traceback
from pathlib import Path

from transcribe_client.deepinfra import DeepInfraAdapter

def compress_audio(input_path: str) -> str:
    p = Path(input_path)
    out = p.parent / f"{p.stem}_compressed.mp3"
    cmd = [
        'ffmpeg', '-y', '-i', str(p), '-acodec', 'mp3', '-b:a', '64k', '-ar', '16000', '-ac', '1', str(out)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return str(out)
    except subprocess.CalledProcessError as e:
        print('Compression failed, falling back to original file', e)
        return str(p)


def main():
    if len(sys.argv) < 2:
        print('Usage: run_pipeline_requests.py <path-to-audio>')
        return 2
    file_path = sys.argv[1]
    print('Using file:', file_path)
    try:
        compressed = compress_audio(file_path)
        print('Compressed to:', compressed)
        adapter = DeepInfraAdapter()
        print('Adapter model:', adapter.model)
        res = adapter.transcribe(compressed)
        print('RESULT:')
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print('EXCEPTION:', type(e).__name__, str(e))
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
