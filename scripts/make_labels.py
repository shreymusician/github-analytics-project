"""Create or refresh data/labels/gate_a.csv from the latest Gate A run.

Machine columns are refreshed from reports/gate_a/summary.json; human columns you have filled in are kept.
Run:  PYTHONPATH=. python scripts/make_labels.py        (add --check to only validate your entries)
"""
import json
import sys
from pathlib import Path

from repolens import labels
from repolens.profile import ANALYZER_VERSION

CSV = Path("data/labels/gate_a.csv")
SUMMARY = Path("reports/gate_a/summary.json")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        bad = labels.problems(CSV)
        print("\n".join(bad) if bad else "all filled-in cells are valid")
        return 1 if bad else 0
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    rows = []
    for s in summary:
        stem = s["repo"].replace("/", "__")
        pj = next(SUMMARY.parent.glob(f"*_{stem}.json"), None)
        profile = json.loads(pj.read_text(encoding="utf-8"))["profile"] if pj else None
        rows.append(labels.machine_row(s, profile, ANALYZER_VERSION))
    written = labels.merge(CSV, rows)
    reviewed = sum(1 for r in written if r.get("insight_0_2"))
    print(f"wrote {CSV}: {len(written)} repos, {reviewed} with human scores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
