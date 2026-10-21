"""Import graph for JavaScript / TypeScript, with no parser dependency.

Regex extraction is less exact than a real parser (tree-sitter is the later upgrade), but it handles the forms that
matter for architecture: ES `import ... from`, `export ... from`, side-effect imports, `require()` and dynamic
`import()`. Comments are blanked first. Path aliases (tsconfig `paths`, bundler aliases) are NOT resolved: an aliased
import is treated as an external package, which can only under-report internal edges, never invent them.

Module ids are repo-relative file paths, so they cannot collide with the Python graph's dotted module names.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .files import iter_files, read_text

JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_RESOLVE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".json")
_ENTRY_STEMS = {"index", "main", "app", "cli", "server"}
_NODE_BUILTINS = {"assert", "buffer", "child_process", "cluster", "crypto", "dns", "events", "fs", "http", "https", "net", "os",
                  "path", "perf_hooks", "process", "querystring", "readline", "stream", "string_decoder", "timers", "tls",
                  "url", "util", "v8", "vm", "worker_threads", "zlib"}

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
# `//` starts a comment only at line start or after whitespace/punctuation; inside a word it is part of a URL string.
_LINE_COMMENT = re.compile(r"(?m)(?:^|(?<=[\s;{}(),]))//[^\n]*")
_SPECIFIER = re.compile(
    r"""(?:\bimport\s+(?:[\w*${}\s,]+?\s+from\s+)?|\bexport\s+(?:\*(?:\s+as\s+\w+)?|\{[^}]*\})\s+from\s+|"""
    r"""\brequire\s*\(\s*|\bimport\s*\(\s*)['"]([^'"\n]+)['"]""")


def extract_specifiers(text: str) -> list[str]:
    """Module specifiers imported by a JS/TS source text, in order, duplicates removed."""
    text = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))
    return list(dict.fromkeys(m.group(1) for m in _SPECIFIER.finditer(text)))


def package_name(spec: str) -> str | None:
    """The npm package a bare specifier refers to ('lodash/fp' -> 'lodash', '@ai-sdk/openai/x' -> '@ai-sdk/openai'),
    or None for relative, absolute, protocol or Node-builtin specifiers."""
    if spec.startswith((".", "/", "#")) or ":" in spec.split("/")[0]:
        return None                                    # node:fs, https://..., data:, file:
    parts = spec.split("/")
    name = "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]
    return None if name in _NODE_BUILTINS else name


def _resolve(importer: str, spec: str, known: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = (Path(importer).parent / spec).as_posix()
    parts: list[str] = []
    for seg in base.split("/"):                        # normalise ./ and ../ without touching the filesystem
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(seg)
    norm = "/".join(parts)
    candidates = [norm, *(norm + e for e in _RESOLVE_EXTS), *(f"{norm}/index{e}" for e in _RESOLVE_EXTS)]
    # TypeScript writes './x.js' for a file that is really x.ts
    stem, dot, ext = norm.rpartition(".")
    if dot and ext in ("js", "jsx", "mjs", "cjs"):
        candidates += [stem + e for e in (".ts", ".tsx", ".mts", ".cts")]
    return next((c for c in candidates if c in known), None)


def _package_entries(root: Path, known: set[str]) -> set[str]:
    """Entry files declared in package.json (main, module, bin), when they exist in the repo."""
    entries: set[str] = set()
    pj = root / "package.json"
    if not pj.is_file():
        return entries
    try:
        data = json.loads(read_text(pj))
    except ValueError:
        return entries
    declared = [data.get("main"), data.get("module"), data.get("source")]
    b = data.get("bin")
    declared += list(b.values()) if isinstance(b, dict) else [b]
    for d in declared:
        if isinstance(d, str):
            hit = _resolve("package.json", "./" + d.lstrip("./"), known)
            if hit:
                entries.add(hit)
    return entries


def build_js_graph(root: Path, external: Counter | None = None) -> tuple[dict[str, set[str]], dict[str, str], set[str]]:
    """Return (edges importer->{imported}, id->relpath, entry ids) over the repo's JS/TS source files.

    `external`, if given, is filled with {npm package: number of files importing it}.
    """
    files = {rel: path for rel, path, _ in iter_files(root) if rel.lower().endswith(JS_EXTS) and not rel.lower().endswith(".d.ts")}
    known = set(files)
    edges: dict[str, set[str]] = {rel: set() for rel in files}
    for rel, path in files.items():
        pkgs: set[str] = set()
        for spec in extract_specifiers(read_text(path)):
            target = _resolve(rel, spec, known)
            if target and target != rel:
                edges[rel].add(target)
            elif target is None and (pkg := package_name(spec)):
                pkgs.add(pkg)
        if external is not None:
            external.update(pkgs)
    entries = _package_entries(root, known)
    for rel in files:
        parts = rel.split("/")
        if Path(rel).stem.lower() in _ENTRY_STEMS and len(parts) <= 2 and parts[0] in (Path(rel).name, "src", "bin", "lib"):
            entries.add(rel)
    return edges, {rel: rel for rel in files}, entries
