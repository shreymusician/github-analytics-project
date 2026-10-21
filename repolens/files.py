"""Shared, bounded file walking so every analyzer sees the same file set."""
from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist", "build",
             "site-packages", ".tox", ".mypy_cache", ".pytest_cache", "vendor", ".idea",
             ".next", "target", ".cache"}
MAX_FILE_BYTES = 1_000_000


def iter_files(root: Path):
    """Yield (relative posix path, absolute Path, size) for files worth analyzing."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            try:
                if p.is_symlink():
                    continue
                size = p.stat().st_size
            except OSError:
                continue
            yield p.relative_to(root).as_posix(), p, size


def read_text(p: Path, limit: int = MAX_FILE_BYTES) -> str:
    try:
        if p.stat().st_size > limit:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
