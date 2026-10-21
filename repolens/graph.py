"""Architecture discovery from the Python import graph, with no ML model.

* PageRank (own implementation) finds the *core* modules: the ones many
  important modules depend on. This answers "which files should I read first?".
* Label propagation finds *communities*: clusters of tightly coupled modules,
  i.e. the real subsystems regardless of how the folders are named.
"""
from __future__ import annotations

import ast
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .files import iter_files, read_text
from .jsgraph import JS_EXTS, build_js_graph
from .notebooks import scan_repo as scan_notebooks
from .signals import _is_test as is_test_path

SRC_ROOTS = ("src", "lib", "app")  # common layouts where the package root is one level down


def module_name(rel: str) -> str:
    parts = rel[:-3].split("/")
    if len(parts) > 1 and parts[0] in SRC_ROOTS and not (parts[0] == "app" and len(parts) == 2):
        parts = parts[1:]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


IMPORT_ALIASES = {"PIL": "Pillow", "cv2": "OpenCV", "sklearn": "scikit-learn", "yaml": "PyYAML",
                  "bs4": "BeautifulSoup", "skimage": "scikit-image", "dateutil": "python-dateutil",
                  "dotenv": "python-dotenv", "jwt": "PyJWT", "serial": "pyserial"}
_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def build_graph(root: Path, external: Counter | None = None) -> tuple[dict[str, set[str]], dict[str, str], set[str]]:
    """Return (edges importer->{imported}, module->relpath, entry-point modules).

    If `external` is given, it is filled with {top-level third-party module: number of files importing it}.
    """
    sources = {}
    for rel, path, _ in iter_files(root):
        if rel.endswith(".py"):
            sources[module_name(rel)] = (rel, path)
    mods = set(sources)
    local_tops = {m.split(".")[0] for m in mods} | {Path(r).parts[0] for r, _ in sources.values() if "/" in r}
    edges: dict[str, set[str]] = {m: set() for m in mods}
    entries: set[str] = set()

    for mod, (rel, path) in sources.items():
        try:
            tree = ast.parse(read_text(path))
        except (SyntaxError, ValueError, RecursionError):
            continue
        is_pkg = rel.endswith("__init__.py")
        pkg = mod if is_pkg else mod.rpartition(".")[0]
        seen_ext: set[str] = set()
        for node in ast.walk(tree):
            if external is not None:
                tops = ([a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import)
                        else [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module and not node.level
                        else [])
                seen_ext.update(x for x in tops if x not in _STDLIB and x not in local_tops)
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    up = pkg.split(".") if pkg else []
                    up = up[: len(up) - (node.level - 1)] if node.level > 1 else up
                    base = ".".join(filter(None, [".".join(up), base]))
                targets = [base] + [f"{base}.{a.name}" for a in node.names if a.name != "*"]
            elif isinstance(node, ast.If) and _is_main_guard(node):
                entries.add(mod)
            for t in targets:
                hit = _resolve(t, mods)
                if hit and hit != mod:
                    edges[mod].add(hit)
        if external is not None:
            external.update(seen_ext)
        if not rel.endswith("__init__.py") and mod.rsplit(".", 1)[-1] in {"main", "app", "cli", "__main__", "manage", "server", "run"}:
            entries.add(mod)
    # A script under docs/, debug/, examples/... runs when invoked but is not how the project is used.
    entries = {m for m in entries if not _NON_ENTRY_DIRS.search(sources[m][0])}
    return edges, {m: v[0] for m, v in sources.items()}, entries


def _is_main_guard(node: ast.If) -> bool:
    t = node.test
    return (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__")


def _resolve(name: str, mods: set[str]) -> str | None:
    while name:
        if name in mods:
            return name
        name = name.rpartition(".")[0]
    return None


def pagerank(edges: dict[str, set[str]], damping: float = 0.85, iters: int = 60, tol: float = 1e-9) -> dict[str, float]:
    """Importance flows from importer to imported, so heavily-depended-on modules score high."""
    nodes = sorted(edges)
    n = len(nodes)
    if not n:
        return {}
    rank = {v: 1.0 / n for v in nodes}
    for _ in range(iters):
        dangling = sum(rank[v] for v in nodes if not edges[v])
        new = {v: (1 - damping) / n + damping * dangling / n for v in nodes}
        for v in nodes:
            if edges[v]:
                share = damping * rank[v] / len(edges[v])
                for w in edges[v]:
                    new[w] += share
        delta = sum(abs(new[v] - rank[v]) for v in nodes)
        rank = new
        if delta < tol:
            break
    return rank


def communities(edges: dict[str, set[str]], iters: int = 30) -> list[list[str]]:
    """Deterministic label propagation on the undirected import graph."""
    adj: dict[str, set[str]] = defaultdict(set)
    for a, outs in edges.items():
        adj[a]  # ensure isolated nodes exist
        for b in outs:
            adj[a].add(b)
            adj[b].add(a)
    label = {v: v for v in adj}
    for _ in range(iters):
        changed = False
        for v in sorted(adj):
            if not adj[v]:
                continue
            counts = Counter(label[w] for w in adj[v])
            best = max(counts.values())
            new = min(l for l, c in counts.items() if c == best)
            if new != label[v] and counts.get(label[v], 0) < best:
                label[v], changed = new, True
        if not changed:
            break
    groups: dict[str, list[str]] = defaultdict(list)
    for v, l in label.items():
        groups[l].append(v)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))


def _is_js(m: str) -> bool:
    """JS/TS module ids are repo-relative file paths; Python ids are dotted module names."""
    return m.lower().endswith(JS_EXTS)


