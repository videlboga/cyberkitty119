#!/usr/bin/env bash
# Run the docs metadata validator inside a disposable Python container.
# Designed for contributors who can't install Python packages system-wide.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Running docs metadata validator in Docker..."

docker run --rm -v "$PWD":/work -w /work python:3.11-slim bash -lc \
  "python -m pip install --upgrade pip >/dev/null && pip install pyyaml >/dev/null && python .github/scripts/validate_metadata.py docs"

echo "Validator finished successfully."
