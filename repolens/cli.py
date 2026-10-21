from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .external import External
from .fetch import FetchError
from .llm.router import LLMRouter, keys_from_env
from .profile import run
from .report import render
from .storage import DEFAULT_DB, Store


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="repolens", description="Analyze a repo and explain what the README doesn't.")
    ap.add_argument("source", help="GitHub URL, owner/name, or local git directory")
    ap.add_argument("--md", help="write Markdown report to this file (default: print to stdout)")
    ap.add_argument("--json", help="write full JSON result to this file")
    ap.add_argument("--no-llm", action="store_true", help="deterministic analysis only")
    ap.add_argument("--offline", action="store_true", help="skip GitHub/Scorecard lookups")
    ap.add_argument("--no-cache", action="store_true", help="do not read or write the cache")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    a = ap.parse_args(argv)

    router = None
    if not a.no_llm:
        keys = keys_from_env()
        if keys:
            router = LLMRouter(keys=keys)
            print(f"LLM providers: {', '.join(router.order)}", file=sys.stderr)
        else:
            print("No API keys found (see .env.example): running without AI narration.", file=sys.stderr)

    store = None if a.no_cache else Store(a.db)
    try:
        ext = None if a.offline else External(github_token=os.environ.get("GITHUB_TOKEN"))
        result = run(a.source, store=store, router=router, external=ext)
    except FetchError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()

    print(f"cache: {result['cache']}", file=sys.stderr)
    if router is not None and result["narrative"] is None:
        print("warning: AI narration failed on every provider; showing deterministic report.", file=sys.stderr)
    if a.json:
        Path(a.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
    md = render(result)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(md)
    return 0
