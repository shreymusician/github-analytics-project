"""Git-history intelligence: what the final snapshot (and README) never tells you."""
from __future__ import annotations

import re
import time
from collections import Counter
from itertools import combinations

from .fetch import FetchError, git

_SEP, _FLD = "\x1e", "\x1f"
_WIP = re.compile(r"\b(wip|tmp|temp|fix(es|ed)?|typo|update|minor|test|stuff|asdf|changes?)\b", re.I)
DAY = 86400
MAX_COCHANGE_FILES = 30   # huge commits (mass renames, vendoring) say nothing about coupling


def parse_log(raw: str) -> list[dict]:
    commits = []
    for chunk in raw.split(_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        head, _, files = chunk.partition("\n")
        parts = head.split(_FLD)
        if len(parts) < 4:
            continue
        try:
            ts = int(parts[2])
        except ValueError:
            continue
        commits.append({"sha": parts[0], "author": parts[1], "ts": ts, "msg": parts[3],
                        "files": [f for f in files.split("\n") if f.strip()]})
    return sorted(commits, key=lambda c: c["ts"])


def analyze_history(repo_dir, now: float | None = None, max_commits: int = 5000) -> dict:
    now = now or time.time()
    try:
        raw = git(["log", f"-n{max_commits}", "--no-merges", "--no-renames", "--name-only",
                   f"--pretty=format:{_SEP}%H{_FLD}%an{_FLD}%at{_FLD}%s"], cwd=repo_dir)
    except FetchError:
        return {"commits": 0, "status": "no-git-history"}
    commits = parse_log(raw)
    if not commits:
        return {"commits": 0, "status": "empty"}
    return summarize(commits, now)


def summarize(commits: list[dict], now: float) -> dict:
    n = len(commits)
    first, last = commits[0]["ts"], commits[-1]["ts"]
    span_days = max((last - first) / DAY, 0.0)
    authors = Counter(c["author"] for c in commits)

    # bus factor: fewest authors who together made >=50% of commits
    acc, bus = 0, 0
    for _, cnt in authors.most_common():
        acc += cnt
        bus += 1
        if acc >= n / 2:
            break

    gaps = [(b["ts"] - a["ts"]) / DAY for a, b in zip(commits, commits[1:])]
    idle_days = (now - last) / DAY
    if idle_days <= 90:
        status = "active"
    elif idle_days <= 365:
        status = "stale"
    else:
        status = "abandoned"

    # burstiness: share of all commits landing in the busiest 14-day window
    ts = [c["ts"] for c in commits]
    j, best = 0, 0
    for i in range(n):
        while ts[i] - ts[j] > 14 * DAY:
            j += 1
        best = max(best, i - j + 1)
    burst = best / n
    shape = ("one-shot-burst" if n >= 3 and (span_days < 7 or (burst > 0.8 and span_days < 60))
             else "sustained" if span_days > 180 and n >= 30 else "short-lived")

    file_changes: Counter = Counter()
    pairs: Counter = Counter()
    for c in commits:
        fs = sorted(set(c["files"]))
        file_changes.update(fs)
        if 2 <= len(fs) <= MAX_COCHANGE_FILES:
            pairs.update(combinations(fs, 2))

    wip = sum(1 for c in commits if _WIP.search(c["msg"])) / n
    return {
        "commits": n,
        "first_commit": time.strftime("%Y-%m-%d", time.gmtime(first)),
        "last_commit": time.strftime("%Y-%m-%d", time.gmtime(last)),
        "span_days": round(span_days),
        "idle_days": round(idle_days),
        "status": status,
        "shape": shape,
        "contributors": len(authors),
        "top_author_share": round(authors.most_common(1)[0][1] / n, 2),
        "bus_factor": bus,
        "longest_gap_days": round(max(gaps), 1) if gaps else 0,
        "low_effort_message_ratio": round(wip, 2),
        "hotspots": [{"file": f, "changes": k} for f, k in file_changes.most_common(5)],
        "co_changed": [{"files": list(p), "times": k} for p, k in pairs.most_common(5) if k >= 2],
        "origin_story": [c["msg"][:80] for c in commits[:5]],
    }
