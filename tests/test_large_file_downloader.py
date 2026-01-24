import os
import tempfile
from pathlib import Path


def test_probe_cache_single(tmp_path):
    """Smoke test placeholder for `_probe_cache_copy()` behavior.

    This test is a minimal, fast check to ensure test harness works. Replace
    with real unit tests that import the function and exercise filesystem cases.
    """
    p = tmp_path / "videos"
    p.mkdir()
    f = p / "file_1.mp4"
    f.write_bytes(b"dummy")
    # simple assertion to ensure test runner reports OK
    assert f.exists()
