import json

from repolens import notebooks


def nb_file(tmp_path, cells, name="n.ipynb"):
    p = tmp_path / name
    p.write_text(json.dumps({"cells": cells, "nbformat": 4}), encoding="utf-8")
    return p


MD = lambda s: {"cell_type": "markdown", "source": s.splitlines(keepends=True)}
CODE = lambda s, out=False: {"cell_type": "code", "source": s.splitlines(keepends=True),
                             "outputs": [{"data": {"image/png": "A" * 300_000}}] if out else []}


def test_outline_headings_code_and_outputs_flag(tmp_path):
    p = nb_file(tmp_path, [MD("# Training a GPT\nIntro text\n## Embeddings\n### detail"), CODE("import numpy as np\nx = 1", out=True),
                           MD("## Attention"), CODE("%matplotlib inline\n!pip install torch\nprint(1)")])
    nb = notebooks.read_notebook(p)
    assert nb["title"] == "Training a GPT" and nb["headings"] == ["Training a GPT", "Embeddings", "detail", "Attention"]
    assert nb["code_cells"] == 2 and nb["markdown_cells"] == 2 and nb["has_outputs"] is True
    assert "%matplotlib" not in nb["code"] and "!pip" not in nb["code"] and "print(1)" in nb["code"]
    assert notebooks.outline(nb).startswith("2 code cell(s), 2 markdown cell(s); title: Training a GPT; sections: Embeddings")


def test_imports_from_cells_including_broken_ones():
    assert notebooks.notebook_imports("import numpy as np\nfrom torch.nn import Linear\nimport os, json\nfrom . import x") == {"numpy", "torch", "os", "json"}
    broken = "import pandas as pd, matplotlib.pyplot as plt\nfrom sklearn import svm\nthis is not python (((\n"
    assert notebooks.notebook_imports(broken) == {"pandas", "matplotlib", "sklearn"}      # syntax error: line-matching fallback


def test_reading_view_has_headings_and_code_but_never_outputs(tmp_path):
    big = "\n".join(f"x{i} = {i}" for i in range(30))
    nb = notebooks.read_notebook(nb_file(tmp_path, [MD("# Title\n## Step one"), CODE(big, out=True), MD("## Step two"), CODE("y = 2")]))
    view = notebooks.reading_view(nb)
    assert "## Title" in view and "## Step one" in view and "## Step two" in view and "x0 = 0" in view and "y = 2" in view
    assert "..." in view and "x29" not in view                                  # long cells are cut to their first lines
    assert "AAAA" not in view and len(view) <= 1800                             # embedded output never leaks into the view
    assert len(notebooks.reading_view(nb, max_chars=50)) <= 50


def test_unreadable_notebooks_return_none(tmp_path):
    (tmp_path / "bad.ipynb").write_text("{not json", encoding="utf-8")
    (tmp_path / "v3.ipynb").write_text(json.dumps({"worksheets": [{"cells": []}], "nbformat": 3}), encoding="utf-8")
    (tmp_path / "weird.ipynb").write_text(json.dumps({"cells": "nope"}), encoding="utf-8")
    for n in ("bad", "v3", "weird", "missing"):
        assert notebooks.read_notebook(tmp_path / f"{n}.ipynb") is None


def test_notebook_with_odd_cells_and_string_sources_does_not_crash(tmp_path):
    p = nb_file(tmp_path, [{"cell_type": "markdown", "source": "# One-line string source"}, "junk", None,
                           {"cell_type": "code", "source": "import re"}])
    nb = notebooks.read_notebook(p)
    assert nb["title"] == "One-line string source" and nb["code_cells"] == 1
    assert notebooks.notebook_imports(nb["code"]) == {"re"} and "import re" in notebooks.reading_view(nb)


def test_architecture_sees_notebook_imports_outline_and_ignores_local_modules(tmp_path):
    from repolens import graph, stack
    (tmp_path / "mylib").mkdir()
    (tmp_path / "mylib" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    nb_file(tmp_path, [MD("# Welcome to RL\n## Q-learning"), CODE("import gym\nimport numpy as np\nimport mylib\nimport os\n"), CODE("x = 1")], "week1.ipynb")
    nb_file(tmp_path, [MD("# Second"), CODE("import torch\nimport gym")], "week2.ipynb")
    a = graph.analyze_architecture(tmp_path)
    assert a["notebook_files"] == 2 and a["notebooks"][0]["file"] == "week1.ipynb"          # most code cells first
    assert a["notebooks"][0]["title"] == "Welcome to RL" and "imports" not in a["notebooks"][0]
    mods = {i["module"]: i["files"] for i in a["third_party_imports"]}
    assert mods == {"gym": 2, "numpy": 1, "torch": 1}                                        # not os (stdlib), not mylib (local)
    assert {"reinforcement-learning", "deep-learning", "data"} <= set(stack.tags_for_imports(a["third_party_imports"]))


def test_notebook_only_repo_still_reports_notebooks_without_python_modules(tmp_path):
    from repolens import graph
    nb_file(tmp_path, [MD("# Only a notebook"), CODE("import pandas as pd")], "only.ipynb")
    a = graph.analyze_architecture(tmp_path)
    assert a["python_modules"] == 0 and a["js_modules"] == 0 and a["notebook_files"] == 1
    assert [i["module"] for i in a["third_party_imports"]] == ["pandas"]
