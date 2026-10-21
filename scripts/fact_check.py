"""Fact-check the Gate A profiles against GitHub's own data. Run: PYTHONPATH=. python scripts/fact_check.py

Writes reports/gate_a/fact_check.json and prints agreement per repo and per check.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
from repolens import factcheck
from repolens.external import External

REPORTS = Path("reports/gate_a")


def main() -> int:
    ext = External(github_token=os.environ.get("GITHUB_TOKEN"))
    out, per_check = {}, defaultdict(lambda: [0, 0])
    for f in sorted(REPORTS.glob("[0-9]*.json")):
        profile = json.loads(f.read_text(encoding="utf-8"))["profile"]
        owner, name = profile["repo"].split("/")
        meta = ext.repo_meta(owner, name) or {}
        truth = {"paths": ext.tree_paths(owner, name), "last_commit": ext.last_commit_date(owner, name),
                 "language": meta.get("language"), "license": meta.get("license")}
        rows = factcheck.compare(profile, truth)
        s = factcheck.summarize(rows)
        out[profile["repo"]] = {"summary": s, "rows": rows, "truth_paths_available": truth["paths"] is not None}
        for r in rows:
            if r["agree"] is not None:
                per_check[r["check"]][0] += bool(r["agree"])
                per_check[r["check"]][1] += 1
        flag = "" if truth["paths"] is not None else "  (GitHub file list unavailable: file checks skipped)"
        print(f"{profile['repo']:40} {s['agree']}/{s['checks']} agree  disagree: {s['disagreements'] or '-'}{flag}")
    print("\nper check:")
    for c, (a, n) in per_check.items():
        print(f"  {c:26} {a}/{n}")
    tot_a, tot_n = sum(a for a, _ in per_check.values()), sum(n for _, n in per_check.values())
    print(f"\nOVERALL {tot_a}/{tot_n} facts agree with GitHub")
    (REPORTS / "fact_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
