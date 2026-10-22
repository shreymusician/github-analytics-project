"""Run the repo finder over many different goals and report objective red flags. Run: PYTHONPATH=. python scripts/discovery_check.py

No human needed. Per goal it checks, on the top results: curated lists near the top, results sharing none of the goal's
words, one owner flooding the list, archived repos near the top, a wrong language, and whether the model judge answered.
Uses GitHub search (needs GITHUB_TOKEN) and your LLM keys. Writes reports/discovery_check.json.

Caveat: the model's own relevance ratings are shown for information but are NOT independent (the same model family
that helped rank also rates them), so no "pass" depends on them.
"""
import json
import os
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".env")
from repolens import discover as d
from repolens.external import External
from repolens.llm.router import LLMRouter, keys_from_env

GOALS = [
    ("I want to build a RAG chatbot over my documents", "python"),
    ("train a custom object detection model with YOLO on my own images", "python"),
    ("forecast time series like sales or energy demand", "python"),
    ("learn reinforcement learning by solving CartPole and Atari games", "python"),
    ("fine-tune a small language model with LoRA", "python"),
    ("build a movie recommender system", "python"),
    ("transcribe speech to text with Whisper", None),
    ("sentiment analysis of tweets with transformers", "python"),
    ("an LLM web scraper that extracts structured data", "typescript"),
    ("classify images with a convolutional neural network from scratch", "python"),
]
TOP = 6


def check(goal: str, language: str | None, ext, router) -> dict:
    t = time.time()
    queries, how = d.queries_for_goal(goal, router)
    try:
        cands = d.gather(ext, queries, today=date.today(), language=language, pause=2.2)
    except d.SearchLimited as e:
        return {"goal": goal, "error": str(e)}
    ranked = d.rank(cands, goal, ext=ext, top=TOP, router=router)
    owners = Counter(c["full_name"].split("/")[0] for c in ranked)
    judged = [c for c in ranked if c.get("llm_why") and c["llm_why"] != "not judged by the model"]
    flags = {
        "few_results": len(ranked) < 3,
        "collections_in_top3": sum(1 for c in ranked[:3] if c.get("collection")),
        "off_topic_in_top5": sum(1 for c in ranked[:5] if not c["matched_terms"] and c.get("llm_relevance", 0) < 2),
        "owner_flood": max(owners.values(), default=0) > 2,
        "archived_in_top3": sum(1 for c in ranked[:3] if c.get("archived")),
        "wrong_language": sum(1 for c in ranked if language and (c.get("language") or "").lower() != language.lower()),
        "model_judge_missing": router is not None and not judged,
    }
    return {"goal": goal, "language": language, "how": how, "queries": queries, "candidates": len(cands), "flags": flags,
            "mean_model_rating_top3": round(sum(c.get("llm_relevance", 0) for c in ranked[:3]) / max(1, len(ranked[:3])), 2) if judged else None,
            "top": [{"repo": c["full_name"], "score": c["score"], "stars": c["stars"], "model": c.get("llm_relevance"),
                     "collection": c.get("collection"), "archived": c.get("archived"), "size_mb": round((c.get("size_kb") or 0) / 1024)} for c in ranked],
            "secs": round(time.time() - t)}


def main() -> int:
    ext = External(github_token=os.environ.get("GITHUB_TOKEN"))
    keys = keys_from_env()
    router = LLMRouter(keys=keys, timeout=120) if keys else None
    results = []
    bad = Counter()
    for goal, lang in GOALS:
        r = check(goal, lang, ext, router)
        results.append(r)
        if "error" in r:
            print(f"- {goal[:58]:58} ERROR {r['error']}")
            continue
        f = r["flags"]
        active = {k: v for k, v in f.items() if v}
        bad.update(active.keys())
        print(f"- {goal[:58]:58} {len(r['top'])} shown / {r['candidates']} found | flags: {active or 'none'} | model avg top3: {r['mean_model_rating_top3']}")
        for t in r["top"][:5]:
            print(f"      {t['repo']:46} score {t['score']:.2f} stars {t['stars']:>6} model {t['model']} {'[LIST]' if t['collection'] else ''}{'[ARCHIVED]' if t['archived'] else ''} {t['size_mb']} MB")
        time.sleep(4)
    print("\nGOALS WITH EACH FLAG:", dict(bad) or "none")
    Path("reports").mkdir(exist_ok=True)
    Path("reports/discovery_check.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
