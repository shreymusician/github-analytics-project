import os
import subprocess
import time

import pytest

from repolens import graph, history, stack
from repolens.profile import analyze

DAY = 86400


def sh(cwd, *args, ts=None, author="Ann"):
    env = {**os.environ, "GIT_AUTHOR_NAME": author, "GIT_COMMITTER_NAME": author,
           "GIT_AUTHOR_EMAIL": "a@x.io", "GIT_COMMITTER_EMAIL": "a@x.io"}
    if ts:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = f"{int(ts)} +0000"
    subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True)


def write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "demo"
    r.mkdir()
    sh(r, "init", "-q")
    base = time.time() - 400 * DAY  # last commit will be >1y... adjusted below
    write(r, "requirements.txt", "fastapi==0.110\nchromadb>=0.4\nlangchain\npytest\n")
    write(r, "README.md", "# Demo\n\n## Install\nrun `pip install -r requirements.txt` then `python app/main.py`.\n" + "x" * 600)
    write(r, "Dockerfile", "FROM python:3.11\n")
    write(r, "app/__init__.py", "")
    write(r, "app/core.py", "def core():\n    return 1\n")
    write(r, "app/utils.py", "from app.core import core\n\ndef u():\n    return core()\n")
    write(r, "app/api.py", "from app import core, utils\n\ndef a():\n    return utils.u()\n")
    write(r, "app/main.py", "from app import api\n\nif __name__ == '__main__':\n    api.a()\n")
    write(r, "app/todo.py", "# TODO finish\ndef later():\n    pass\n")
    write(r, "tests/test_core.py", "from app.core import core\n\ndef test_c():\n    assert core() == 1\n")
    sh(r, "add", "-A")
    sh(r, "commit", "-qm", "initial import", ts=base)
    for i in range(4):
        write(r, "app/core.py", f"def core():\n    return {i + 2}\n")
        write(r, "app/utils.py", f"from app.core import core\n\ndef u():\n    return core() + {i}\n")
        sh(r, "add", "-A")
        sh(r, "commit", "-qm", f"fix {i}", ts=base + (i + 1) * DAY, author="Bob" if i == 3 else "Ann")
    return r


def test_stack(repo):
    s = stack.detect_stack(repo)
    assert s["primary_language"] == "Python"
    assert {"rag", "vector-db", "web-api", "llm-orchestration"} <= set(s["capability_tags"])
    assert "chromadb" in s["recognized_dependencies"]
    assert 0 < s["pinned_ratio"] < 1


def test_graph_core_and_entrypoint(repo):
    edges, paths, entries = graph.build_graph(repo)
    assert "app.core" in edges["app.utils"] and "app.core" in edges["app.api"]
    assert paths["app.core"] == "app/core.py"
    assert "app.main" in entries
    pr = graph.pagerank(edges)
    assert max(pr, key=pr.get) == "app.core"          # most depended-on module ranks first
    assert abs(sum(pr.values()) - 1) < 1e-6
    arch = graph.analyze_architecture(repo)
    assert arch["read_first"][0]["file"] == "app/core.py"


def test_communities_split_disconnected_clusters():
    edges = {"a": {"b"}, "b": {"a"}, "c": {"d"}, "d": {"c"}, "e": set()}
    groups = graph.communities(edges)
    assert sorted(map(tuple, groups[:2])) == [("a", "b"), ("c", "d")]


def test_history(repo):
    h = history.analyze_history(repo, now=time.time())
    assert h["commits"] == 5
    assert h["contributors"] == 2 and h["bus_factor"] == 1
    assert h["status"] == "abandoned"                   # last commit ~395 days ago
    assert h["shape"] == "one-shot-burst"
    assert h["hotspots"][0]["file"] in {"app/core.py", "app/utils.py"}
    assert any(set(c["files"]) == {"app/core.py", "app/utils.py"} for c in h["co_changed"])
    assert h["origin_story"][0] == "initial import"


def test_history_status_is_relative_to_now(repo):
    fresh = history.analyze_history(repo, now=time.time() - 395 * DAY + 3 * DAY)
    assert fresh["status"] == "active"


def test_profile_end_to_end(repo):
    p = analyze(str(repo))
    assert p["sha"] and p["stack"]["primary_language"] == "Python"
    dep = {e["note"]: e["ok"] for e in p["deployability"]["evidence"]}
    assert dep["Dockerfile present (Dockerfile)"] is True
    assert any(not e["ok"] and "CI" in e["note"] for e in p["deployability"]["evidence"])
    comp = {e["note"]: e["ok"] for e in p["completeness"]["evidence"]}
    assert any("stub" in k and not v for k, v in comp.items())      # app/todo.py is a stub
    assert 0 < p["completeness"]["score"] < 100 and 0 < p["deployability"]["score"] < 100
    assert "_paths" not in p["stack"]


def test_rejects_garbage_source():
    from repolens.fetch import FetchError, open_repo
    with pytest.raises(FetchError):
        open_repo("not a repo; rm -rf /")
