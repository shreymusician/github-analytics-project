"""Run the full pipeline over the Gate A repo list. One repo at a time; failures are recorded, never fatal."""
import json, os, sys, time, traceback
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(".env")
from repolens.external import External
from repolens.llm.router import LLMRouter, keys_from_env
from repolens.profile import run
from repolens.report import render
from repolens.storage import Store

REPOS = ["feyninc/chonkie", "lightly-ai/lightly", "roboflow/sports", "nianticlabs/monodepth2", "jaymody/picoGPT",
         "snipsco/snips-nlu", "idealo/image-super-resolution", "andri27-ts/Reinforcement-Learning",
         "raiyanyahya/how-to-train-your-gpt", "mishushakov/llm-scraper"]
out = Path("reports/gate_a"); out.mkdir(parents=True, exist_ok=True)
router = LLMRouter(keys=keys_from_env(), timeout=120)
ext = External(github_token=os.environ.get("GITHUB_TOKEN"))
store = Store(".cache/repolens.db")
summary = []
for i, repo in enumerate(REPOS, 1):
    t = time.time(); name = repo.replace("/", "__")
    try:
        res = run(repo, store=store, router=router, external=ext)
        (out / f"{i:02d}_{name}.md").write_text(render(res), encoding="utf-8")
        (out / f"{i:02d}_{name}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        p, n = res["profile"], res["narrative"]
        row = {"n": i, "repo": repo, "ok": True, "secs": round(time.time() - t), "cache": res["cache"],
               "completeness": p["completeness"]["score"], "deployability": p["deployability"]["score"],
               "narrated": bool(n), "dropped": n["dropped"] if n else None, "provider": n["provider"] if n else None,
               "dropped_detail": n["dropped_detail"] if n else None}
    except Exception as e:
        row = {"n": i, "repo": repo, "ok": False, "secs": round(time.time() - t), "error": f"{type(e).__name__}: {str(e)[:300]}",
               "trace": traceback.format_exc()[-600:]}
    summary.append(row)
    print(json.dumps({k: v for k, v in row.items() if k != "trace"}), flush=True)
(out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print("DONE", flush=True)
