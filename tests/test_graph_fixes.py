"""Read-first ranking fix found by the Gate A run."""
from repolens import graph
from tests.test_analyzers import write  # noqa: F401


def test_read_first_skips_trivial_modules(tmp_path):
    body = "\n".join(f"def f{i}():\n    return {i}" for i in range(8))
    write(tmp_path, "pkg/__init__.py", "from pkg.core import f0\n")
    write(tmp_path, "pkg/constants.py", "X = 1\n")
    write(tmp_path, "pkg/core.py", body + "\n")
    for i in range(6):
        write(tmp_path, f"pkg/m{i}.py", f"from pkg import constants\nfrom pkg.core import f0\n{body}\n")
    write(tmp_path, "pkg/cli.py", f"from pkg import m0, m1, m2\nfrom pkg.core import f0\n{body}\nif __name__ == '__main__':\n    pass\n")
    files = [r["file"] for r in graph.analyze_architecture(tmp_path)["read_first"]]
    assert files[0] == "pkg/cli.py"
    assert "pkg/constants.py" not in files and "pkg/__init__.py" not in files and "pkg/core.py" in files


def test_scripts_in_docs_debug_examples_are_not_entry_points(tmp_path):
    """snips-nlu reported docs/write_ontology_doc.py and debug/debug.py as its entry points."""
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/__main__.py", "def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n")
    write(tmp_path, "docs/write_doc.py", "if __name__ == '__main__':\n    print('doc')\n")
    write(tmp_path, "debug/debug.py", "if __name__ == '__main__':\n    print('dbg')\n")
    write(tmp_path, "examples/demo/run.py", "if __name__ == '__main__':\n    print('demo')\n")
    write(tmp_path, "scripts/train.py", "if __name__ == '__main__':\n    print('train')\n")        # scripts/ stays: real entry in ML repos
    eps = graph.analyze_architecture(tmp_path)["entry_points"]
    assert eps == ["pkg/__main__.py", "scripts/train.py"]


def test_generic_catch_all_modules_rank_below_equal_peers(tmp_path):
    body = "\n".join(f"def f{i}():\n    return {i}" for i in range(8))
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/utils.py", body + "\n")          # imported by everyone, like most utils modules
    write(tmp_path, "pkg/engine.py", body + "\n")         # imported by the same modules, same size
    for i in range(6):
        write(tmp_path, f"pkg/m{i}.py", f"from pkg import utils, engine\n{body}\n")
    files = [r["file"] for r in graph.analyze_architecture(tmp_path)["read_first"]]
    assert "pkg/engine.py" in files and "pkg/utils.py" in files          # demoted, not excluded
    assert files.index("pkg/engine.py") < files.index("pkg/utils.py")


def test_test_files_never_appear_in_read_first(tmp_path):
    """snips-nlu and llm-scraper listed tests/test_*.py and *.test.ts first: tests import everything, so they score high."""
    body = "\n".join(f"def f{i}():\n    return {i}" for i in range(8))
    write(tmp_path, "pkg/__init__.py", "")
    write(tmp_path, "pkg/engine.py", body + "\n")
    write(tmp_path, "pkg/parser.py", "from pkg import engine\n" + body + "\n")
    for i in range(5):
        write(tmp_path, f"pkg/m{i}.py", f"from pkg import engine, parser\n{body}\n")
    write(tmp_path, "pkg/tests/test_engine.py", "from pkg import engine, parser, m0, m1, m2, m3, m4\n" + body + "\n")   # imports everything
    write(tmp_path, "web/a.test.ts", "import { x } from './b'\n" + "export const a = 1\n" * 15)
    write(tmp_path, "web/b.ts", "export const x = 1\n" * 15)
    files = [r["file"] for r in graph.analyze_architecture(tmp_path)["read_first"]]
    assert files and not any("test" in f for f in files)
    assert "pkg/engine.py" in files
