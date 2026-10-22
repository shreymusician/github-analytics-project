"""Check our analyzers' facts against GitHub's own data (a second, independent opinion).

The truth side is deliberately simple filename/date logic over GitHub's file list, not our analyzer code, so a
bug in an analyzer cannot also hide in the checker. It covers FACTS only (is there a Dockerfile? is it stale?)
and says nothing about whether a report is insightful: that still needs a human.
"""
from __future__ import annotations

import re
from datetime import date

from . import ci

_MANIFEST_NAMES = {"pyproject.toml", "setup.py", "setup.cfg", "pipfile", "environment.yml", "environment.yaml",
                   "package.json", "go.mod", "cargo.toml"}
_CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".ipynb")
_TEST_DIR = {"test", "tests", "__tests__", "spec", "specs"}


def _base(p: str) -> str:
    return p.rsplit("/", 1)[-1].lower()


def truth_has_dockerfile(paths):
    return any(_base(p) == "dockerfile" or _base(p).endswith(".dockerfile") for p in paths)


def truth_has_ci(paths):
    return bool(ci.detect(paths))


def truth_has_license(paths, spdx):
    return bool(spdx and spdx != "NOASSERTION") or any("/" not in p and _base(p).startswith(("license", "copying")) for p in paths)


def truth_has_manifest(paths):
    return any(_base(p) in _MANIFEST_NAMES or re.fullmatch(r"requirements[-\w]*\.txt", _base(p)) for p in paths)


def truth_has_tests(paths):
    for p in paths:
        low = p.lower()
        if not low.endswith(_CODE_EXT):
            continue
        parts = low.split("/")
        b = parts[-1]
        if (set(parts[:-1]) & _TEST_DIR or b.startswith("test_") or re.search(r"(_test\.(py|go)|\.(test|spec)\.[jt]sx?)$", b)):
            return True
    return False


def truth_activity(last_commit: str, today: date) -> str:
    days = (today - date.fromisoformat(last_commit)).days
    return "active" if days <= 90 else "stale" if days <= 365 else "abandoned"


def _ok(profile: dict, area: str, startswith: str) -> bool:
    return any(e["ok"] is True and e["note"].startswith(startswith) for e in profile[area]["evidence"])


def compare(profile: dict, truth: dict, today: date | None = None) -> list[dict]:
    """One row per fact: what we said, what GitHub says, whether they agree (None = cannot compare)."""
    today = today or date.today()
    paths = truth.get("paths")
    rows: list[dict] = []

    def row(check, ours, theirs, agree=None, note=""):
        rows.append({"check": check, "ours": ours, "truth": theirs,
                     "agree": (ours == theirs) if agree is None and ours is not None and theirs is not None else agree, "note": note})

    if paths is not None:
        row("has_dockerfile", _ok(profile, "deployability", "Dockerfile present"), truth_has_dockerfile(paths))
        row("has_ci", _ok(profile, "deployability", "CI pipeline"), truth_has_ci(paths))
        row("has_license", _ok(profile, "completeness", "license present"), truth_has_license(paths, truth.get("license")))
        row("has_dependency_manifest", bool(profile["stack"]["manifests"]), truth_has_manifest(paths))
        row("has_tests", profile["metrics"]["test_files"] > 0, truth_has_tests(paths),
            note="ours requires real test content, so 'ours=False, truth=True' can mean a demo script named test_*")
        n_ours, n_truth = profile["stack"]["file_census"]["total_files"], len(paths)
        row("file_count", n_ours, n_truth, agree=n_truth > 0 and n_ours >= 0.7 * n_truth,
            note="we skip vendor/build folders, so we may see fewer files; agree if we saw at least 70%")
    if truth.get("last_commit") and profile["history"].get("status") in {"active", "stale", "abandoned"}:
        row("activity_status", profile["history"]["status"], truth_activity(truth["last_commit"], today))
    if truth.get("language"):
        ours = profile["stack"].get("primary_language")
        norm = lambda s: (s or "").lower().replace(" notebook", "")
        row("primary_language", ours, truth["language"], agree=norm(ours) == norm(truth["language"]),
            note="GitHub counts bytes of every language file; we count code and notebook sources")
    return rows


def summarize(rows: list[dict]) -> dict:
    judged = [r for r in rows if r["agree"] is not None]
    return {"checks": len(judged), "agree": sum(1 for r in judged if r["agree"]),
            "disagreements": [r["check"] for r in judged if not r["agree"]]}
