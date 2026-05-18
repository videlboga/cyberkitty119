#!/usr/bin/env python3
"""Simple CLI to verify that Yukassa webhook has been hit recently."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify last Yukassa webhook timestamp and emit non-zero status if stale."
    )
    parser.add_argument(
        "--status-file",
        default=str(Path("./data") / "yukassa_webhook_status.json"),
        help="Path to the status JSON file (default: ./data/yukassa_webhook_status.json)",
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=60 * 24,
        help="Maximum acceptable age in minutes (default: 1440 / 24h)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status_path = Path(args.status_file)
    if not status_path.exists():
        print(f"CRITICAL: status file {status_path} not found")
        return 2

    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"CRITICAL: failed to read {status_path}: {exc}")
        return 2

    timestamp = data.get("timestamp")
    if not timestamp:
        print(f"CRITICAL: timestamp missing in {status_path}")
        return 2

    try:
        ping_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except Exception as exc:  # noqa: BLE001
        print(f"CRITICAL: invalid timestamp '{timestamp}': {exc}")
        return 2

    age = datetime.now(timezone.utc) - ping_time
    max_age = timedelta(minutes=args.max_age_minutes)
    status = data.get("status")
    details = data.get("details", {})

    if age > max_age:
        print(
            f"CRITICAL: last Yukassa webhook {age} ago (status={status}, details={details}) exceeds {max_age}"
        )
        return 2

    print(
        f"OK: last Yukassa webhook {age} ago (status={status}, details={details}) within {max_age}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
