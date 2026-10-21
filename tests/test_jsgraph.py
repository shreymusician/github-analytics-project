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
