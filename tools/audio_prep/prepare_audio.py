#!/usr/bin/env python3
"""Wrapper for legacy prepare_audio module."""

import sys
from pathlib import Path

# Add project root to sys.path so we can import transkribator_modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from transkribator_modules.audio.prepare import prepare_audio, _download_with_ytdlp, _download_http, extract_audio, split_audio_into_chunks, _cli

if __name__ == "__main__":
    _cli()
