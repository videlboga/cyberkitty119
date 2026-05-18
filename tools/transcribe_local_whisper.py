#!/usr/bin/env python3
"""Local transcription helper using faster-whisper.


Usage:
    tools/transcribe_local_whisper.py /path/to/chunk_dir /path/to/out_dir [--model medium] [--device cpu]

Produces per-chunk JSON files with a simple {'text': ...} shape and a combined transcript.txt
in the out_dir. Defaults to model='medium' and device='cpu' (useful for test runs that prioritise
better quality over minimal footprint).

This is intended as a drop-in quick tester to avoid using the remote API.
"""
import sys
import os
import argparse
import json
from pathlib import Path

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('chunk_dir')
    p.add_argument('out_dir')
    p.add_argument('--model', default='medium', help='Whisper model id (tiny, base, small, medium, etc)')
    p.add_argument('--device', default='cpu', help='Device to run on (cpu or cuda)')
    return p.parse_args()

def main():
    args = parse_args()
    chunk_dir = Path(args.chunk_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print('ERROR: faster_whisper is not installed or failed to import:', e, file=sys.stderr)
        sys.exit(2)

    model = WhisperModel(args.model, device=args.device)

    files = sorted(chunk_dir.glob('chunk_*.wav'))
    if not files:
        print('No chunk_*.wav files found in', chunk_dir, file=sys.stderr)
        sys.exit(3)

    combined_texts = []
    for f in files:
        base = f.stem
        outjson = out_dir / f'{base}.json'
        print('Transcribing', f)
        segments, info = model.transcribe(str(f), language='ru')
        text = ''.join([s.text for s in segments]).strip()
        combined_texts.append(text)
        with outjson.open('w', encoding='utf-8') as fh:
            json.dump({'text': text, 'model': args.model, 'duration': info.duration}, fh, ensure_ascii=False)

    with (out_dir / 'transcript.txt').open('w', encoding='utf-8') as out:
        out.write('\n'.join([t for t in combined_texts if t.strip()]))

    print('Done. Outputs in', out_dir)

if __name__ == '__main__':
    main()
