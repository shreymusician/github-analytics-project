"""Everything the web page needs, as plain functions over data (no HTTP in here, so it is easy to test).

Safety choices: the page can only analyze GitHub repositories (owner/name or a github.com URL), never a local path;
reports are read only from inside the project's `reports/` folder; secrets never leave this module (the page learns
which providers are configured, never a key); feedback is appended to a local file.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import time
from datetime import date
from pathlib import Path

from .. import architecture as arch_mod
from .. import discover, evidence
from ..external import External
from ..fetch import _GH
from ..llm.providers import PROVIDERS
from ..llm.router import LLMRouter, keys_from_env
from ..profile import ANALYZER_VERSION, run
from ..report import render
from ..storage import Store

FEEDBACK_KINDS = {"find", "report"}
EVIDENCE_CHARS = 700
SKIP_PROFILE_KEYS = {"samples"}                 # source excerpts and README text are big and not needed to render the page


class BadRequest(ValueError):
    """The request is invalid; the message is safe to show to the user."""


def parse_source(s: str) -> str:
    """'owner/name' or a github.com URL -> 'owner/name'. Local paths and anything else are refused."""
    s = (s or "").strip()
    if not s or len(s) > 200 or s.startswith((".", "/", "\\")) or ":" in s.replace("https://github.com/", "", 1) or "\\" in s:
        raise BadRequest("Enter a GitHub repository as owner/name or a github.com URL.")
    m = _GH.match(s)
    if not m or set(m.group(1)) <= {"."} or set(m.group(2)) <= {"."}:
        raise BadRequest("Enter a GitHub repository as owner/name or a github.com URL.")
    return f"{m.group(1)}/{m.group(2)}"


class Service:
    def __init__(self, base: Path | str = ".", ext: External | None = None, router=None, env_keys: dict | None = None):
        self.base = Path(base).resolve()
        self.keys = keys_from_env() if env_keys is None else env_keys
        self.ext = ext
        self.router = router if router is not None else (LLMRouter(keys=self.keys, timeout=120) if self.keys else None)

    # ------------------------------------------------------------------ status
    def status(self) -> dict:
        return {"analyzer_version": ANALYZER_VERSION, "github_token": bool(os.environ.get("GITHUB_TOKEN")),
                "providers": [{"name": n, "model": p.model(), "configured": n in self.keys} for n, p in PROVIDERS.items()],
                "can_narrate": bool(self.keys), "today": date.today().isoformat()}

    # ------------------------------------------------------------------ find
    def find(self, goal: str, language: str | None, top: int, progress) -> dict:
        goal = (goal or "").strip()
        if not goal or len(goal) > 300:
            raise BadRequest("Describe what you want to build or learn, in a sentence (up to 300 characters).")
        top = max(1, min(int(top or 6), 10))
        language = (language or "").strip().lower() or None
        if language and not re.fullmatch(r"[a-z0-9+#.\- ]{1,30}", language):
            raise BadRequest("That language name looks wrong.")
        ext = self.ext or External(github_token=os.environ.get("GITHUB_TOKEN"))
        progress("Turning your goal into search words…")
        queries, how = discover.queries_for_goal(goal, self.router)
        if not queries:
            raise BadRequest("Could not turn that goal into search words. Try describing it with more specific terms.")
        progress(f"Searching GitHub with {len(queries)} queries ({how})…")
        cands = discover.gather(ext, queries, today=date.today(), language=language, pause=2.2)
        progress(f"Found {len(cands)} candidates. Checking their dependencies and asking the model to rate them…")
        ranked = discover.rank(cands, goal, ext=ext, top=top, router=self.router)
        progress("Done.")
        return {"goal": goal, "language": language, "queries": queries, "how": how, "requested": top,
                "ranked": [self._card(c) for c in ranked],
                "order": [c["full_name"] for c in discover.learning_order(ranked)]}

    @staticmethod
    def _card(c: dict) -> dict:
        size = c.get("size_kb")
        return {"full_name": c["full_name"], "url": f"https://github.com/{c['full_name']}", "description": c.get("description"),
                "stars": c["stars"], "pushed_at": c["pushed_at"], "language": c.get("language"), "topics": c.get("topics") or [],
                "size_mb": round(size / 1024, 1) if isinstance(size, (int, float)) else None, "archived": bool(c.get("archived")),
                "collection": bool(c.get("collection")), "weak": bool(c.get("weak")), "score": c["score"], "parts": c["parts"],
                "matched_terms": c.get("matched_terms", []), "dep_hits": c.get("dep_hits") or [],
                "model_rating": c.get("llm_relevance"), "model_why": c.get("llm_why")}

    # ------------------------------------------------------------------ analyze
    def analyze(self, source: str, progress) -> dict:
        name = parse_source(source)
        ext = self.ext or External(github_token=os.environ.get("GITHUB_TOKEN"))
        progress(f"Fetching {name} (read-only partial clone; nothing from it is run)…")
        store = Store()                      # one connection per job: sqlite connections cannot be shared across threads
        try:
            progress("Analyzing the code, history, tests and CI…" + ("" if self.router else " (no model keys: facts only)"))
            result = run(name, store=store, router=self.router, external=ext, architecture=self.router is not None)
        finally:
            store.close()
        progress("Done.")
        return present(result)

    # ------------------------------------------------------------------ saved reports
    def reports(self) -> list[dict]:
        root = self.base / "reports"
        out = []
        for p in sorted(root.rglob("*")) if root.is_dir() else []:
            rel = p.relative_to(root)
            if p.suffix not in (".json", ".md") or len(rel.parts) > 2 or p.name in ("summary.json", "audit.json", "fact_check.json", "answerability.json") \
                    or p.name.startswith(("run", "discovery")):
                continue
            group = rel.parts[0] if len(rel.parts) == 2 else "(top level)"
            label = re.sub(r"^\d+_", "", p.stem).replace("__", "/")
            out.append({"path": rel.as_posix(), "group": group, "label": label, "kind": p.suffix[1:], "kb": round(p.stat().st_size / 1024)})
        return out

    def report(self, rel: str) -> dict:
        root = (self.base / "reports").resolve()
        target = (root / rel).resolve()
        if root not in target.parents or target.suffix not in (".json", ".md") or not target.is_file():
            raise BadRequest("No such report.")
        if target.suffix == ".md":
            return {"markdown": target.read_text(encoding="utf-8", errors="replace")}
        data = json.loads(target.read_text(encoding="utf-8"))
        if "profile" not in data:
            raise BadRequest("That file is not a repository report.")
        return present(data)

    # ------------------------------------------------------------------ feedback
    def add_feedback(self, payload: dict) -> dict:
        kind, rating = payload.get("kind"), payload.get("rating")
        target = str(payload.get("target") or "")[:200]
        if kind not in FEEDBACK_KINDS or rating not in ("up", "down") or not target:
            raise BadRequest("Feedback needs a kind (find or report), a target and a rating (up or down).")
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, "target": target, "rating": rating,
               "goal": str(payload.get("goal") or "")[:300], "note": str(payload.get("note") or "")[:500]}
        path = self.base / "data" / "feedback" / "feedback.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return {"saved": True, "total": sum(1 for _ in open(path, encoding="utf-8"))}

    # ------------------------------------------------------------------ the project itself
    def project(self) -> dict:
        return {"stats": self._stats(), "roadmap": self._roadmap(), "pipeline": PIPELINE, "modules": self._modules(),
                "decisions": self._decisions(), "verification": self._verification(), "commits": self._commits(40)}

    def _git(self, *args) -> str:
        try:
            r = subprocess.run(["git", *args], cwd=self.base, capture_output=True, text=True, encoding="utf-8", timeout=20)
            return r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def _stats(self) -> dict:
        mods = list((self.base / "repolens").rglob("*.py"))
        tests = list((self.base / "tests").glob("test_*.py"))
        n_tests = sum(len(re.findall(r"^\s*def test_", p.read_text(encoding="utf-8", errors="replace"), re.M)) for p in tests)
        commits = self._git("rev-list", "--count", "HEAD").strip()
        return {"commits": int(commits) if commits.isdigit() else None, "modules": len(mods),
                "code_lines": sum(len(p.read_text(encoding="utf-8", errors="replace").splitlines()) for p in mods),
                "test_functions": n_tests, "test_files": len(tests), "scripts": len(list((self.base / "scripts").glob("*.py"))),
                "docs": len(list((self.base / "docs").glob("*.md")))}

    def _commits(self, n: int) -> list[dict]:
        out = []
        for line in self._git("log", f"-n{n}", "--format=%h\x1f%ad\x1f%s", "--date=short").splitlines():
            h, d, s = (line.split("\x1f") + ["", "", ""])[:3]
            out.append({"hash": h, "date": d, "subject": s})
        return out

    def _modules(self) -> list[dict]:
        out = []
        for p in sorted((self.base / "repolens").rglob("*.py")):
            if p.name == "__init__.py" or p.name == "__main__.py":
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            try:
                doc = ast.get_docstring(ast.parse(text)) or ""
            except SyntaxError:
                doc = ""
            rel = p.relative_to(self.base).as_posix()
            out.append({"path": rel, "name": p.stem, "summary": doc.strip().splitlines()[0] if doc.strip() else "",
                        "lines": len(text.splitlines()), "layer": LAYER.get(p.stem, "web" if "/web/" in rel else "other")})
        return out

    def _decisions(self) -> list[dict]:
        path = self.base / "docs" / "DECISIONS.md"
        if not path.is_file():
            return []
        out = []
        for block in re.split(r"(?m)^## ", path.read_text(encoding="utf-8")):
            m = re.match(r"(D\d+)\.\s+([^\n]+)\n(.*)", block, re.S)      # title = first line only
            if m:
                body = re.sub(r"\s+", " ", m.group(3)).strip()
                out.append({"id": m.group(1), "title": m.group(2).strip(), "text": body[:700]})
        return out

    def _roadmap(self) -> dict:
        path = self.base / "data" / "progress.json"
        if not path.is_file():
            return {"versions": [], "limits": [], "overall": None}
        data = json.loads(path.read_text(encoding="utf-8"))
        value = {"done": 1.0, "partial": 0.5, "todo": 0.0}
        for v in data["versions"]:
            total = sum(i.get("w", 1) for i in v["items"])
            v["percent"] = round(100 * sum(value[i["s"]] * i.get("w", 1) for i in v["items"]) / max(1, total))
        def avg(ids):
            vs = [v for v in data["versions"] if v["id"] in ids]
            w = sum(v["weight"] for v in vs)
            return round(sum(v["percent"] * v["weight"] for v in vs) / w) if w else None
        data["overall"] = {"core": avg({"V0", "V1", "V2", "V3", "V4"}), "full": avg({v["id"] for v in data["versions"]})}
        return data

    def _verification(self) -> dict:
        root = self.base / "reports" / "gate_a"
        out: dict = {}

        def load(name):
            p = root / name
            try:
                return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
            except (OSError, ValueError):
                return None

        s = load("summary.json")
        if s:
            out["gate_a"] = {"repos": len(s), "narrated": sum(1 for r in s if r.get("narrated")),
                             "crashes": sum(1 for r in s if not r.get("ok")),
                             "dropped_statements": sum((r.get("dropped") or 0) for r in s)}
        a = load("audit.json")
        if a:
            counts: dict = {}
            indep = total = 0
            for v in a.values():
                if v:
                    total += 1
                    indep += bool(v.get("independent"))
                    for k, n in (v.get("counts") or {}).items():
                        counts[k] = counts.get(k, 0) + n
            out["audit"] = {"counts": counts, "audits": total, "independent": indep}
        f = load("fact_check.json")
        if f:
            tot = sum(v["summary"]["checks"] for v in f.values())
            out["fact_check"] = {"checks": tot, "agree": sum(v["summary"]["agree"] for v in f.values())}
        ans = load("answerability.json")
        if ans and "summary" in ans:
            out["answerability"] = {arm: {k: v[k] for k in ("accuracy", "wrong_rate", "unknown_rate")} for arm, v in ans["summary"].items()}
        return out


# ---------------------------------------------------------------------- presenting a pipeline result
def present(result: dict) -> dict:
    """A pipeline result trimmed for the browser: no source excerpts or file index, plus the evidence text that
    citations point at, the deep facts, and the Markdown report."""
    p = result["profile"]
    slim = {k: v for k, v in p.items() if k not in SKIP_PROFILE_KEYS}
    slim["stack"] = {k: v for k, v in p["stack"].items() if k not in ("path_index", "notable_files")}
    ev = {it["id"]: it["text"][:EVIDENCE_CHARS] for it in evidence.build_packet(p)["items"]}
    ev.update({it["id"]: it["text"][:EVIDENCE_CHARS] for it in arch_mod.build_packet(p)["items"]})
    return {"profile": slim, "narrative": result.get("narrative"), "architecture": result.get("architecture"),
            "cache": result.get("cache"), "timings": result.get("timings"), "evidence": ev,
            "facts": discover.deep_facts(result), "markdown": render(result)}


# ---------------------------------------------------------------------- static knowledge about the pipeline
LAYER = {"fetch": "analyzers", "files": "analyzers", "stack": "analyzers", "graph": "analyzers", "jsgraph": "analyzers",
         "notebooks": "analyzers", "history": "analyzers", "signals": "analyzers", "ci": "analyzers", "external": "analyzers",
         "redact": "safety", "evidence": "llm", "narrate": "llm", "architecture": "llm", "router": "llm", "providers": "llm",
         "smoke": "llm", "audit": "verification", "factcheck": "verification", "answerability": "verification",
         "labels": "verification", "discover": "discovery", "find": "discovery", "profile": "pipeline", "report": "pipeline",
         "storage": "pipeline", "cli": "pipeline"}

PIPELINE = [
    {"n": 1, "title": "Fetch", "kind": "custom", "module": "fetch", "text": "Partial git clone: full history, file contents only for the latest commit. Repo code is only ever read, never run."},
    {"n": 2, "title": "Analyze (no AI)", "kind": "custom", "module": "stack, graph, jsgraph, notebooks, history, signals, ci",
     "text": "Stack and manifests, Python and JS/TS import graphs with PageRank, notebook outlines, git-history statistics, CI/test/Docker/license rules."},
    {"n": 3, "title": "Evidence packet", "kind": "custom", "module": "evidence, redact",
     "text": "Numbered facts (E1, E2…) and source excerpts (S1, S2…). Secrets are scrubbed; repo text is fenced as untrusted data."},
    {"n": 4, "title": "LLM stages", "kind": "ai", "module": "narrate, architecture, llm/router",
     "text": "Narration and 'how it works', via Groq, Gemini or OpenRouter with automatic failover. Every statement must cite evidence; names, files and numbers must exist in it, or it is dropped."},
    {"n": 5, "title": "Report", "kind": "custom", "module": "report, profile, storage", "text": "At-a-glance box, scores with reasons, citations, cached per repo and commit."},
    {"n": 6, "title": "Verify", "kind": "verify", "module": "audit, factcheck, answerability",
     "text": "A different model audits every claim, facts are cross-checked against GitHub, and a reader test checks that key facts are findable."},
    {"n": 7, "title": "Discover", "kind": "custom", "module": "discover, find",
     "text": "Goal to search words (model-assisted) to GitHub search to cheap checks to explained ranking; optional deep analysis of finalists."},
]
