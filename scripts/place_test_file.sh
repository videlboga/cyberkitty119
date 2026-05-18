#!/usr/bin/env bash
set -euo pipefail

# Utility to copy the repo sample file into the telegram-bot-api volume
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLE="$ROOT/sample.wav"

if [ ! -f "$SAMPLE" ]; then
  echo "No sample.wav in repo root. Create or copy a small test file named sample.wav" >&2
  exit 2
fi

DEST_DIR=$(ls -d telegram-bot-api-data/*/videos 2>/dev/null | head -n1 || true)
if [ -z "$DEST_DIR" ]; then
  echo "telegram-bot-api-data/*/videos not found — ensure docker-compose mounts the volume" >&2
  exit 2
fi

cp "$SAMPLE" "$DEST_DIR/test_$(date +%s).wav"
echo "Copied sample.wav -> $DEST_DIR"
