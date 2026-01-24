#!/usr/bin/env bash
set -euo pipefail

# Smoke test scaffold: place a test media file into the telegram-bot-api host volume
# and wait for the bot to copy it into its own videos folder. This is a helper
# for local developer runs — it does not assume any particular compose filename.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SAMPLE_FILE="$REPO_ROOT/sample.wav"

if [ ! -f "$SAMPLE_FILE" ]; then
  echo "No sample.wav found in repo root — create or copy a small test file as sample.wav" >&2
  exit 2
fi

echo "Placing sample file into telegram-bot-api host volume (make sure compose is running)..."

# Try to detect a bot token folder under telegram-bot-api-data
TGA_DIR=$(ls -d telegram-bot-api-data/* 2>/dev/null | head -n1 || true)
if [ -z "$TGA_DIR" ]; then
  echo "telegram-bot-api-data not found in repo root. Make sure docker-compose mounts ./telegram-bot-api-data to the service." >&2
  exit 2
fi

DEST_DIR="$TGA_DIR/videos"
mkdir -p "$DEST_DIR"
cp "$SAMPLE_FILE" "$DEST_DIR/test_manual_$(date +%s).wav"

echo "Placed sample into $DEST_DIR. Tail bot logs to watch for copy activity:"
echo "  docker compose logs -f bot"

echo "Smoke test helper finished — observe containers' logs for progress."
