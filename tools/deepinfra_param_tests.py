#!/usr/bin/env python3
"""Run parameterized DeepInfra inference requests against a single audio file.

Writes results to tools/deepinfra_param_results.json

Usage:
  DEEPINFRA_API_KEY=... python tools/deepinfra_param_tests.py /path/to/audio.mp3

This script intentionally does NOT fall back to local whisper; it only tests DeepInfra.
"""
import os
import sys
import time
import json
from pathlib import Path
from itertools import product
from typing import Any, Dict

from requests import post


def run_request(file_path: Path, params: Dict[str, Any], timeout: int = 300) -> Dict[str, Any]:
    model = os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo")
    key = os.getenv("DEEPINFRA_API_KEY")
    url = f"https://api.deepinfra.com/v1/inference/{model}"
    headers = {"Authorization": f"Bearer {key}"}

    data = {}
    # map allowed params
    if "task" in params:
        data["task"] = params["task"]
    if "language" in params and params["language"]:
        data["language"] = params["language"]
    if "temperature" in params:
        data["temperature"] = str(params["temperature"])
    if "chunk_level" in params:
        data["chunk_level"] = params["chunk_level"]
    if "chunk_length_s" in params:
        data["chunk_length_s"] = str(params["chunk_length_s"])

    t0 = time.time()
    try:
        with open(file_path, "rb") as f:
            files = {"audio": (file_path.name, f, "application/octet-stream")}
            resp = post(url, headers=headers, files=files, data=data, timeout=timeout)

        elapsed = time.time() - t0
        result = {
            "status_code": resp.status_code,
            "elapsed": elapsed,
            "ok": resp.ok,
            "params": params,
        }
        # try parse json
        try:
            result_body = resp.json()
            result["body_json"] = result_body
        except Exception:
            text = resp.text
            result["body_text_snippet"] = text[:4000]

        return result

    except Exception as exc:
        elapsed = time.time() - t0
        return {"status_code": None, "ok": False, "error": f"{type(exc).__name__}: {str(exc)}", "elapsed": elapsed, "params": params}


def main():
    if len(sys.argv) < 2:
        print("Usage: python tools/deepinfra_param_tests.py /path/to/audio.mp3")
        return 2

    fp = Path(sys.argv[1])
    if not fp.exists():
        print("File not found:", fp)
        return 2

    key = os.getenv("DEEPINFRA_API_KEY")
    if not key:
        print("DEEPINFRA_API_KEY not set in environment")
        return 3

    # parameter grid to test
    tasks = ["transcribe"]
    chunk_levels = ["segment", "word"]
    chunk_lengths = [15, 30]
    temperatures = [0, 0.2]
    languages = [os.getenv("DEEPINFRA_LANGUAGE", "ru")]

    combos = []
    for t, cl, cl_s, temp, lang in product(tasks, chunk_levels, chunk_lengths, temperatures, languages):
        combos.append({"task": t, "chunk_level": cl, "chunk_length_s": cl_s, "temperature": temp, "language": lang})

    results = []
    out_file = Path(__file__).parent / "deepinfra_param_results.json"

    for idx, params in enumerate(combos, start=1):
        print(f"[{idx}/{len(combos)}] Testing params: {params}")
        res = run_request(fp, params)
        print(" -> status:", res.get("status_code"), "ok:", res.get("ok"), "elapsed:", round(res.get("elapsed", 0), 2))
        if res.get("body_text_snippet"):
            print("   body snippet:", res.get("body_text_snippet")[:400])
        results.append(res)
        # write partial results for safety
        try:
            out_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        except Exception:
            pass

    print("All done. Results written to", out_file)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
