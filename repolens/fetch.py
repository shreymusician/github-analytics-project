"""Get a repo onto disk without crawling or bulk indexing.

Uses a *partial clone* (`--filter=blob:none`): full commit/tree history comes
down cheaply (needed for history analysis) while file contents are fetched
only for the checked-out HEAD. Repo contents are only ever read as text; no
repo code is executed here.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

CACHE_DIR = Path(".cache/repos")
_GH = re.compile(r"^(?:https://github\.com/)?([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


class FetchError(RuntimeError):
    pass


def repo_id(source: str) -> str:
    """Stable cache identity: `owner/name` (lowercase) for GitHub sources, else the resolved path."""
    p = Path(source)
    if p.is_dir():
        return str(p.resolve())
    m = _GH.match(source.strip())
    if not m:
        raise FetchError(f"not a local directory or GitHub repo: {source!r}")
    return f"{m.group(1)}/{m.group(2)}".lower()


def github_parts(source: str) -> tuple[str, str] | None:
    """(owner, name) if `source` is a GitHub URL / owner/name (not a local directory), else None."""
    if Path(source).is_dir():
        return None
    m = _GH.match(source.strip())
    return (m.group(1), m.group(2)) if m else None


def open_repo(source: str, cache_dir: Path = CACHE_DIR) -> Path:
    """`source` is a local git directory, a GitHub URL, or `owner/name`."""
    p = Path(source)
    if p.is_dir():
        return p.resolve()
    m = _GH.match(source.strip())
    if not m:
        raise FetchError(f"not a local directory or GitHub repo: {source!r}")
    owner, name = m.groups()
    dest = cache_dir / f"{owner}__{name}"
    if (dest / ".git").is_dir():
        _git(["fetch", "--quiet", "origin"], cwd=dest)
        _git(["reset", "--quiet", "--hard", "FETCH_HEAD"], cwd=dest)
        return dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(["-c", "core.symlinks=false", "clone", "--quiet", "--filter=blob:none",
          f"https://github.com/{owner}/{name}.git", str(dest)])
    return dest.resolve()


def _git(args: list[str], cwd: Path | None = None) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except (OSError, subprocess.TimeoutExpired) as e:
        raise FetchError(f"git failed: {type(e).__name__}") from e
    if r.returncode:
        raise FetchError(f"git {args[0]} failed: {r.stderr.strip()[:300]}")
    return r.stdout


git = _git
