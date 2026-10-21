"""Positive control for the audit: does the judge actually catch claims we KNOW are false?

Plants three false claims and one true claim into a real narration, runs the audit, and reports which were caught.
Run: PYTHONPATH=. python scripts/audit_selftest.py     (uses your own API keys; needs reports/gate_a from a Gate A run)
"""
import copy
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
from repolens import audit, evidence
from repolens.llm.router import LLMRouter, keys_from_env

PLANTED = [
    ("false: contradicts the evidence", "The project has over 500 active contributors."),
    ("false: not in the evidence at all", "It ships a Kubernetes Helm chart used for production deployments."),
    ("false: contradicts the evidence", "The repository has been abandoned for more than two years."),
    ("TRUE control", None),   # filled from the evidence below
]


def main() -> int:
    d = json.loads(next(Path("reports/gate_a").glob("01_*.json")).read_text(encoding="utf-8"))
    packet = evidence.build_packet(d["profile"])
    narration = copy.deepcopy(d["narrative"])
    h = d["profile"]["history"]
    true_claim = f"The history shows {h['commits']} commits and {h['contributors']} contributors."
    cite = next(i["id"] for i in packet["items"] if i["text"].startswith("History:"))
    for _, text in PLANTED:
        narration["narrative"]["caveats"].append({"text": text or true_claim, "evidence": [cite]})
    n_real = len(narration["narrative"]["caveats"]) - len(PLANTED)

    out = audit.audit(packet, narration, LLMRouter(keys=keys_from_env(), timeout=120))
    if out is None:
        print("audit failed (no judge answered)")
        return 1
    print(f"judge: {out['judge']}  independent: {out['independent']}\n")
    caught = 0
    for i, (label, text) in enumerate(PLANTED):
        v = next(x for x in out["verdicts"] if x["id"] == f"caveats.{n_real + i}")
        is_false = label.startswith("false")
        ok = (v["verdict"] in ("unsupported", "contradicted")) if is_false else (v["verdict"] == "supported")
        caught += ok
        print(f"[{'OK ' if ok else 'MISS'}] {label:36} -> {v['verdict']:12} | {v['reason']}")
    print(f"\n{caught}/{len(PLANTED)} planted claims handled correctly")
    return 0 if caught == len(PLANTED) else 2


if __name__ == "__main__":
    sys.exit(main())
