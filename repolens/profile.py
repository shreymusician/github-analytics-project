"""Assemble the Repo Profile: custom analyzers first, optional LLM narration on top."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import evidence, graph, history, narrate as narrate_mod, signals, stack
from .fetch import git, github_parts, open_repo, repo_id
from .files import read_text
from .redact import redact
from .storage import Store

# Bump when analyzer output or the narration prompt changes: cached artifacts from older versions are ignored.
ANALYZER_VERSION = 7
K_ANALYSIS, K_NARRATIVE = f"analysis.v{ANALYZER_VERSION}", f"narrative.v{ANALYZER_VERSION}"

README_CHARS, EXCERPT_CHARS, EXCERPT_LINES, EXCERPTS = 1500, 1200, 60, 3


def _samples(root: Path, st: dict, arch: dict) -> dict:
    readme = next((p for p in st["_paths"] if re.fullmatch(r"readme(\.\w+)?", p.lower())), None)
    out = {"readme_head": redact(read_text(root / readme)[:README_CHARS]) if readme else "", "excerpts": []}
    for r in arch.get("read_first", [])[:EXCERPTS]:
        text = "\n".join(read_text(root / r["file"]).splitlines()[:EXCERPT_LINES])[:EXCERPT_CHARS]
        if text:
            out["excerpts"].append({"file": r["file"], "text": redact(text)})
    return out


def _timed(sink: dict | None, key: str, fn, *args, **kw):
    """Run fn and, if a dict was given, record how many seconds it took under `key`."""
    t = time.perf_counter()
    out = fn(*args, **kw)
    if sink is not None:
        sink[key] = round(time.perf_counter() - t, 2)
    return out


def analyze_root(root: Path, source: str, sha: str | None, now: float | None = None,
                 timings: dict | None = None) -> dict:
    st = _timed(timings, "stack", stack.detect_stack, root)
    arch = _timed(timings, "graph", graph.analyze_architecture, root)
    hist = _timed(timings, "history", history.analyze_history, root, now=now)
    sig = _timed(timings, "signals", signals.assess, root, st, arch, hist)
    from_imports = [t for t in stack.tags_for_imports(arch.get("third_party_imports", [])) if t not in st["capability_tags"]]
    st["capability_tags"] = st["capability_tags"] + from_imports
    st["tags_from_imports"] = from_imports
    samples = _timed(timings, "samples", _samples, root, st, arch)
    st.pop("_paths")
    return {"repo": source, "sha": sha, "stack": st, "architecture": arch, "history": hist,
            "samples": samples, **sig}


def analyze(source: str, now: float | None = None) -> dict:
    """Analyzers only (no cache, no LLM)."""
    root = open_repo(source)
    return analyze_root(root, source, _head_sha(root), now)


def _head_sha(root: Path) -> str | None:
    try:
        return git(["rev-parse", "HEAD"], cwd=root).strip()
    except Exception:
        return None


def run(source: str, store: Store | None = None, router=None, now: float | None = None, external=None) -> dict:
    """Full pipeline. Returns {'profile', 'narrative', 'cache'}.

    Cached by (repo, commit SHA): an unchanged repo costs no analysis and no tokens.
    `narrative` is None when no router/keys are available or every provider failed.
    """
    t0 = time.perf_counter()
    timings: dict = {}
    rid = repo_id(source)
    root = _timed(timings, "fetch", open_repo, source)       # clone on first sight, fetch afterwards
    sha = _head_sha(root)
    cache = {"analysis": "n/a", "narrative": "n/a"}

    profile = store.get(rid, sha, K_ANALYSIS) if (store and sha) else None
    if profile:
        cache["analysis"] = "hit"
    else:
        detail: dict = {}
        profile = _timed(timings, "analysis", analyze_root, root, source, sha, now, timings=detail)
        timings["analysis_detail"] = detail          # per analyzer: stack, graph, history, signals, samples
        parts = github_parts(source)
        if external is not None and parts:
            # snapshot as of analysis time; cached with the SHA
            profile["external"] = _timed(timings, "external", external.gather, *parts)
        cache["analysis"] = "miss"
        if store and sha:
            store.put(rid, sha, K_ANALYSIS, profile)

    narrative = None
    if router is not None:
        cached = store.get(rid, sha, K_NARRATIVE) if (store and sha) else None
        if cached:
            narrative, cache["narrative"] = cached, "hit"
        else:
            cache["narrative"] = "miss"
            narrative = _timed(timings, "narration", narrate_mod.narrate, evidence.build_packet(profile), router)
            if narrative and narrative["narrative"].get("summary") and store and sha:
                # a narration with no surviving summary is a degraded result (e.g. everything was dropped by
                # grounding): do not cache it, so the next run gets another chance instead of reusing the failure
                store.put(rid, sha, K_NARRATIVE, narrative)
    timings["total"] = round(time.perf_counter() - t0, 2)
    return {"profile": profile, "narrative": narrative, "cache": cache, "timings": timings}
