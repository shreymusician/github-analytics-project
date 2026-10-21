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