def _stem(m: str) -> str:
    return Path(m).stem if _is_js(m) else m.rsplit(".", 1)[-1]


def _name_cluster(members: list[str]) -> str:
    key = lambda m: (m.rpartition("/")[0] or "(root)") if _is_js(m) else (m.split(".")[0] if "." in m else m)
    return Counter(key(m) for m in members).most_common(1)[0][0]


TRIVIAL_NAMES = {"__about__", "__version__", "_version", "version", "constants", "exceptions", "logger"}
# Catch-all modules: real code, but rarely the place to learn what a project does. Ranked lower, not excluded.
GENERIC_STEMS = {"utils", "util", "helpers", "helper", "common", "misc"}
GENERIC_PENALTY = 0.5
_NON_ENTRY_DIRS = re.compile(r"(^|/)(docs?|debug|examples?|samples?|benchmarks?|bench|tests?|tutorials?)/", re.I)
MIN_SUBSTANCE = 12


def substance(root: Path, rel: str) -> int:
    """Lines that do something: not blank, comment, import, docstring fence or `__all__`."""
    n = 0
    for line in read_text(root / rel).splitlines():
        s = line.strip()
        if s and not s.startswith(("#", "//", "/*", "*", "import ", "from ", "__all__", '"""', "'''", ")", "]", "}")):
            n += 1
    return n


def rank_read_first(root: Path, edges, paths, entries, pr, imported_by) -> list[str]:
    """Where to start reading: entry points, 'hubs' that wire many modules together, and substantial
    'foundations' that many modules depend on. Bare re-export `__init__.py` files and trivial
    constants/version/logger modules are skipped (everything imports them; they teach nothing)."""
    subst = {m: substance(root, paths[m]) for m in edges}
    pool = [m for m in edges if not is_test_path(paths[m])] or list(edges)   # tests import everything: they never lead
    cand = [m for m in pool if (imported_by[m] or edges[m] or m in entries)
            and subst[m] >= MIN_SUBSTANCE and _stem(m) not in TRIVIAL_NAMES]
    if len(cand) < 5:                      # tiny repo: do not filter, there is little to choose from
        cand = [m for m in pool if imported_by[m] or m in entries]
    if not cand:
        return []
    max_pr = max(pr[m] for m in cand) or 1
    max_out = max(len(edges[m]) for m in cand) or 1
    max_sub = max(subst[m] for m in cand) or 1

    def score(m: str) -> float:
        s = 0.5 * pr[m] / max_pr + 0.3 * len(edges[m]) / max_out + 0.2 * subst[m] / max_sub
        s = s * GENERIC_PENALTY if _stem(m) in GENERIC_STEMS else s
        return s + (0.3 if m in entries else 0)
    ordered = sorted(cand, key=lambda m: (-score(m), m))
    head = [m for m in ordered if m in entries][:2]            # "start here": the best entry point(s) always lead
    return head + [m for m in ordered if m not in head]


def analyze_architecture(root: Path, top: int = 8) -> dict:
    ext: Counter = Counter()
    py_edges, paths, entries = build_graph(root, external=ext)
    js_edges, js_paths, js_entries = build_js_graph(root, external=ext)      # same Counter: third-party imports of both
    edges, paths, entries = {**py_edges, **js_edges}, {**paths, **js_paths}, entries | js_entries
    entries = {m for m in entries if not _NON_ENTRY_DIRS.search(paths[m])}      # also for JS/TS entry files
    nbs = scan_notebooks(root)
    repo_names = {p.name for p in root.iterdir() if p.is_dir()} | {p.stem for p in root.glob("*.py")}
    for nb in nbs:                                                           # notebooks count as importing files too
        ext.update(m for m in nb["imports"] if m not in _STDLIB and m not in repo_names)
    nb_info = {"notebook_files": len(nbs),
               "notebooks": [{k: v for k, v in nb.items() if k != "imports"}
                             for nb in sorted(nbs, key=lambda x: (-x["code_cells"], x["file"]))[:6]]}
    if not edges:
        return {"python_modules": 0, "js_modules": 0, **nb_info,
                "third_party_imports": [{"module": m, "name": IMPORT_ALIASES.get(m, m), "files": c}
                                        for m, c in sorted(ext.items(), key=lambda kv: (-kv[1], kv[0]))[:15]]}
    pr = pagerank(edges)
    imported_by = Counter(w for outs in edges.values() for w in outs)
    ranked = rank_read_first(root, edges, paths, entries, pr, imported_by)[:top]
    groups = [g for g in communities(edges) if len(g) > 1]
    n_edges = sum(len(v) for v in edges.values())
    return {
        "python_modules": len(py_edges),
        "js_modules": len(js_edges),
        **nb_info,
        "import_edges": n_edges,
        "third_party_imports": [{"module": m, "name": IMPORT_ALIASES.get(m, m), "files": c}
                                for m, c in sorted(ext.items(), key=lambda kv: (-kv[1], kv[0]))[:15]],
        "entry_points": sorted(paths[m] for m in entries),
        "read_first": [{"file": paths[m], "importance": round(pr[m] * len(pr), 2),
                        "imported_by": imported_by[m], "imports": len(edges[m])} for m in ranked],
        "subsystems": [{"name": _name_cluster(g), "size": len(g),
                        "files": [paths[m] for m in g[:6]]} for g in groups[:6]],
        "isolated_modules": sorted(paths[m] for m in edges
                                   if not edges[m] and not any(m in e for e in edges.values()))[:15],
    }
