#!/usr/bin/env bash
set -uo pipefail

# Transcribe prepared WAV chunks via vpnspace netns and OpenAI.
# Usage: transcribe_vpnspace.sh /path/to/chunk_dir /path/to/out_dir
# Requires: OPENAI_API_KEY in env or .env in repo root.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." >/dev/null && pwd)

chunk_dir=${1:-}
out_dir=${2:-}

if [ -z "$chunk_dir" ] || [ -z "$out_dir" ]; then
  echo "Usage: $0 /path/to/chunk_dir /path/to/out_dir" >&2
  exit 2
fi

if [ -z "${OPENAI_API_KEY:-}" ] && [ -f "$REPO_ROOT/.env" ]; then
  OPENAI_API_KEY=$(grep -m1 '^OPENAI_API_KEY=' "$REPO_ROOT/.env" | sed 's/^OPENAI_API_KEY=//' | tr -d '\r')
  export OPENAI_API_KEY
fi

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY is not set" >&2
  exit 3
fi

model=${OPENAI_TRANSCRIBE_MODEL:-gpt-4o-mini-transcribe}
lang=${OPENAI_TRANSCRIBE_LANGUAGE:-ru}
# default max time for curl (seconds)
max_time=${OPENAI_CURL_MAX_TIME:-3600}
# concurrency for parallel chunk uploads
concurrency=${OPENAI_CONCURRENCY:-3}

mkdir -p "$out_dir"

# temp dir for traces/results
tmpd=$(mktemp -d 2>/dev/null || mktemp -d -t transcribe_vpn)
trap 'rm -rf "$tmpd"' EXIT

echo "Running with concurrency=$concurrency, max_time=$max_time"

# start background jobs, limit concurrency via wait -n
started=0
for chunk in $(ls -1 "$chunk_dir"/chunk_*.wav | sort); do
  base=$(basename "$chunk" .wav)
  out_json="$out_dir/${base}.json"
  trace1="$tmpd/${base}.trace.txt"
  trace2="$tmpd/${base}.retry.trace.txt"

  echo "[chunk] $base"

  (
    # first attempt
    first=$(sudo ip netns exec vpnspace curl --trace-ascii "$trace1" -s -o "$out_json" -w "%{http_code} %{time_total}\n" -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer $OPENAI_API_KEY" -F "model=$model" -F "file=@$chunk" -F "language=$lang" --max-time $max_time) || first="000 0"
    echo "$first"
    http_code=$(echo "$first" | awk '{print $1}')

    if [ "$http_code" != "200" ]; then
      echo "[chunk] $base - first attempt code=$http_code -> retrying with --http1.1"
      retry_max=$(( max_time * 3 ))
      # retry will write to same out_json (overwrite) and a retry trace
      retry=$(sudo ip netns exec vpnspace curl --http1.1 --trace-ascii "$trace2" -s -o "$out_json" -w "%{http_code} %{time_total}\n" -X POST "https://api.openai.com/v1/audio/transcriptions" -H "Authorization: Bearer $OPENAI_API_KEY" -F "model=$model" -F "file=@$chunk" -F "language=$lang" --max-time $retry_max) || retry="000 0"
      echo "[chunk] retry -> $retry"
    fi
  ) &

  started=$((started+1))
  # limit concurrency
  while [ $(jobs -rp | wc -l) -ge "$concurrency" ]; do
    # wait for any job to finish
    wait -n || true
  done
done

# wait for remaining background jobs
wait || true

# combine JSON outputs into transcript

OUT_DIR="$out_dir" python3 - <<'PY'
import json, glob, os
out_dir = os.environ['OUT_DIR']
files = sorted(glob.glob(os.path.join(out_dir, 'chunk_*.json')))
texts = []
for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
            text = data.get('text') or ''
            if text.strip():
                texts.append(text.strip())
    except Exception as e:
        texts.append(f"[ERROR reading {f}: {e}]")
with open(os.path.join(out_dir, 'transcript.txt'), 'w', encoding='utf-8') as out:
    out.write('\n'.join(texts))
print('\n'.join(texts))
PY
