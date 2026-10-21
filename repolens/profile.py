"""Assemble the Repo Profile: custom analyzers first, optional LLM narration on top."""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import architecture as arch_mod, evidence, graph, history, narrate as narrate_mod, signals, stack
from .fetch import git, github_parts, open_repo, repo_id
from .files import read_text
from .redact import redact
from .storage import Store

# Bump when analyzer output or the narration prompt changes: cached artifacts from older versions are ignored.
ANALYZER_VERSION = 13
K_ANALYSIS, K_NARRATIVE = f"analysis.v{ANALYZER_VERSION}", f"narrative.v{ANALYZER_VERSION}"
K_ARCH = f"architecture.v{ANALYZER_VERSION}"

README_CHARS, EXCERPT_CHARS, EXCERPT_LINES, EXCERPTS = 1500, 1200, 60, 3


# The "how it works" stage reads more source than the main narration does.
ARCH_FILES, ARCH_EXCERPT_LINES, ARCH_EXCERPT_CHARS = 6, 80, 1800
_ENTRY_STEMS = ("index", "main", "app", "cli", "server", "core", "engine", "pipeline", "model", "models", "api", "__main__")
_GENERATED = re.compile(r"(\.min\.|\.bundle\.|\.d\.ts$|-lock\.|\.lock$)")


def _size(root: Path, rel: str) -> int:
    try:
        return (root / rel).stat().st_size
    except OSError:
        return 0


def _is_source(rel: str) -> bool:
    low = rel.lower()
    return Path(rel).suffix.lower() in stack.CODE_EXTS and not _GENERATED.search(low) and "test" not in low


def pick_arch_files(root: Path, st: dict, arch: dict, hist: dict | None = None, n: int = ARCH_FILES) -> list[str]:
    """Which source files the 'how it works' stage reads. Mixing signals matters: files everyone imports are
    often glue (package __init__, CLI helpers) and miss the core idea (chonkie's chunkers).

    1. up to 3 of the import graph's read-first picks (Python);
    2. up to 2 of the most-changed source files in the git history (where the work happens);
    3. the biggest source file of each of the heaviest directories not yet represented (covers the main modules);
    4. entry-like names (index, main, app, cli...), shallow and big first, to fill any remaining slots
       (this is also what makes non-Python repos work, since the graph cannot see them).
    """
    chosen: list[str] = []

    def take(rel: str) -> None:
        if rel not in chosen and (root / rel).is_file():
            chosen.append(rel)

    graph_picks = [r["file"] for r in arch.get("read_first", []) if Path(r["file"]).stem.lower() not in graph.GENERIC_STEMS]
    for rel in graph_picks[:3]:
        take(rel)
    hot = [h["file"] for h in (hist or {}).get("hotspots", []) if _is_source(h["file"])]
    for rel in hot[:2]:
        take(rel)

    sources = [p for p in st.get("path_index", []) if _is_source(p)] or [p for p in st.get("notable_files", []) if _is_source(p)]
    by_dir: dict[str, list[tuple[int, str]]] = {}
    for p in sources:
        by_dir.setdefault(p.rpartition("/")[0], []).append((_size(root, p), p))
    covered = {c.rpartition("/")[0] for c in chosen}
    for d, files in sorted(by_dir.items(), key=lambda kv: -sum(s for s, _ in kv[1])):
        if len(chosen) >= n:
            break
        if d not in covered:
            # inside a directory: an entry-like file if there is one, otherwise the biggest
            take(min(files, key=lambda sf: (0 if Path(sf[1]).stem.lower() in _ENTRY_STEMS else 1,
                                          1 if Path(sf[1]).stem.lower() in graph.GENERIC_STEMS else 0, -sf[0], sf[1]))[1])
            covered.add(d)

    def rank(p: str):
        return (0 if Path(p).stem.lower() in _ENTRY_STEMS else 1, 1 if Path(p).stem.lower() in graph.GENERIC_STEMS else 0,
                p.count("/"), -_size(root, p), p)
    for p in sorted((p for p in sources if p not in chosen), key=rank):
        if len(chosen) >= n:
            break
        take(p)
    return chosen[:n]


def _excerpt(root: Path, rel: str, lines: int, chars: int) -> str:
    return "\n".join(read_text(root / rel).splitlines()[:lines])[:chars]


def _samples(root: Path, st: dict, arch: dict, hist: dict | None = None) -> dict:
    readme = next((p for p in st["_paths"] if re.fullmatch(r"readme(\.\w+)?", p.lower())), None)
    out = {"readme_head": redact(read_text(root / readme)[:README_CHARS]) if readme else "", "excerpts": [],
           "arch_excerpts": []}
    for r in arch.get("read_first", [])[:EXCERPTS]:
        text = _excerpt(root, r["file"], EXCERPT_LINES, EXCERPT_CHARS)
        if text:
            out["excerpts"].append({"file": r["file"], "text": redact(text)})
    for rel in pick_arch_files(root, st, arch, hist):
        text = _excerpt(root, rel, ARCH_EXCERPT_LINES, ARCH_EXCERPT_CHARS)
        if text:
            out["arch_excerpts"].append({"file": rel, "text": redact(text)})
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
    samples = _timed(timings, "samples", _samples, root, st, arch, hist)
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


def run(source: str, store: Store | None = None, router=None, now: float | None = None, external=None,
        architecture: bool = False) -> dict:
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
    result = {"profile": profile, "narrative": narrative, "cache": cache, "timings": timings}
    if architecture and router is not None:
        # opt-in "how it works" stage; only cached when it produced at least one surviving statement
        cached = store.get(rid, sha, K_ARCH) if (store and sha) else None
        if cached:
            result["architecture"], cache["architecture"] = cached, "hit"
        else:
            cache["architecture"] = "miss"
            arch = _timed(timings, "architecture", arch_mod.narrate_architecture, profile, router)
            result["architecture"] = arch
            if arch and arch["architecture"]["how_it_works"] and store and sha:
                store.put(rid, sha, K_ARCH, arch)
    timings["total"] = round(time.perf_counter() - t0, 2)
    return result
