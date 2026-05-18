from pathlib import Path
from typing import Optional


def download_file(file_ref: str, dest_dir: Optional[str] = None) -> str:
    """Minimal downloader stub.

    For now just return a synthetic local path for the given file_ref.
    If dest_dir exists and contains a file with that name, return its path.
    """
    if dest_dir:
        p = Path(dest_dir) / file_ref
        if p.exists():
            return str(p)
    # synthetic path (not touching disk)
    return f"/tmp/{file_ref}"
