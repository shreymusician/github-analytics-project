"""Read Jupyter notebooks as text: outline, imports and a compact reading view.

Many AI/ML repos are notebook-first. A notebook is JSON whose size is mostly embedded outputs (plots, base64 images),
so its byte size says little; what matters is the markdown headings and the code cells. Only cell *sources* are read
(never outputs); notebooks are parsed as data and never executed.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

MAX_NOTEBOOK_BYTES = 30_000_000
_MAGIC = re.compile(r"^\s*[%!?]")                           # %matplotlib inline, !pip install ..., ?func
_IMPORT_LINE = re.compile(r"^[ \t]*(?:from[ \t]+([\w.]+)[ \t]+import|import[ \t]+([\w.,\t ]+))", re.M)   # one line only
_HEADING = re.compile(r"^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$")


def _src(cell: dict) -> str:
    s = cell.get("source", "")
    return "".join(s) if isinstance(s, list) else str(s)


def read_notebook(path: Path) -> dict | None:
    """Parsed summary of one notebook, or None if it cannot be read (too big, not JSON, nbformat 3...)."""
    try:
        if path.stat().st_size > MAX_NOTEBOOK_BYTES:
            return None
        nb = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        cells = nb["cells"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(cells, list):
        return None
    headings: list[str] = []
    code: list[str] = []
    n_code = n_md = 0
    has_outputs = False
    for c in cells:
        if not isinstance(c, dict):
            continue
        kind, text = c.get("cell_type"), _src(c)
        if kind == "markdown":
            n_md += 1
            for line in text.splitlines():
                m = _HEADING.match(line)
                if m:
                    headings.append(m.group(2).strip())
        elif kind == "code":
            n_code += 1
            has_outputs = has_outputs or bool(c.get("outputs"))
            code.append("\n".join(l for l in text.splitlines() if not _MAGIC.match(l)))
    return {"title": headings[0] if headings else None, "headings": headings[:25], "code_cells": n_code,
            "markdown_cells": n_md, "has_outputs": has_outputs, "code": "\n\n".join(code), "cells": cells}


def notebook_imports(code: str) -> set[str]:
    """Top-level module names imported by a notebook's code cells (magics already removed)."""
    names: set[str] = set()
    try:
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module.split(".")[0])
        return names
    except (SyntaxError, ValueError, RecursionError):
        pass                                                # cells with syntax errors: fall back to line matching
    for m in _IMPORT_LINE.finditer(code):
        if m.group(1):
            names.add(m.group(1).split(".")[0])
        else:
            names.update(p.strip().split(" as ")[0].split(".")[0] for p in m.group(2).split(",") if p.strip())
    return {n for n in names if n.isidentifier()}


def reading_view(nb: dict, max_lines: int = 80, max_chars: int = 1800) -> str:
    """A compact, human-readable rendering: markdown headings and the start of each code cell, in order.
    Outputs are never included. Truncated to max_lines / max_chars."""
    out: list[str] = []
    for c in nb["cells"]:
        if not isinstance(c, dict):
            continue
        text = _src(c)
        if c.get("cell_type") == "markdown":
            out += [f"## {m.group(2).strip()}" for l in text.splitlines() if (m := _HEADING.match(l))]
        elif c.get("cell_type") == "code":
            body = [l for l in text.splitlines() if l.strip() and not _MAGIC.match(l)]
            if body:
                out += ["```"] + body[:12] + (["..."] if len(body) > 12 else []) + ["```"]
        if len(out) >= max_lines:
            break
    return "\n".join(out[:max_lines])[:max_chars]


def outline(nb: dict) -> str:
    """One line for the evidence packet: title, a few section headings, and how much code there is."""
    sections = [h for h in nb["headings"][1:8]]
    return (f"{nb['code_cells']} code cell(s), {nb['markdown_cells']} markdown cell(s)"
            + (f"; title: {nb['title']}" if nb["title"] else "")
            + (f"; sections: {' | '.join(sections)}" if sections else ""))
