"""Stack detection fixes found by the Gate A run: missed manifests, asset-skewed census, notebook sizes."""
import json

from repolens import stack
from tests.test_analyzers import write  # noqa: F401


def test_setup_py_install_requires_is_a_manifest(tmp_path):
    write(tmp_path, "setup.py", "from setuptools import setup\nsetup(name='x', install_requires=['numpy==1.2', 'pandas>=1', 'six'])\n")
    write(tmp_path, "a.py", "x = 1\n")
    s = stack.detect_stack(tmp_path)
    assert s["manifests"] == ["setup.py"] and set(s["dependencies"]) == {"numpy", "pandas", "six"}


def test_setup_py_is_parsed_not_executed(tmp_path):
    write(tmp_path, "setup.py", "import os\nos.system('echo pwned > pwned.txt')\nfrom setuptools import setup\nsetup(install_requires=read_reqs())\n")
    s = stack.detect_stack(tmp_path)
    assert not (tmp_path / "pwned.txt").exists() and s["manifests"] == ["setup.py"] and s["dependencies"] == []


def test_setup_cfg_pipfile_conda(tmp_path):
    write(tmp_path, "setup.cfg", "[options]\ninstall_requires =\n    torch>=2\n    tqdm\n")
    write(tmp_path, "Pipfile", "[packages]\nflask = \"*\"\nrequests = \"==2.1\"\n")
    write(tmp_path, "environment.yml", "name: e\ndependencies:\n  - python=3.11\n  - numpy=1.26\n  - pip:\n    - foo\nchannels:\n  - defaults\n")
    s = stack.detect_stack(tmp_path)
    assert {"torch", "tqdm", "flask", "requests", "numpy", "python"} <= set(s["dependencies"])
    assert "foo" in s["dependencies"] and "pip" not in s["dependencies"]      # pip-section packages are real deps
    assert len(s["manifests"]) == 3


def test_authored_vs_assets_census():
    c = stack.file_census([("logo.png", 9_000_000), ("weights.hdf5", 90_000_000), ("a.py", 6000), ("README.md", 4000)])
    assert c["authored"] == {"code": 0.6, "docs": 0.4}
    assert c["assets_share_bytes"] > 0.99
    assert list(c["categories"])[0] == "other"                       # raw bytes still available


def test_notebook_size_counts_source_not_outputs(tmp_path):
    nb = {"cells": [{"cell_type": "code", "source": ["print(1)\n"], "outputs": [{"data": {"image/png": "A" * 500_000}}]}]}
    p = tmp_path / "n.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    assert stack.notebook_source_bytes(p) == len("print(1)\n")
    assert stack.notebook_source_bytes(tmp_path / "missing.ipynb") is None


def test_notable_files_include_source_files_of_any_language():
    paths = ["README.md", "src/index.ts", "src/models.ts", "src/deep/nested/util.ts", "tests/a.test.ts",
             "notebooks/a.ipynb", "package.json", "logo.png"]
    n = stack.notable_files(paths)
    assert "src/index.ts" in n and "src/models.ts" in n and "README.md" in n and "package.json" in n
    assert "tests/a.test.ts" not in n and "logo.png" not in n            # tests and binaries are not reading suggestions
    assert n.index("src/index.ts") < n.index("src/deep/nested/util.ts")  # shallow files first
