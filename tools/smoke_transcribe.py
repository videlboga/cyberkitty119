#!/usr/bin/env python3
"""Smoke-run transcription helper.

Usage: python tools/smoke_transcribe.py /path/to/file

Tries adapters in order: LocalAdapter (HTTP), DiWorkerAdapter (docker), StubAdapter.
Writes result JSON to /tmp/smoke_transcribe_result.json and prints which adapter was used.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from transcribe_client import TranscribeClient
from transcribe_client.local import LocalAdapter
from transcribe_client.di_worker import DiWorkerAdapter
from transcribe_client.stub import StubAdapter


def main():
    p = argparse.ArgumentParser()
    p.add_argument("file", help="Path to media file to transcribe")
    args = p.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}")
        return 2

    # Try adapters in order
    adapters = [
        ("local", LocalAdapter()),
        ("di_worker", DiWorkerAdapter()),
        ("stub", StubAdapter()),
    ]

    last_exc = None
    for name, adapter in adapters:
        client = TranscribeClient(adapter=adapter)
        try:
            print(f"Trying adapter: {name}")
            res = client.transcribe(str(file_path), mode=name)
            out_path = Path("/tmp/smoke_transcribe_result.json")
            out_path.write_text(json.dumps({"adapter": name, "result": res}, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"SUCCESS with adapter: {name}")
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:  # pragma: no cover - runtime helper
            print(f"Adapter {name} failed: {exc}")
            last_exc = exc

    print("All adapters failed; last error:", last_exc)
    return 3


if __name__ == "__main__":
    sys.exit(main())
