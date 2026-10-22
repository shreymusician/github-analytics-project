"""python -m repolens.find "<goal in plain words>" [--language python] [--top 6] [--no-llm]

Finds repositories worth studying for a goal (Stage A: no cloning). Uses your GitHub token for search and, unless
--no-llm, one small model call to turn the goal into search queries. Prints a Markdown guide.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from .discover import SearchLimited, gather, queries_for_goal, rank, render_guide
from .external import External
from .llm.router import LLMRouter, keys_from_env


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="repolens.find", description="Find repositories worth studying for a goal.")
    ap.add_argument("goal", help='for example "build a RAG chatbot"')
    ap.add_argument("--language", help="only repositories whose main language is this (for example python)")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--no-llm", action="store_true", help="build queries from the goal's own words, no model call")
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
    guide = render_guide(a.goal, rank(candidates, a.goal, ext=ext, top=max(1, a.top), router=router), how, queries, a.language, requested_top=a.top)
    if a.md:
        open(a.md, "w", encoding="utf-8").write(guide)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(guide)
    return 0


def load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(".env")


if __name__ == "__main__":
    raise SystemExit(main())
