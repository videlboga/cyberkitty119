"""Utility to download a Telegram file via local Bot API storage."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from transkribator_modules.config import BOT_TOKEN, logger
from transkribator_modules.utils.large_file_downloader import download_large_file


async def _run_download(file_id: str, destination: Path, expected_size: int | None) -> bool:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger.info(
        "Starting manual download via local Bot API",
        extra={"file_id": file_id, "destination": str(destination)},
    )
    return await download_large_file(
        bot_token=BOT_TOKEN,
        file_id=file_id,
        destination=destination,
        expected_size_bytes=expected_size,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download a Telegram file via the local Bot API cache.",
    )
    parser.add_argument("file_id", help="Telegram file_id to fetch")
    parser.add_argument(
        "--dest",
        default="/app/videos/manual_download.bin",
        help="Destination path inside the container (default: %(default)s)",
    )
    parser.add_argument(
        "--expected-size",
        type=int,
        default=None,
        help="Optional expected size in bytes to speed up cache probing",
    )
    args = parser.parse_args()

    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not configured inside the container")

    ok = asyncio.run(_run_download(args.file_id, Path(args.dest), args.expected_size))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

