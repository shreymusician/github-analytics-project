import json
import time

import pytest

from repolens import profile
from repolens.web import service as svc
from repolens.web.jobs import JobManager
from repolens.web.service import BadRequest, Service
from tests.test_analyzers import repo, sh, write  # noqa: F401
from tests.test_discover import FakeExt, cand  # noqa: F401
from tests.test_v1 import FakeRouter  # noqa: F401


def wait(jm, jid, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        snap = jm.get(jid)
        if snap["status"] in ("done", "error"):
            return snap
        time.sleep(0.01)
    raise AssertionError("job did not finish")


# ------------------------------------------------------------------ jobs
def test_job_reports_progress_then_result():
    jm = JobManager()
    jid = jm.submit("t", lambda progress: (progress("step one"), progress("step two"), {"answer": 42})[2])
    snap = wait(jm, jid)
    assert snap["status"] == "done" and snap["result"] == {"answer": 42} and snap["progress"] == ["step one", "step two"]
    assert jm.get(jid, since=1)["progress"] == ["step two"] and jm.get(jid, since=1)["next"] == 2          # polling resumes where it left off
    assert jm.get("nope") is None


def test_job_errors_are_captured_and_never_contain_a_key():
    jm = JobManager()
    def boom(progress):
        progress("using sk-abcdefghijklmnopqrstuvwxyz0123 to call")
        raise RuntimeError("request failed for key gsk_abcdefghijklmnopqrstuvwxyz0123")
    snap = wait(jm, jm.submit("t", boom))
    assert snap["status"] == "error" and snap["result"] is None and "RuntimeError" in snap["error"]
    assert "gsk_abcdef" not in snap["error"] and all("sk-abcdefgh" not in line for line in snap["progress"])


def test_a_job_can_only_be_read_by_its_owner_and_active_jobs_are_counted():
    jm = JobManager()
    gate = []
    jid = jm.submit("t", lambda progress: (time.sleep(0.2), {"ok": 1})[1], owner=7)
    assert jm.active_for(7) == 1 and jm.active_for(8) == 0
    assert jm.get(jid, owner=8) is None and jm.get(jid, owner=None) is None and jm.get(jid, owner=7) is not None
    end = time.time() + 5
    while jm.get(jid, owner=7)["status"] not in ("done", "error") and time.time() < end:
        time.sleep(0.02)
    assert jm.active_for(7) == 0 and jm.get(jid, owner=7)["result"] == {"ok": 1}


def test_only_a_limited_number_of_jobs_run_at_once_and_old_jobs_are_forgotten():
    jm = JobManager(max_running=1)
    order = []
    def slow(tag):
        def f(progress):
            order.append(f"start {tag}"); time.sleep(0.05); order.append(f"end {tag}"); return {"tag": tag}
        return f
    a, b = jm.submit("t", slow("a")), jm.submit("t", slow("b"))
    wait(jm, a); wait(jm, b)
    assert order.index("end a") < order.index("start b") or order.index("end b") < order.index("start a")   # never overlapped
    ids = [jm.submit("t", lambda p: {}) for _ in range(60)]
    wait(jm, ids[-1])
    assert jm.get(ids[0]) is None and jm.get(ids[-1]) is not None                                        # only the newest 50 are kept


# ------------------------------------------------------------------ input checks
def test_only_github_repositories_are_accepted():
    assert svc.parse_source("owner/name") == "owner/name"
    assert svc.parse_source(" https://github.com/Cinnamon/kotaemon.git ") == "Cinnamon/kotaemon"
    for bad in ("", "   ", "C:/Users/me/secret", "/etc/passwd", "./local", "..\\x", "owner", "a/b/c", "https://evil.com/a/b", "a/..", "../x",
                "owner/name; rm -rf /", "x" * 300, "file:///etc/passwd", "git@github.com:a/b.git"):
        with pytest.raises(BadRequest):
            svc.parse_source(bad)


def test_status_lists_models_but_no_keys_and_server_keys_are_off_unless_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_SECRETSECRETSECRETSECRET")
    st = Service(tmp_path).status()
    assert "SECRET" not in json.dumps(st) and "groq" in st["models"]
    assert Service(tmp_path).fixed_router is None                       # hosted users bring their own keys
    assert Service(tmp_path, use_server_keys=True).fixed_router is not None
    assert Service.router_for({}) is None and Service.router_for({"groq": "gsk_abcdefghijkl"}) is not None


# ------------------------------------------------------------------ feedback
def test_feedback_is_validated_and_bounded(tmp_path):
    s = Service(tmp_path)
    ok = s.add_feedback({"kind": "find", "target": "a/b", "rating": "up", "goal": "rag chatbot", "note": "great"})
    assert ok == {"kind": "find", "target": "a/b", "rating": "up", "goal": "rag chatbot", "note": "great"}
    for bad in ({}, {"kind": "x", "target": "a", "rating": "up"}, {"kind": "find", "target": "", "rating": "up"},
                {"kind": "find", "target": "a", "rating": "meh"}):
        with pytest.raises(BadRequest):
            s.add_feedback(bad)
    big = s.add_feedback({"kind": "find", "target": "t" * 999, "rating": "up", "note": "n" * 999})
    assert len(big["target"]) == 200 and len(big["note"]) == 500         # stored text is bounded


# ------------------------------------------------------------------ reports
def test_reports_are_listed_and_read_only_from_inside_the_reports_folder(tmp_path):
    (tmp_path / "reports/gate_a").mkdir(parents=True)
    (tmp_path / "reports/find").mkdir(parents=True)
    (tmp_path / "secret.json").write_text('{"profile": {}}', encoding="utf-8")
    (tmp_path / "reports/gate_a/01_a__b.json").write_text("{}", encoding="utf-8")
    (tmp_path / "reports/gate_a/summary.json").write_text("[]", encoding="utf-8")
    (tmp_path / "reports/gate_a/run.log").write_text("x", encoding="utf-8")
    (tmp_path / "reports/find/c__d.md").write_text("# report\nhello", encoding="utf-8")
    s = Service(tmp_path)
    listed = {(r["group"], r["label"], r["kind"]) for r in s.reports()}
    assert listed == {("gate_a", "a/b", "json"), ("find", "c/d", "md")}                                  # summary files and logs are not reports
    assert s.report("find/c__d.md") == {"markdown": "# report\nhello"}
    for bad in ("../secret.json", "..\\secret.json", "/etc/passwd", "gate_a/summary.log", "gate_a/nope.json", "find", ""):
        with pytest.raises(BadRequest):
            s.report(bad)
    with pytest.raises(BadRequest):
        s.report("gate_a/01_a__b.json")                                                                  # valid JSON but not a repo report


def test_present_trims_the_result_and_adds_evidence_facts_and_markdown(repo):
    result = profile.run(str(repo))
    out = svc.present(result)
    assert "samples" not in out["profile"] and "path_index" not in out["profile"]["stack"]
    assert out["evidence"] and all(k.startswith(("E", "S")) for k in out["evidence"]) and len(out["markdown"]) > 500
    assert "## At a glance" in out["markdown"] and out["facts"]["completeness"] == result["profile"]["completeness"]["score"]
    assert json.dumps(out)                                                                              # everything is JSON-serializable


# ------------------------------------------------------------------ the project tab
def test_project_info_is_built_from_the_real_files(tmp_path):
    (tmp_path / "repolens").mkdir()
    (tmp_path / "repolens/alpha.py").write_text('"""Does the alpha thing.\n\nMore."""\nx = 1\n', encoding="utf-8")
    (tmp_path / "repolens/stack.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_a.py").write_text("def test_one():\n    pass\n\ndef test_two():\n    pass\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/DECISIONS.md").write_text("# Decisions\n\n## D1. First choice\n**Decision:** do it.\n\nWhy.\n\n## D2. Second\ntext\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data/progress.json").write_text(json.dumps({"versions": [
        {"id": "V0", "name": "A", "weight": 1, "items": [{"t": "x", "s": "done"}]},
        {"id": "V1", "name": "B", "weight": 3, "items": [{"t": "y", "s": "done", "w": 1}, {"t": "z", "s": "todo", "w": 3}]},
        {"id": "V5", "name": "C", "weight": 4, "items": [{"t": "q", "s": "partial"}]}], "limits": ["l"]}), encoding="utf-8")
    p = Service(tmp_path).project()
    assert p["stats"]["modules"] == 2 and p["stats"]["test_functions"] == 2 and p["stats"]["code_lines"] > 0
    mods = {m["name"]: m for m in p["modules"]}
    assert mods["alpha"]["summary"] == "Does the alpha thing." and mods["stack"]["layer"] == "analyzers"
    assert [d["id"] for d in p["decisions"]] == ["D1", "D2"] and p["decisions"][0]["title"] == "First choice" and "do it" in p["decisions"][0]["text"]
    pct = {v["id"]: v["percent"] for v in p["roadmap"]["versions"]}
    assert pct == {"V0": 100, "V1": 25, "V5": 50}                                                       # V1: 1 done of weight 1+3
    assert p["roadmap"]["overall"]["core"] == round((100 * 1 + 25 * 3) / 4) and p["roadmap"]["overall"]["full"] == round((100 + 75 + 200) / 8)
    assert len(p["pipeline"]) == 7 and p["commits"] == [] and p["verification"] == {}                     # no git repo / reports here: empty, not a crash


# ------------------------------------------------------------------ find / analyze through the service
def test_find_returns_cards_order_and_progress_and_validates_input():
    ext = FakeExt({"rag chatbot": [cand("a/rag-chatbot", desc="A rag chatbot", stars=900), cand("b/other-rag-chatbot", desc="rag chatbot", stars=500)]})
    ext.last_status = None
    s = Service(".", ext=ext, router=None)
    steps = []
    out = s.find("rag chatbot", "Python", 5, steps.append)
    assert out["language"] == "python" and out["how"] == "keywords" and out["requested"] == 5
    assert {c["full_name"] for c in out["ranked"]} == {"a/rag-chatbot", "b/other-rag-chatbot"} and out["order"]
    card = out["ranked"][0]
    assert card["url"].startswith("https://github.com/") and "relevance" in card["parts"] and card["score"] > 0
    assert steps[0].startswith("Turning your goal") and steps[-1] == "Done." and json.dumps(out)
    for bad in ("", "   ", "x" * 301):
        with pytest.raises(BadRequest):
            s.find(bad, None, 5, steps.append)
    with pytest.raises(BadRequest):
        s.find("rag chatbot", "py thon; drop", 5, steps.append)
    with pytest.raises(BadRequest):
        s.find("the and of", None, 5, steps.append)                                                      # nothing searchable


def test_analyze_rejects_local_paths_and_returns_the_presented_result(repo, monkeypatch):
    s = Service(".", ext=FakeExt(), router=None)
    with pytest.raises(BadRequest):
        s.analyze(str(repo), lambda m: None)                                                             # a real local folder is still refused
    class NoDb:
        def close(self): pass
    monkeypatch.setattr(svc, "Store", lambda *a, **k: NoDb())
    monkeypatch.setattr(svc, "run", lambda name, **k: profile.run(str(repo)))
    msgs = []
    out = s.analyze("owner/name", msgs.append)
    assert out["markdown"] and out["facts"] and msgs[0].startswith("Fetching owner/name") and "no model keys" in msgs[1] and msgs[-1] == "Done."
