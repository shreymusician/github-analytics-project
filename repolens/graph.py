"""Architecture discovery from the Python import graph, with no ML model.

* PageRank (own implementation) finds the *core* modules: the ones many
  important modules depend on. This answers "which files should I read first?".
* Label propagation finds *communities*: clusters of tightly coupled modules,
  i.e. the real subsystems regardless of how the folders are named.
"""
from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .files import iter_files, read_text

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


def _name_cluster(members: list[str]) -> str:
    first = Counter(m.split(".")[0] if "." in m else m for m in members).most_common(1)[0][0]
    return first


def analyze_architecture(root: Path, top: int = 8) -> dict:
    ext: Counter = Counter()
    edges, paths, entries = build_graph(root, external=ext)
    if not edges:
        return {"python_modules": 0}
    pr = pagerank(edges)
    imported_by = Counter(w for outs in edges.values() for w in outs)
    # modules nobody imports only qualify if they are entry points; otherwise PageRank ties are noise
    ranked = sorted((m for m in pr if imported_by[m] or m in entries), key=lambda m: (-pr[m], m))[:top]
    groups = [g for g in communities(edges) if len(g) > 1]
    n_edges = sum(len(v) for v in edges.values())
    return {
        "python_modules": len(edges),
        "import_edges": n_edges,
        "third_party_imports": [{"module": m, "name": IMPORT_ALIASES.get(m, m), "files": c}
                                for m, c in sorted(ext.items(), key=lambda kv: (-kv[1], kv[0]))[:15]],
        "entry_points": sorted(paths[m] for m in entries),
        "read_first": [{"file": paths[m], "importance": round(pr[m] * len(pr), 2),
                        "imported_by": imported_by[m]} for m in ranked],
        "subsystems": [{"name": _name_cluster(g), "size": len(g),
                        "files": [paths[m] for m in g[:6]]} for g in groups[:6]],
        "isolated_modules": sorted(paths[m] for m in edges
                                   if not edges[m] and not any(m in e for e in edges.values()))[:15],
    }
