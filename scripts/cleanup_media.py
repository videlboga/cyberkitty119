#!/usr/bin/env python3
"""Cleanup utility for pruning cached media artifacts.

By default the script removes files older than the retention window from the
standard media directories (videos, audio, telegram-bot-api-data). Optionally
it can enforce a maximum total size per directory by deleting the oldest
remaining files until the target is met.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_MEDIA_DIRS = ("videos", "audio", "telegram-bot-api-data")


@dataclass(slots=True)
class FileInfo:
    path: Path
    size: int
    mtime: float


def iter_files(root: Path) -> Iterable[FileInfo]:
    for path in root.rglob("*"):
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        yield FileInfo(path=path, size=stat.st_size, mtime=stat.st_mtime)


def human_bytes(value: int) -> str:
    suffixes = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{size:.1f} TB"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete old media artifacts to free disk space.")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Relative media paths will be resolved against it.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=list(DEFAULT_MEDIA_DIRS),
        help="Target directories (relative to base-dir unless absolute).",
    )
    parser.add_argument(
        "--retain-hours",
        type=float,
        default=48.0,
        help="Retain files newer than this many hours (default: 48).",
    )
    parser.add_argument(
        "--max-size-gb",
        type=float,
        default=None,
        help="Maximum total size of each directory. Oldest files beyond the limit will be removed.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not delete anything, just report actions.")
    parser.add_argument("--remove-empty-dirs", action="store_true", help="Prune empty directories after cleanup.")
    parser.add_argument("--verbose", action="store_true", help="Print every deletion.")
    return parser.parse_args(argv)


def resolve_targets(base_dir: Path, raw_paths: list[str]) -> list[Path]:
    targets: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = base_dir / path
        path = path.resolve()
        if path.exists():
            targets.append(path)
    return targets


def delete_path(path: Path, dry_run: bool, verbose: bool) -> None:
    if verbose:
        print(f"Removing {path}")
    if dry_run:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except IsADirectoryError:
        for child in path.rglob("*"):
            if child.is_file():
                delete_path(child, dry_run, verbose)
        try:
            path.rmdir()
        except OSError:
            pass


def cleanup_directory(
    directory: Path,
    retain_before: float,
    max_size_bytes: int | None,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int]:
    files = list(iter_files(directory))
    if not files:
        return (0, 0)

    removed_files = 0
    reclaimed_space = 0

    # Age-based cleanup
    for info in files:
        if info.mtime >= retain_before:
            continue
        delete_path(info.path, dry_run, verbose)
        removed_files += 1
        reclaimed_space += info.size

    if max_size_bytes is not None:
        remaining = [f for f in iter_files(directory)]
        total_size = sum(f.size for f in remaining)
        if total_size > max_size_bytes:
            remaining.sort(key=lambda f: f.mtime)  # oldest first
            for info in remaining:
                if total_size <= max_size_bytes:
                    break
                delete_path(info.path, dry_run, verbose)
                removed_files += 1
                reclaimed_space += info.size
                total_size -= info.size

    return removed_files, reclaimed_space


def prune_empty_dirs(directory: Path, dry_run: bool) -> int:
    removed = 0
    for path in sorted(directory.rglob("*"), key=lambda p: len(p.as_posix().split("/")), reverse=True):
        if not path.is_dir():
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            removed += 1
            if dry_run:
                continue
            try:
                path.rmdir()
            except OSError:
                continue
        except OSError:
            continue
    return removed


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    retain_seconds = max(args.retain_hours, 0) * 3600
    retain_before = (dt.datetime.now(tz=dt.timezone.utc).timestamp()) - retain_seconds
    max_size_bytes = None if args.max_size_gb is None else int(args.max_size_gb * (1024**3))

    targets = resolve_targets(args.base_dir, args.paths)
    if not targets:
        print("No target directories found for cleanup.", file=sys.stderr)
        return 1

    print("Cleanup configuration:")
    print(f"  Base dir:        {args.base_dir}")
    print(f"  Targets:         {', '.join(str(t) for t in targets)}")
    print(f"  Retain newer than {args.retain_hours} hours")
    if max_size_bytes is not None:
        print(f"  Max size:        {human_bytes(max_size_bytes)}")
    print(f"  Dry run:         {args.dry_run}")

    total_removed = 0
    total_space = 0

    for directory in targets:
        removed_files, reclaimed_space = cleanup_directory(
            directory, retain_before, max_size_bytes, args.dry_run, args.verbose
        )
        total_removed += removed_files
        total_space += reclaimed_space
        print(
            f"{'[DRY-RUN] ' if args.dry_run else ''}"
            f"{directory}: removed {removed_files} files, reclaimed {human_bytes(reclaimed_space)}"
        )
        if args.remove_empty_dirs:
            removed_dirs = prune_empty_dirs(directory, args.dry_run)
            if removed_dirs:
                print(f"  Removed {removed_dirs} empty directories")

    print(f"Total removed files: {total_removed}")
    print(f"Total reclaimed space: {human_bytes(total_space)}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    sys.exit(main())
