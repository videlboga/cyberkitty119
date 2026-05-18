#!/usr/bin/env python3
import sys
import json
import traceback
import os
from pathlib import Path

from transcribe_client.deepinfra import DeepInfraAdapter


def main():
    if len(sys.argv) < 2:
        print("Usage: run_deepinfra_test.py <path-to-audio-file>")
        return 2
    file_path = sys.argv[1]
    print("Using file:", file_path)
    try:
        adapter = DeepInfraAdapter()
        print("Adapter model:", adapter.model)
        res = adapter.transcribe(file_path)
        print("RESULT:")
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print("EXCEPTION:", type(e).__name__, str(e))
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
