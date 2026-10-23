"""Run the answerability test over the Gate A repos. Run: PYTHONPATH=. python scripts/answerability.py

For each repo three documents are shown, one at a time, to a model that must answer checkable questions using only
that document: the repo's README, GitHub Intel's report, and both. Answers are graded by code against GitHub's data.
Uses your own API keys. Writes <GATE_A_DIR>/answerability.json.
"""
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
from repolens import answerability as an
from repolens.external import External
from repolens.llm.router import LLMRouter, keys_from_env
from repolens.report import render

REPORTS = Path(os.environ.get("GATE_A_DIR", "reports/gate_a"))
CLONES = Path(".cache/repos")
README_CHARS = 8000
ARMS = ("readme", "report", "both")


def readme_text(owner: str, name: str) -> str:
    d = CLONES / f"{owner}__{name}"
    for p in sorted(d.glob("*")) if d.is_dir() else []:
        if p.is_file() and p.stem.lower() == "readme":
            return p.read_text(encoding="utf-8", errors="replace")[:README_CHARS]
    return ""


def main() -> int:
    ext = External(github_token=os.environ.get("GITHUB_TOKEN"))
    router = LLMRouter(keys=keys_from_env(), timeout=120)
    results, graded = {}, {a: [] for a in ARMS}
    print(f"{'repo':36} " + "  ".join(f"{a:>12}" for a in ARMS) + "    (correct/wrong/unknown)")
    for f in sorted(REPORTS.glob("[0-9]*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        owner, name = data["profile"]["repo"].split("/")
        meta = ext.repo_meta(owner, name) or {}
        deps = ext.manifest_dependencies(owner, name)
        truth = an.truth_for({"paths": ext.tree_paths(owner, name), "last_commit": ext.last_commit_date(owner, name),
                              "language": meta.get("language"), "license": meta.get("license"),
                              "archived": meta.get("archived"), "deps": deps})
        readme, report = readme_text(owner, name), render(data)
        docs = {"readme": readme, "report": report, "both": f"README:\n{readme}\n\n---\n\nREPORT:\n{report}"}
        row, results[data["profile"]["repo"]] = [], {}
        for arm in ARMS:
            answers = an.read_document(docs[arm], router)
            g = an.grade_all(answers, truth)
            graded[arm].append(g)
            results[data["profile"]["repo"]][arm] = {"answers": answers, "graded": g}
            c = list(g.values())
            row.append(f"{c.count('correct')}/{c.count('wrong')}/{c.count('unknown')}" + ("" if answers else "!"))
        print(f"{data['profile']['repo']:36} " + "  ".join(f"{r:>12}" for r in row))

    summ = {a: an.summarize(graded[a]) for a in ARMS}
    print("\nPER ARM (accuracy = correct of answerable; wrong = confidently wrong; unknown = document did not say)")
    for a in ARMS:
        s = summ[a]
        print(f"  {a:7} accuracy {s['accuracy']}  wrong {s['wrong_rate']}  unknown {s['unknown_rate']}  ({s['correct']}c {s['wrong']}w {s['unknown']}u of {s['answerable']})")
    print("\nPER QUESTION (correct/wrong/unknown)")
    for q in an.QIDS:
        print(f"  {q:9} " + "   ".join(f"{a}: {summ[a]['per_question'][q].get('correct', 0)}/{summ[a]['per_question'][q].get('wrong', 0)}/{summ[a]['per_question'][q].get('unknown', 0)}" for a in ARMS))
    print("\nCONFIDENTLY WRONG ANSWERS")
    for repo, arms in results.items():
        for a in ("report", "readme"):
            for q, v in arms[a]["graded"].items():
                if v == "wrong":
                    print(f"  [{a}] {repo} {q}: answered {arms[a]['answers'].get(q)!r}")
    (REPORTS / "answerability.json").write_text(json.dumps({"summary": summ, "results": results}, indent=2, default=list), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
