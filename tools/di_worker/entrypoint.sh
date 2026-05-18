#!/usr/bin/env bash
set -euo pipefail

# Simple entrypoint: run subcommand in /opt/di
if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <run_chunk_scan|run_e2e> [args...]" >&2
  exit 2
fi

cmd="$1"; shift
case "$cmd" in
  run_chunk_scan)
    exec /opt/di/run_chunk_scan.sh "$@"
    ;;
  run_e2e)
    exec /opt/di/run_e2e.sh "$@"
    ;;
  prepare_audio)
    # Run the bundled prepare_audio script: prepare_audio <input> [--out-dir ...]
    exec /opt/di/prepare_audio.py "$@"
    ;;
  debug)
    # Run arbitrary debug command inside container after wg_entrypoint brings up wg0
    # Usage: debug <shell-cmd>
    exec /bin/bash -lc "$*"
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
