import os
from pathlib import Path
import sys
from requests import post

def main(path: str):
    model = os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo")
    key = os.getenv("DEEPINFRA_API_KEY")
    if not key:
        print("DEEPINFRA_API_KEY not set in environment", file=sys.stderr)
        return 2

    url = f"https://api.deepinfra.com/v1/inference/{model}"
    p = Path(path)
    if not p.exists():
        print(f"File not found: {p}", file=sys.stderr)
        return 2

    data = {
        "task": os.getenv("DEEPINFRA_TASK", "transcribe"),
        "temperature": os.getenv("DEEPINFRA_TEMPERATURE", "0"),
        "chunk_level": os.getenv("DEEPINFRA_CHUNK_LEVEL", "segment"),
        "chunk_length_s": os.getenv("DEEPINFRA_CHUNK_LENGTH_S", "30"),
    }
    # include language if provided
    lang = os.getenv("DEEPINFRA_LANGUAGE")
    if lang:
        data["language"] = lang

    print("Will POST to:", url)
    print("Multipart fields: files -> ('audio', <file>), data ->", data)

    try:
        with open(p, "rb") as f:
            files = {"audio": (p.name, f, "application/octet-stream")}
            headers = {"Authorization": f"Bearer {key}"}
            resp = post(url, headers=headers, files=files, data=data, timeout=300)

        print("HTTP status:", resp.status_code)
        body = resp.text
        if not body:
            print("Empty response body")
        else:
            print("Response body (first 4000 chars):")
            print(body[:4000])
        return 0
    except Exception as e:
        print("Request failed:", type(e).__name__, e, file=sys.stderr)
        return 3


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python deepinfra_debug.py /path/to/audiofile", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
