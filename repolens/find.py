"""python -m repolens.find "<goal in plain words>" [--language python] [--top 6] [--no-llm]
                          [--deep N | --deep-repos owner/a,owner/b] [--dry-run]

Finds repositories worth studying for a goal. Stage A uses GitHub search data only and clones nothing. With --deep N
(or --deep-repos), Stage B then clones those repositories (a partial clone, read-only: nothing from them is ever
run) and analyzes them in depth; --dry-run shows exactly what would be cloned, and how big, without downloading.
Uses your GitHub token for search and, unless --no-llm, a few small model calls. Prints a Markdown guide.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

from .discover import SearchLimited, apply_deep, deep_analyze, gather, queries_for_goal, rank, render_guide
from .external import External
from .llm.router import LLMRouter, keys_from_env
from .profile import run
from .report import render
from .storage import Store

REPORTS_DIR = Path("reports/find")


def select_targets(ranked: list[dict], deep: int, names: list[str]) -> list[dict]:
    """Which ranked repositories get the deep analysis: exactly the named ones, else the first `deep`."""
    if names:
        wanted = {n.lower() for n in names}
        return [c for c in ranked if c["full_name"].lower() in wanted]
    return ranked[:max(0, deep)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="repolens.find", description="Find repositories worth studying for a goal.")
    ap.add_argument("goal", help='for example "build a RAG chatbot"')
    ap.add_argument("--language", help="only repositories whose main language is this (for example python)")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--no-llm", action="store_true", help="build queries from the goal's own words, no model call")
    ap.add_argument("--deep", type=int, default=0, metavar="N", help="also clone and analyze the top N in depth (Stage B)")
    ap.add_argument("--deep-repos", default="", help="comma-separated owner/name list to analyze in depth instead of the top N")
    ap.add_argument("--dry-run", action="store_true", help="show what Stage B would clone (with sizes) and stop; downloads nothing")
    ap.add_argument("--reports-dir", default=str(REPORTS_DIR), help="where the full report of each deep-analyzed repo is saved")
    ap.add_argument("--md", help="write the guide to this file instead of printing it")
    a = ap.parse_args(argv)
    if not a.goal.strip():
        print("error: empty goal", file=sys.stderr)
        return 2

    load_env()
    router = None
    if not a.no_llm and (keys := keys_from_env()):
        router = LLMRouter(keys=keys)
    ext = External(github_token=os.environ.get("GITHUB_TOKEN"))
    queries, how = queries_for_goal(a.goal, router)
    if not queries:
        print("error: could not turn that goal into search words", file=sys.stderr)
        return 2
    try:
        candidates = gather(ext, queries, today=date.today(), language=a.language, pause=2.2)
    except SearchLimited as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    if not candidates and not os.environ.get("GITHUB_TOKEN"):
        print("note: no results; GitHub search is limited without GITHUB_TOKEN (see .env.example)", file=sys.stderr)
    ranked = rank(candidates, a.goal, ext=ext, top=max(1, a.top), router=router)

    names = [n.strip() for n in a.deep_repos.split(",") if n.strip()]
    targets = select_targets(ranked, a.deep, names)
    if a.dry_run and (a.deep or names):
        total = sum((c.get("size_kb") or 0) for c in targets) / 1024
        print(f"Would clone {len(targets)} repositories (GitHub-reported size, upper bound; partial clones are usually smaller):")
        for c in targets:
            print(f"  {c['full_name']}: {(c.get('size_kb') or 0) / 1024:.0f} MB")
        print(f"  total up to about {total:.0f} MB. Nothing was downloaded.")
        return 0

    if targets:
        store = Store()
        out_dir = Path(a.reports_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        def save(name: str, result: dict) -> None:
            (out_dir / f"{name.replace('/', '__')}.md").write_text(render(result), encoding="utf-8")

        try:
            deep = deep_analyze(targets, lambda n: run(n, store=store, router=router, external=ext, architecture=True),
                                len(targets), save=save, progress=lambda m: print(m, file=sys.stderr))
        finally:
            store.close()
        ranked = apply_deep(ranked, deep)

    guide = render_guide(a.goal, ranked, how, queries, a.language, requested_top=a.top)
    if a.md:
        Path(a.md).write_text(guide, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(guide)
    return 0


def load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(".env")


if __name__ == "__main__":
    raise SystemExit(main())
