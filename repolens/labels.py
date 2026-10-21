"""Human review labels for analyzed repos, stored as a CSV beside the machine's own scores.

These labels are the project's calibration data (ROADMAP V2): the machine columns say what the tool
claimed, the human columns say what a reviewer thought. `merge()` refreshes the machine columns for
every repo but never touches a human column that already has a value.
"""
from __future__ import annotations

import csv
from pathlib import Path

MACHINE = ["repo", "analyzer_version", "machine_completeness", "machine_deployability", "analysis_depth",
           "narration_provider", "statements_dropped"]
HUMAN = ["insight_0_2", "false_statements", "completeness_verdict", "deployability_verdict",
         "read_first_quality", "trust", "notes"]
COLUMNS = MACHINE + HUMAN

# Allowed human values, documented in docs/GATE_A.md; validated by problems() for non-empty cells.
ALLOWED = {
    "insight_0_2": {"0", "1", "2"},
    "completeness_verdict": {"too_low", "about_right", "too_high"},
    "deployability_verdict": {"too_low", "about_right", "too_high"},
    "read_first_quality": {"useless", "ok", "good"},
    "trust": {"yes", "maybe", "no"},
}


def machine_row(summary_row: dict, profile: dict | None, analyzer_version: int) -> dict:
    """Machine columns for one repo from a gate_a summary row (and its profile, for analysis depth)."""
    return {
        "repo": summary_row["repo"],
        "analyzer_version": analyzer_version,
        "machine_completeness": summary_row.get("completeness", ""),
        "machine_deployability": summary_row.get("deployability", ""),
        "analysis_depth": (profile or {}).get("analysis_depth", ""),
        "narration_provider": summary_row.get("provider") or "",
        "statements_dropped": "" if summary_row.get("dropped") is None else summary_row["dropped"],
    }


def load(path: Path) -> dict[str, dict]:
    if not Path(path).exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["repo"]: r for r in csv.DictReader(f) if r.get("repo")}


def merge(path: Path, machine_rows: list[dict]) -> list[dict]:
    """Write the CSV: machine columns from `machine_rows`, human columns kept from the existing file.

    Repos already in the file but absent from `machine_rows` are kept untouched (a reviewer's work is
    never deleted because a run skipped a repo). Returns the rows written, in file order.
    """
    existing = load(path)
    rows: dict[str, dict] = {k: dict(v) for k, v in existing.items()}
    for m in machine_rows:
        row = rows.setdefault(m["repo"], {c: "" for c in COLUMNS})
        row.update({k: m[k] for k in MACHINE})
        for h in HUMAN:
            row.setdefault(h, "")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows.values():
            w.writerow({c: r.get(c, "") for c in COLUMNS})
    return list(rows.values())


def problems(path: Path) -> list[str]:
    """Human cells that hold a value outside the allowed set (empty cells are fine: not reviewed yet)."""
    out = []
    for repo, r in load(path).items():
        for col, allowed in ALLOWED.items():
            v = (r.get(col) or "").strip()
            if v and v not in allowed:
                out.append(f"{repo}: {col}={v!r} not in {sorted(allowed)}")
        fs = (r.get("false_statements") or "").strip()
        if fs and not fs.isdigit():
            out.append(f"{repo}: false_statements={fs!r} must be a whole number")
    return out
