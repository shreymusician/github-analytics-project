"""V1.1: check which configured providers actually work. Run: python -m repolens.llm.smoke

Reads keys from .env. Prints provider, model and result only: never keys.
"""
from __future__ import annotations

import time

import httpx

from .providers import PROVIDERS
from .router import AllProvidersFailed, LLMRouter, keys_from_env


def main() -> int:
    keys = keys_from_env()
    if not keys:
        print("No keys found. Copy .env.example to .env and fill in at least one key.")
        return 1
    bad = 0
    for name in PROVIDERS:
        if name not in keys:
            print(f"{name:11} skipped (no key)")
            continue
        router = LLMRouter(keys=keys, order=[name], client=httpx.Client(timeout=30))
        t = time.time()
        try:
            text, _ = router.ask([{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=200)
            print(f"{name:11} OK    model={PROVIDERS[name].model()}  {time.time() - t:.1f}s  reply={text.strip()[:30]!r}")
        except AllProvidersFailed as e:
            bad += 1
            print(f"{name:11} FAIL  model={PROVIDERS[name].model()}  {e.errors.get(name)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
