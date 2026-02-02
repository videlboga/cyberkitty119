#!/usr/bin/env bash
set -euo pipefail

# E2E runner: assumes audio is already prepared and accepts an audio file as input
# Usage: run_e2e.sh /path/to/input.mp3 [outdir]

# If DEEPINFRA_API_KEY isn't in the environment, try to source common env files
# from the repository root so developers can keep credentials in `.env`/`env.sample`.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." >/dev/null && pwd)
maybe_load_env() {
  # look for .env, env, env.sample, .env.sample at repo root
  for f in ".env" "env" "env.sample" ".env.sample"; do
    if [ -f "$REPO_ROOT/$f" ]; then
      # shellcheck disable=SC1090
      set -a
      # shellcheck disable=SC1090
      . "$REPO_ROOT/$f"
      set +a
      echo "Sourced environment from $REPO_ROOT/$f"
      return 0
    fi
  done
  return 1
}

if [ -z "${DEEPINFRA_API_KEY:-}" ]; then
  maybe_load_env || true
fi

# allow using OpenAI as an alternative: set USE_OPENAI=1 and OPENAI_API_KEY
if [ -z "${DEEPINFRA_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: DEEPINFRA_API_KEY or OPENAI_API_KEY not set (set USE_OPENAI=1 to prefer OpenAI)" >&2
  exit 3
fi

# default OpenAI model for transcription; can be overridden in env
OPENAI_TRANSCRIBE_MODEL=${OPENAI_TRANSCRIBE_MODEL:-gpt-4o-mini-transcribe}

audio=${1:-/data/input.mp3}
outdir=${2:-/data/out/di_e2e}
mkdir -p "$outdir"

# call single transcription (whole file)
out="$outdir/result_whole.json"
tracefile="$outdir/result_whole.curl_trace.txt"
start=$(date +%s.%N)
# decide provider: OpenAI (preferred when USE_OPENAI=1 and OPENAI_API_KEY present) or DeepInfra
if [ "${USE_OPENAI:-0}" = "1" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
  echo "Using OpenAI model $OPENAI_TRANSCRIBE_MODEL"
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer $OPENAI_API_KEY" -F "model=$OPENAI_TRANSCRIBE_MODEL" -F "file=@$audio" -F "language=ru" --max-time "$CURL_MAX_TIME" || echo "000")
else
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo?task=transcribe&language=ru" -H "Authorization: Bearer $DEEPINFRA_API_KEY" -F "audio=@$audio" --max-time "$CURL_MAX_TIME" || echo "000")
fi
end=$(date +%s.%N)
elapsed=$(awk "BEGIN{print $end - $start}")

# redact Authorization header in trace to avoid leaking token in outputs
if [ -f "$tracefile" ]; then
  sed -i -E 's/(Authorization: Bearer )[^[:space:]]+/\1[REDACTED]/I' "$tracefile" || true
fi

echo "http_code=$http_code elapsed_s=$elapsed output=$out trace=$tracefile"
ls -lah "$outdir" | sed -n '1,200p'

# If extractor is available, run it to produce CSV and plain transcript
if [ -x "/opt/di/extract_segments.py" ] || [ -f "/opt/di/extract_segments.py" ]; then
  if command -v python3 >/dev/null 2>&1; then
    python3 /opt/di/extract_segments.py "$out" "$outdir" || true
  elif command -v python >/dev/null 2>&1; then
    python /opt/di/extract_segments.py "$out" "$outdir" || true
  else
    echo "Note: extract_segments.py exists but no python interpreter found in PATH" >&2
  fi
fi
