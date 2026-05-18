#!/usr/bin/env bash
set -euo pipefail

# Benchmark different chunk durations and curl timeouts against OpenAI transcription API.
# Usage:
#   run_benchmark_timeouts.sh /path/to/input.wav /path/to/outdir
# Optional env:
#   OPENAI_API_KEY (required)
#   OPENAI_TRANSCRIBE_MODEL (default: gpt-4o-mini-transcribe)
#   BENCH_DURATIONS (space-separated seconds, default: "60 120 240 300")
#   BENCH_TIMEOUTS (space-separated seconds, default: "300 900 1800")
#   BENCH_LANGUAGE (default: ru)
#
# Output:
#   outdir/bench_summary.csv
#   outdir/bench_chunks/*.wav
#   outdir/bench_results/*.json + *.trace.txt

input=${1:-/data/input.wav}
outdir=${2:-/data/out/bench}

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY is not set" >&2
  exit 2
fi

model=${OPENAI_TRANSCRIBE_MODEL:-gpt-4o-mini-transcribe}
bench_durations=${BENCH_DURATIONS:-"60 120 240 300"}
bench_timeouts=${BENCH_TIMEOUTS:-"300 900 1800"}
lang=${BENCH_LANGUAGE:-ru}

mkdir -p "$outdir/bench_chunks" "$outdir/bench_results"
summary="$outdir/bench_summary.csv"

echo "duration_s,timeout_s,http_code,elapsed_s,chunk_file,output_json" > "$summary"

# Prepare chunks with different durations
for dur in $bench_durations; do
  chunk="$outdir/bench_chunks/chunk_${dur}s.wav"
  # Re-encode to ensure WAV PCM 16k mono
  ffmpeg -y -i "$input" -t "$dur" -acodec pcm_s16le -ar 16000 -ac 1 "$chunk" >/dev/null 2>&1

done

# Run curl with different timeouts
for dur in $bench_durations; do
  chunk="$outdir/bench_chunks/chunk_${dur}s.wav"
  for timeout in $bench_timeouts; do
    out_json="$outdir/bench_results/result_${dur}s_${timeout}s.json"
    tracefile="$outdir/bench_results/result_${dur}s_${timeout}s.trace.txt"
    start=$(date +%s.%N)
    http_code=$(curl --trace-ascii "$tracefile" -s -o "$out_json" -w "%{http_code}" \
      -X POST "https://api.openai.com/v1/audio/transcriptions" \
      -H "Authorization: Bearer $OPENAI_API_KEY" \
      -F "model=$model" \
      -F "file=@$chunk" \
      -F "language=$lang" \
      --max-time "$timeout" || echo "000")
    end=$(date +%s.%N)
    elapsed=$(awk "BEGIN{print $end - $start}")
    # redact Authorization header in trace
    if [ -f "$tracefile" ]; then
      sed -i -E 's/(Authorization: Bearer )[^[:space:]]+/\1[REDACTED]/I' "$tracefile" || true
    fi
    echo "$dur,$timeout,$http_code,$elapsed,$chunk,$out_json" >> "$summary"
    echo "[bench] dur=${dur}s timeout=${timeout}s http=${http_code} elapsed=${elapsed}s"
  done
done

ls -lah "$outdir" | sed -n '1,200p'
