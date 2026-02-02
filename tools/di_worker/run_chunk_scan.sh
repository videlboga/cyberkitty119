#!/usr/bin/env bash
set -euo pipefail

# Expect DEEPINFRA_API_KEY in env. If not present, try to source common env files
# from the repository root (so developers can keep values in env.sample or .env).
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." >/dev/null && pwd)
maybe_load_env() {
  for f in ".env" "env" "env.sample" ".env.sample"; do
    if [ -f "$REPO_ROOT/$f" ]; then
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

if [ -z "${DEEPINFRA_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  maybe_load_env || true
fi

if [ -z "${DEEPINFRA_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: DEEPINFRA_API_KEY or OPENAI_API_KEY not set (set USE_OPENAI=1 to prefer OpenAI)" >&2
  exit 3
fi

# default OpenAI model for transcription; can be overridden in env
OPENAI_TRANSCRIBE_MODEL=${OPENAI_TRANSCRIBE_MODEL:-gpt-4o-mini-transcribe}

file=${1:-/data/input.mp3}
outdir=${2:-/data/out/di_chunk_scan}
mkdir -p "$outdir"
metrics="$outdir/metrics.csv"
echo "run,chunk_level,chunk_length_s,temperature,http_code,elapsed_s,output_file" > "$metrics"
idx=0
chunk_levels=("none" "segment" "sentence")
lengths=("" 120 60 30 15 5)
for cl in "${chunk_levels[@]}"; do
  if [ "$cl" = "none" ]; then
    idx=$((idx+1))
    out="$outdir/result_${idx}.json"
    tracefile="$outdir/result_${idx}.curl_trace.txt"
    echo "Run $idx: whole-file (no chunking)"
    start=$(date +%s.%N)
    if [ "${USE_OPENAI:-0}" = "1" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
      echo "Run $idx: using OpenAI model $OPENAI_TRANSCRIBE_MODEL"
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer $OPENAI_API_KEY" -F "model=$OPENAI_TRANSCRIBE_MODEL" -F "file=@$file" -F "language=ru" --max-time "$CURL_MAX_TIME" || echo "000")
    else
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo?task=transcribe&language=ru" -H "Authorization: Bearer $DEEPINFRA_API_KEY" -F "audio=@$file" --max-time "$CURL_MAX_TIME" || echo "000")
    fi
    end=$(date +%s.%N)
    elapsed=$(awk "BEGIN{print $end - $start}")
    # redact token in trace
    if [ -f "$tracefile" ]; then
      sed -i -E 's/(Authorization: Bearer )[^[:space:]]+/\1[REDACTED]/I' "$tracefile" || true
    fi
    echo "$idx,whole,,0,$http_code,$elapsed,$out" >> "$metrics"
    sleep 1
  else
    for L in "${lengths[@]}"; do
      if [ -z "$L" ]; then
        continue
      fi
      idx=$((idx+1))
      out="$outdir/result_${idx}.json"
      tracefile="$outdir/result_${idx}.curl_trace.txt"
      echo "Run $idx: chunk_level=$cl chunk_length_s=$L"
      start=$(date +%s.%N)
      if [ "${USE_OPENAI:-0}" = "1" ] && [ -n "${OPENAI_API_KEY:-}" ]; then
        echo "Run $idx: chunk_level=$cl chunk_length_s=$L — using OpenAI $OPENAI_TRANSCRIBE_MODEL"
        # OpenAI doesn't have the same chunking query params; pass chunk info as form fields so server-side code can consume if needed
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer $OPENAI_API_KEY" -F "model=$OPENAI_TRANSCRIBE_MODEL" -F "file=@$file" -F "language=ru" -F "chunk_level=$cl" -F "chunk_length_s=$L" --max-time "$CURL_MAX_TIME" || echo "000")
      else
        url="https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo?task=transcribe&chunk_level=$cl&chunk_length_s=$L&language=ru"
  CURL_MAX_TIME=${OPENAI_CURL_MAX_TIME:-1800}
  http_code=$(curl --trace-ascii "$tracefile" -s -o "$out" -w "%{http_code}" -X POST "$url" -H "Authorization: Bearer $DEEPINFRA_API_KEY" -F "audio=@$file" --max-time "$CURL_MAX_TIME" || echo "000")
      fi
      end=$(date +%s.%N)
      elapsed=$(awk "BEGIN{print $end - $start}")
      # redact token in trace
      if [ -f "$tracefile" ]; then
        sed -i -E 's/(Authorization: Bearer )[^[:space:]]+/\1[REDACTED]/I' "$tracefile" || true
      fi
      echo "$idx,$cl,$L,0,$http_code,$elapsed,$out" >> "$metrics"
      sleep 1
    done
  fi
done

echo "Done. Metrics written to $metrics"
ls -lah "$outdir" | sed -n '1,200p'

# post-process each result JSON with extractor if present
if [ -f "/opt/di/extract_segments.py" ]; then
  if command -v python3 >/dev/null 2>&1; then
    for j in "$outdir"/result_*.json; do
      [ -f "$j" ] || continue
      python3 /opt/di/extract_segments.py "$j" "$outdir" || true
    done
  elif command -v python >/dev/null 2>&1; then
    for j in "$outdir"/result_*.json; do
      [ -f "$j" ] || continue
      python /opt/di/extract_segments.py "$j" "$outdir" || true
    done
  else
    echo "Note: extract_segments.py present but no python found" >&2
  fi
fi
