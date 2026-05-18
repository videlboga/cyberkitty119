import os
from pathlib import Path
from minimal_app.transcriber import transcribe_audio


def main():
    # sample.wav included in repo root
    repo_root = Path(__file__).resolve().parents[1]
    sample = repo_root / "sample.wav"
    if not sample.exists():
        print("sample.wav not found in repo root")
        return 2

    print("Using DEEPINFRA_MODEL:", os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo"))
    print("Starting transcription (DeepInfra if key present)...")
    res = transcribe_audio(str(sample))
    print("Result text:\n", res.get("text"))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
