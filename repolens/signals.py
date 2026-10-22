"""Rule engine for completeness and deployability.

Every point awarded or withheld carries a human-readable reason, so a score is
never an unexplained number. Weights are first guesses; calibrate them against
hand-labeled repos before trusting them.

A check that cannot be run for this repo (e.g. stub detection on TypeScript) is
recorded as "not assessed" and excluded from the score instead of passing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from . import ci
from .files import read_text

_TODO = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
_RUN_WORDS = re.compile(r"\b(install|usage|getting started|run|quick ?start|setup)\b", re.I)
_CODE_EXT = (".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java")
_TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$")
_TEST_BODY_PY = re.compile(r"\bdef test|\bunittest\b|\bpytest\b")
_TEST_BODY_JS = re.compile(r"\b(describe|it|test)\s*\(|\bexpect\s*\(")
_PY_SHARE_FOR_STUB_CHECKS = 0.5


def _has(paths: list[str], pred) -> list[str]:
    return [p for p in paths if pred(p.lower())]


def _is_test(rel: str) -> bool:
    """Path-based: used to keep tests out of the source/stub scans."""
    return bool(_TEST_PATH.search(rel.lower()))


def confirmed_tests(root: Path, paths: list[str]) -> list[str]:
    """Code files in test locations that actually contain tests (so a demo script named test_simple.py
    or fixtures/JSON inside tests/ do not count)."""
    out = []
    for rel in paths:
        if not _is_test(rel) or not rel.lower().endswith(_CODE_EXT):
            continue
        text = read_text(root / rel)
        if rel.lower().endswith(".py"):
            ok = bool(_TEST_BODY_PY.search(text))
        elif rel.lower().endswith((".js", ".jsx", ".ts", ".tsx")):
            ok = bool(_TEST_BODY_JS.search(text))
        else:
            ok = True            # go/rs/java: trust the path
        if ok:
            out.append(rel)
    return out


def _is_abstract(fn) -> bool:
    return any(("abstract" in ast.dump(d).lower() or "overload" in ast.dump(d).lower()) for d in fn.decorator_list)


def _scan_python(root: Path, paths: list[str]) -> dict:
    funcs = stubs = todos = lines = 0
    for rel in paths:
        if not rel.endswith(".py") or _is_test(rel):
            continue
        text = read_text(root / rel)
        lines += text.count("\n") + 1
        todos += len(_TODO.findall(text))
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError, RecursionError):
            continue
        protocol_fns = set()
        for cls in ast.walk(tree):
            if isinstance(cls, ast.ClassDef) and any("Protocol" in ast.dump(b) for b in cls.bases):
                protocol_fns.update(id(n) for n in ast.walk(cls))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_abstract(node) or id(node) in protocol_fns:
                    continue                      # intentionally bodiless: interface, not unfinished work
                funcs += 1
                body = [b for b in node.body
                        if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
                if not body or all(isinstance(b, ast.Pass) or _raises_nie(b) or _is_ellipsis(b) for b in body):
                    stubs += 1
    return {"functions": funcs, "stubs": stubs, "todos": todos, "lines": lines}


def _raises_nie(n) -> bool:
    return (isinstance(n, ast.Raise) and n.exc is not None and "NotImplementedError" in ast.dump(n.exc))


def _is_ellipsis(n) -> bool:
    return isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and n.value.value is Ellipsis


class _Score:
    def __init__(self):
        self.points, self.max, self.evidence = 0, 0, []

    def check(self, ok: bool, weight: int, good: str, bad: str):
        self.max += weight
        if ok:
            self.points += weight
        self.evidence.append({"ok": bool(ok), "weight": weight, "note": good if ok else bad})

    def skip(self, note: str):
        """Check could not be run: shown, but not counted for or against the score."""
        self.evidence.append({"ok": None, "weight": 0, "note": note})

    def result(self) -> dict:
        return {"score": round(100 * self.points / self.max) if self.max else 0, "evidence": self.evidence}


def assess(root: Path, stack: dict, arch: dict, history: dict) -> dict:
    paths: list[str] = stack["_paths"]
    readme_p = _has(paths, lambda p: re.fullmatch(r"readme(\.\w+)?", p) is not None)
    readme = read_text(root / readme_p[0]) if readme_p else ""
    tests = confirmed_tests(root, paths)
    py = _scan_python(root, paths)
    src_files = [p for p in paths if p.endswith(_CODE_EXT) and not _is_test(p)]
    py_share = stack["languages"].get("Python", 0)
    py_checks_apply = py_share >= _PY_SHARE_FOR_STUB_CHECKS and py["functions"] > 0
    stub_ratio = py["stubs"] / py["functions"] if py["functions"] else 0
    todo_density = py["todos"] / max(py["lines"] / 1000, 1)

    # ---- deployability
    d = _Score()
    dockerfile = _has(paths, lambda p: p.rsplit("/", 1)[-1] in {"dockerfile"} or p.endswith(".dockerfile"))
    d.check(bool(dockerfile), 25, f"Dockerfile present ({dockerfile[:1][0] if dockerfile else ''})", "no Dockerfile")
    found_ci = ci.detect(paths)
    d.check(bool(found_ci), 15, f"CI pipeline configured ({', '.join(found_ci)})", "no CI pipeline")
    d.check(bool(stack["lockfiles"]) or (stack["pinned_ratio"] or 0) >= 0.7, 15,
            "dependencies pinned or locked", "dependencies not pinned/locked: builds may not reproduce")
    d.check(bool(stack["manifests"]), 15, f"dependency manifest ({stack['manifests'][:1][0] if stack['manifests'] else ''})",
            "no dependency manifest: setup steps unknown")
    d.check(bool(arch.get("entry_points")) or bool(_has(paths, lambda p: p in {"procfile", "makefile"} or p.endswith("package.json"))),
            10, "clear entry point / run command", "no obvious entry point")
    d.check(bool(_has(paths, lambda p: p.rsplit("/", 1)[-1] in {".env.example", ".env.sample", ".env.template", "env.example"})),
            10, "env template documents configuration", "no env template")
    d.check(bool(_RUN_WORDS.search(readme)), 10, "README explains install/run", "README lacks install/run instructions")

    # ---- completeness
    c = _Score()
    c.check(bool(tests), 20, f"{len(tests)} test file(s)", "no tests found")
    ratio = len(tests) / max(len(src_files), 1)
    c.check(ratio >= 0.15, 10, f"test/source file ratio {ratio:.2f}", f"thin test coverage by file count ({ratio:.2f})")
    c.check(len(readme) >= 500, 15, f"substantial README ({len(readme)} chars)", f"README missing or thin ({len(readme)} chars)")
    c.check(bool(_has(paths, lambda p: p.rsplit("/", 1)[-1].startswith(("license", "copying")))), 5, "license present", "no license: reuse rights unclear")
    if py_checks_apply:
        c.check(stub_ratio < 0.1, 20, f"{py['stubs']}/{py['functions']} functions are stubs",
                f"{py['stubs']}/{py['functions']} functions are empty stubs: unfinished code")
        c.check(todo_density < 5, 10, f"{py['todos']} TODO/FIXME markers", f"{py['todos']} TODO/FIXME markers ({todo_density:.1f}/KLOC)")
    else:
        why = f"code is mostly {stack['primary_language'] or 'non-Python'}" if stack["primary_language"] != "Python" else "too little Python"
        c.skip(f"stub-function check not assessed ({why}; only Python is analyzed)")
        c.skip("TODO/FIXME density not assessed (only Python is analyzed)")
    c.check(len(src_files) >= 5, 10, f"{len(src_files)} source files", f"only {len(src_files)} source file(s): likely a snippet or early draft")
    if history.get("commits"):
        c.check(history["status"] != "abandoned" and history["shape"] != "one-shot-burst", 10,
                f"history looks {history['status']}/{history['shape']}",
                f"history looks {history['status']}/{history['shape']}")

    comp, dep = c.result(), d.result()
    return {
        "completeness": comp, "deployability": dep,
        "analysis_depth": "full" if py_checks_apply else "partial",
        "metrics": {"test_files": len(tests), "source_files": len(src_files), "readme_chars": len(readme),
                    "python": py},
    }
