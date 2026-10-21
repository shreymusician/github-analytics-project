from collections import Counter

from repolens import jsgraph
from tests.test_analyzers import write  # noqa: F401


def test_extracts_every_import_form_and_ignores_comments():
    src = """
import a from './a'
import { b, c } from "../b"
import * as d from './d.js'
import type { T } from './types'
import './side-effect'
export * from './reexport'
export { x } from './named'
const e = require('./e')
const f = await import('./lazy')
import react from 'react'
// import fake from './commented-line'
/* import fake2 from './commented-block' */
const url = "http://example.com//not-a-comment"; import ok from './after-url'
"""
    got = jsgraph.extract_specifiers(src)
    assert got == ["./a", "../b", "./d.js", "./types", "./side-effect", "./reexport", "./named", "./e", "./lazy",
                   "react", "./after-url"]
    assert "./commented-line" not in got and "./commented-block" not in got


def test_package_names_scoped_builtins_and_protocols():
    assert jsgraph.package_name("lodash/fp") == "lodash"
    assert jsgraph.package_name("@ai-sdk/openai") == "@ai-sdk/openai"
    assert jsgraph.package_name("@ai-sdk/openai/internal") == "@ai-sdk/openai"
    for spec in ("./x", "../y", "/abs", "node:fs", "fs", "path", "https://cdn/x.js", "#internal"):
        assert jsgraph.package_name(spec) is None


def test_graph_resolves_relative_imports_index_files_and_ts_js_extension(tmp_path):
    write(tmp_path, "src/index.ts", "import { run } from './core'\nimport util from './util/index'\nimport z from 'zod'\nimport fs from 'fs'\n")
    write(tmp_path, "src/core.ts", "import { helper } from './util'\nimport { m } from './models.js'\nimport { z } from 'zod'\nimport p from '@scope/pkg/deep'\n")
    write(tmp_path, "src/util/index.ts", "export const helper = 1\n")
    write(tmp_path, "src/models.ts", "import { x } from '../../outside'\nexport const m = 1\n")
    write(tmp_path, "src/types.d.ts", "export type T = string\n")
    ext = Counter()
    edges, paths, entries = jsgraph.build_js_graph(tmp_path, external=ext)
    assert edges["src/index.ts"] == {"src/core.ts", "src/util/index.ts"}
    assert edges["src/core.ts"] == {"src/util/index.ts", "src/models.ts"}       # './util' -> util/index.ts ; './models.js' -> models.ts
    assert edges["src/models.ts"] == set()                                       # ../../outside leaves the repo: not an edge
    assert "src/types.d.ts" not in edges                                         # declaration files are not code
    assert ext == Counter({"zod": 2, "@scope/pkg": 1})                           # builtins excluded, files counted once each
    assert entries == {"src/index.ts"}


def test_entry_points_from_package_json_and_bin(tmp_path):
    write(tmp_path, "package.json", '{"main": "dist-src/lib.js", "bin": {"tool": "./cli/run.ts"}}')
    write(tmp_path, "dist-src/lib.js", "module.exports = 1\n")
    write(tmp_path, "cli/run.ts", "console.log(1)\n")
    write(tmp_path, "other/thing.ts", "export const a = 1\n")
    _, _, entries = jsgraph.build_js_graph(tmp_path)
    assert entries == {"dist-src/lib.js", "cli/run.ts"}


def test_broken_package_json_and_empty_repo_do_not_crash(tmp_path):
    write(tmp_path, "package.json", "{not json")
    assert jsgraph.build_js_graph(tmp_path) == ({}, {}, set())


def test_architecture_analysis_covers_a_typescript_project_end_to_end(tmp_path):
    from repolens import graph
    body = "\n".join(f"export function f{i}(x: number) {{ return x + {i} }}" for i in range(8))
    write(tmp_path, "package.json", '{"name": "scraper", "main": "src/index.ts"}')
    write(tmp_path, "src/index.ts", "import { scrape } from './scraper'\nimport z from 'zod'\n" + body + "\n")
    write(tmp_path, "src/scraper.ts", "import { clean } from './cleanup'\nimport { fmt } from './format'\nimport { chromium } from 'playwright'\nimport z from 'zod'\n" + body + "\n")
    write(tmp_path, "src/cleanup.ts", "import { fmt } from './format'\n" + body + "\n")
    write(tmp_path, "src/format.ts", body + "\n")
    write(tmp_path, "src/constants.ts", "export const A = 1\n")
    write(tmp_path, "docs/example.ts", "import { scrape } from '../src/scraper'\n" + body + "\n")
    write(tmp_path, "src/util.ts", body + "\n")
    for i in range(3):
        write(tmp_path, f"src/m{i}.ts", f"import {{ fmt }} from './format'\nimport {{ f1 }} from './util'\n{body}\n")
    a = graph.analyze_architecture(tmp_path)
    assert a["python_modules"] == 0 and a["js_modules"] >= 8
    assert a["entry_points"] == ["src/index.ts"]
    files = [r["file"] for r in a["read_first"]]
    assert files[0] == "src/index.ts" and "src/format.ts" in files            # entry first, then the most-imported module
    assert "src/constants.ts" not in files                                     # trivial one-liner skipped
    assert files.index("src/format.ts") < files.index("src/util.ts")           # catch-all util ranks below an equal peer
    assert {i["module"]: i["files"] for i in a["third_party_imports"]} == {"zod": 2, "playwright": 1}
    assert a["subsystems"] and a["subsystems"][0]["name"] == "src"             # clusters are named by directory for JS


def test_python_and_typescript_in_one_repo_do_not_collide(tmp_path):
    from repolens import graph
    write(tmp_path, "api/__init__.py", "")
    write(tmp_path, "api/server.py", "import numpy\nfrom api import models\n")
    write(tmp_path, "api/models.py", "x = 1\n")
    write(tmp_path, "web/index.ts", "import { api } from './api'\nimport react from 'react'\n")
    write(tmp_path, "web/api.ts", "export const api = 1\n")
    a = graph.analyze_architecture(tmp_path)
    assert a["python_modules"] == 3 and a["js_modules"] == 2
    assert {i["module"] for i in a["third_party_imports"]} == {"numpy", "react"}
