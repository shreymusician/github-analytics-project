"""Honest reporting of checks that could not run (non-Python repos)."""
from repolens import evidence, profile
from tests.test_analyzers import sh, write  # noqa: F401


def test_non_python_repo_marks_checks_not_assessed(tmp_path):
    sh(tmp_path, "init", "-q")
    for i in range(6):
        write(tmp_path, f"src/m{i}.ts", f"export const a{i} = {i}\n")
    write(tmp_path, "README.md", "# t\n" + "x" * 600)
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "x")
    p = profile.analyze(str(tmp_path))
    assert p["analysis_depth"] == "partial"
    skipped = [e for e in p["completeness"]["evidence"] if e["ok"] is None]
    assert len(skipped) == 2 and all(e["weight"] == 0 for e in skipped)
    text = evidence.packet_text(evidence.build_packet(p))
    assert "NOT ASSESSED" in text and "PARTIAL" in text


def test_partial_wording_is_accurate_about_what_the_graph_covers(tmp_path):
    """The graph understands Python and JS/TS; the stub/TODO checks only Python. The text must not say otherwise."""
    from repolens import evidence
    from repolens.report import render
    sh(tmp_path, "init", "-q")
    for i in range(6):
        write(tmp_path, f"src/m{i}.ts", f"import {{ x }} from './m{(i + 1) % 6}'\nexport const a{i} = {i}\n" * 3)
    write(tmp_path, "README.md", "# t\n" + "x" * 600)
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "x")
    p = profile.analyze(str(tmp_path))
    assert p["architecture"]["js_modules"] == 6
    text = evidence.packet_text(evidence.build_packet(p))
    assert "covers Python and JavaScript/TypeScript" in text and "stub-function and TODO checks only cover Python" in text
    assert "Python and JavaScript/TypeScript" in render({"profile": p, "narrative": None, "cache": {}, "timings": {}})

    other = tmp_path.parent / (tmp_path.name + "_go")
    other.mkdir()
    sh(other, "init", "-q")
    for i in range(6):
        write(other, f"cmd/m{i}.go", f"package main\nfunc f{i}() {{}}\n")
    sh(other, "add", "-A")
    sh(other, "commit", "-qm", "x")
    q = profile.analyze(str(other))
    assert "No import graph could be built" in evidence.packet_text(evidence.build_packet(q))


def test_report_opens_with_an_at_a_glance_block_of_deterministic_facts(tmp_path):
    from repolens.report import render
    sh(tmp_path, "init", "-q")
    write(tmp_path, "requirements.txt", "numpy==1.0\nrequests\n")
    write(tmp_path, "src/app.py", "def run():\n    return 1\n" * 10)
    write(tmp_path, "tests/test_app.py", "def test_x():\n    assert True\n")
    write(tmp_path, ".travis.yml", "language: python\n")
    write(tmp_path, "Dockerfile", "FROM python:3.11\n")
    write(tmp_path, "LICENSE", "MIT\n")
    write(tmp_path, "README.md", "# t\n" + "x" * 600)
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "x")
    p = profile.analyze(str(tmp_path))
    p["external"] = {"github": {"source": "github", "full_name": "o/r", "description": None, "stars": 42, "forks": 1, "archived": True,
                                "fork": False, "topics": [], "pushed_at": "2026-01-01", "license": "MIT", "language": "Python"}}
    md = render({"profile": p, "narrative": None, "cache": {}, "timings": {}})
    glance = md.split("## At a glance")[1].split("\n## ")[0]
    assert md.index("## At a glance") < md.index("## Scores")
    for needle in ("**Language:** Python", "**Maintenance:** active", "**Tests:** yes (1 test files)", "**CI:** Travis CI",
                   "**Docker:** yes", "**License:** yes (MIT)", "42 stars, archived: yes", "**Main libraries:** numpy, requests",
                   "**Source folders:** src"):
        assert needle in glance, needle
    assert "tests" not in glance.split("Source folders:")[1]                       # test folders are not source folders
