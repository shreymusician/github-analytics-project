"""Run the second-model audit over the Gate A narrations. Run: PYTHONPATH=. python scripts/audit_gate_a.py

Reads reports/gate_a/NN_*.json, writes reports/gate_a/audit.json, prints a table. Uses your own API keys.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
from repolens import architecture, audit, evidence
from repolens.llm.router import LLMRouter, keys_from_env

REPORTS = Path(os.environ.get("GATE_A_DIR", "reports/gate_a"))   # GATE_A_DIR: audit another run


def main() -> int:
    router = LLMRouter(keys=keys_from_env(), timeout=120)
    results, tot = {}, {}
    print(f"{'repo':38} {'claims':>6} {'ok':>3} {'part':>4} {'unsup':>5} {'contra':>6} {'judge':>7} {'indep':>5}")
    for f in sorted(REPORTS.glob("[0-9]*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        repo = d["profile"]["repo"]
        if not d.get("narrative"):
            print(f"{repo:38} no narration to audit")
            continue
        out = audit.audit(evidence.build_packet(d["profile"]), d["narrative"], router)
        results[repo] = out
        if d.get("architecture"):                                   # also audit the "how it works" stage
            a = d["architecture"]
            arch_out = audit.audit(architecture.build_packet(d["profile"]),
                                   {"narrative": a["architecture"], "provider": a["provider"]}, router)
            results[repo + " [how it works]"] = arch_out
            if arch_out:
                c = arch_out["counts"]
                print(f"{repo + ' [arch]':38} {arch_out['claims']:>6} {c.get('supported', 0):>3} {c.get('partly', 0):>4} "
                      f"{c.get('unsupported', 0):>5} {c.get('contradicted', 0):>6} {str(arch_out['judge']):>7} {str(arch_out['independent']):>5}")
                for k, v in c.items():
                    tot[k] = tot.get(k, 0) + v
            else:
                print(f"{repo + ' [arch]':38} AUDIT FAILED")
        if out is None:
            print(f"{repo:38} AUDIT FAILED (no judge answered)")
            continue
        c = out["counts"]
        for k, v in c.items():
            tot[k] = tot.get(k, 0) + v
        print(f"{repo:38} {out['claims']:>6} {c.get('supported', 0):>3} {c.get('partly', 0):>4} {c.get('unsupported', 0):>5} "
              f"{c.get('contradicted', 0):>6} {str(out['judge']):>7} {str(out['independent']):>5}")
    print("\nTOTAL", tot)
    (REPORTS / "audit.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for repo, out in results.items():
        for p in (out or {}).get("problems", []):
            print(f"\n[{repo}] {p['verdict'].upper()} {p['id']}: {p['claim'][:140]}\n    judge: {p['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
