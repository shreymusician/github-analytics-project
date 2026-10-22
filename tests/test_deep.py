import pytest

from repolens import discover as d
from repolens import find, profile
from repolens.fetch import FetchError
from tests.test_analyzers import repo, sh, write  # noqa: F401
from tests.test_discover import TODAY, cand  # noqa: F401


def ranked_two():
    return d.rank([cand("a/alpha", desc="rag chatbot", stars=900), cand("b/beta", desc="rag chatbot", stars=800)], "rag chatbot", TODAY)


def test_deep_facts_come_from_a_real_pipeline_result(repo):
    write(repo, ".travis.yml", "language: python\n")
    write(repo, "LICENSE", "MIT\n")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-qm", "ci and license")
    facts = d.deep_facts(profile.run(str(repo)))
    assert facts["tests"] >= 1 and facts["ci"] == "Travis CI" and facts["docker"] is True and facts["license"] is True
    assert facts["status"] in ("active", "stale", "abandoned") and facts["commits"] == 6
    assert 0 <= facts["completeness"] <= 100 and 0 <= facts["deployability"] <= 100
    assert facts["summary"] is None and facts["maturity"] is None                       # no model ran in this result
    assert facts["read_first"] and all(isinstance(f, str) for f in facts["read_first"])


def test_one_failing_repository_does_not_stop_the_others(repo):
    r = ranked_two() + [{**ranked_two()[0], "full_name": "c/gamma"}]
    saved, seen = [], []

    def analyze(name):
        if name == "b/beta":
            raise FetchError("git clone failed: repository not found")
        return profile.run(str(repo))

    deep = d.deep_analyze(r, analyze, 3, save=lambda n, res: saved.append(n), progress=seen.append)
    assert set(deep) == {"a/alpha", "b/beta", "c/gamma"} and "error" in deep["b/beta"] and "FetchError" in deep["b/beta"]["error"]
    assert "completeness" in deep["a/alpha"] and saved == ["a/alpha", "c/gamma"]          # failures are not saved as reports
    assert seen == ["analyzing a/alpha ...", "analyzing b/beta ...", "analyzing c/gamma ..."]
    assert list(d.deep_analyze(r, analyze, 1)) == ["a/alpha"]                                # n limits how many are cloned


def test_deep_facts_change_the_ranking_and_unanalyzed_repos_are_neutral():
    r = ranked_two()
    strong = {"status": "active", "completeness": 100, "deployability": 90}
    weak = {"status": "abandoned", "completeness": 10, "deployability": 10}
    out = d.apply_deep(r, {"a/alpha": weak, "b/beta": strong})
    assert [c["full_name"] for c in out] == ["b/beta", "a/alpha"]
    by = {c["full_name"]: c for c in out}
    assert by["a/alpha"]["parts"]["abandoned penalty"] == -0.10 and "abandoned penalty" not in by["b/beta"]["parts"]
    assert by["b/beta"]["parts"]["completeness"] == 0.15 and by["b/beta"]["parts"]["runnable"] == 0.045
    neutral = d.apply_deep(r, {"a/alpha": strong})
    n = {c["full_name"]: c for c in neutral}["b/beta"]
    assert n["parts"]["completeness"] == 0.075 and n["parts"]["runnable"] == 0.025 and n["deep"] is None     # 50 = "unknown"
    errored = d.apply_deep(r, {"a/alpha": {"error": "FetchError: x"}, "b/beta": strong})
    assert {c["full_name"]: c for c in errored}["a/alpha"]["parts"]["completeness"] == 0.075              # a failure is neutral, not bad
    for c in out:
        assert c["score"] == round(sum(c["parts"].values()), 3)                                          # totals stay explainable


def test_the_guide_shows_deep_facts_failures_and_says_which_repos_were_not_analyzed():
    r = ranked_two()
    facts = {"status": "active", "last_commit": "2026-10-01", "commits": 40, "contributors": 3, "tests": 5, "ci": "GitHub Actions",
             "docker": True, "license": True, "completeness": 90, "deployability": 70, "depth": "full", "maturity": "usable",
             "summary": "A small RAG chatbot.", "read_first": ["app/main.py", "app/rag.py"]}
    md = d.render_guide("rag chatbot", d.apply_deep(r, {"a/alpha": facts, "b/beta": {"error": "FetchError: nope"}}), "keywords", ["rag chatbot"])
    assert "1 of these were also cloned and analyzed in depth" in md and "count as neutral" in md
    assert "**in depth:** active (last commit 2026-10-01, 40 commits, 3 contributor(s)); tests: yes (5 files); CI: GitHub Actions" in md
    assert "completeness 90/100, deployability 70/100; maturity: usable" in md and "what it is: A small RAG chatbot." in md
    assert "start reading: `app/main.py`, `app/rag.py`" in md and "deep analysis failed: FetchError: nope" in md
    plain = d.render_guide("rag chatbot", r, "keywords", ["rag chatbot"])
    assert "Nothing was cloned" in plain and "in depth" not in plain


def test_targets_are_either_the_named_repos_or_the_top_n():
    r = ranked_two()
    assert [c["full_name"] for c in find.select_targets(r, 1, [])] == [r[0]["full_name"]]
    assert [c["full_name"] for c in find.select_targets(r, 0, [])] == []
    assert [c["full_name"] for c in find.select_targets(r, 1, ["B/Beta"])] == ["b/beta"]               # names win over N, case-insensitive
    assert find.select_targets(r, 5, ["not/in-the-list"]) == []                                         # cannot clone what was not found


def test_dry_run_lists_what_would_be_cloned_and_downloads_nothing(monkeypatch, capsys):
    ranked = [{**c, "size_kb": 2048 * (i + 1)} for i, c in enumerate(ranked_two())]
    monkeypatch.setattr(find, "keys_from_env", lambda: {})
    monkeypatch.setattr(find, "gather", lambda *a, **k: [{}])
    monkeypatch.setattr(find, "rank", lambda *a, **k: ranked)
    monkeypatch.setattr(find, "run", lambda *a, **k: pytest.fail("a dry run must not analyze (clone) anything"))
    assert find.main(["rag chatbot", "--no-llm", "--deep", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Would clone 2 repositories" in out and "2 MB" in out and "4 MB" in out and "Nothing was downloaded" in out
    assert find.main(["rag chatbot", "--no-llm", "--deep-repos", "b/beta", "--dry-run"]) == 0
    assert "Would clone 1 repositories" in capsys.readouterr().out


def test_dry_run_prints_the_exact_command_that_reproduces_the_selection(monkeypatch, capsys):
    ranked = [{**c, "size_kb": 1024} for c in ranked_two()]
    monkeypatch.setattr(find, "keys_from_env", lambda: {})
    monkeypatch.setattr(find, "gather", lambda *a, **k: [{}])
    monkeypatch.setattr(find, "rank", lambda *a, **k: ranked)
    monkeypatch.setattr(find, "run", lambda *a, **k: pytest.fail("a dry run must not analyze anything"))
    assert find.main(["rag chatbot", "--language", "python", "--no-llm", "--deep", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "a later run can pick different repositories" in out
    cmd = [l for l in out.splitlines() if "--deep-repos" in l][0].strip()
    assert cmd.startswith('python -m repolens.find "rag chatbot" --language python --deep-repos ')
    assert set(cmd.split("--deep-repos ")[1].split(",")) == {c["full_name"] for c in ranked}


def test_a_named_repository_that_the_search_did_not_return_is_reported_not_silently_skipped(monkeypatch, capsys):
    ranked = [{**c, "size_kb": 1024} for c in ranked_two()]
    monkeypatch.setattr(find, "keys_from_env", lambda: {})
    monkeypatch.setattr(find, "gather", lambda *a, **k: [{}])
    monkeypatch.setattr(find, "rank", lambda *a, **k: ranked)
    monkeypatch.setattr(find, "run", lambda *a, **k: pytest.fail("nothing should be analyzed in a dry run"))
    assert find.main(["rag chatbot", "--no-llm", "--deep-repos", "a/alpha,ghost/repo", "--dry-run"]) == 0
    captured = capsys.readouterr()
    assert "Would clone 1 repositories" in captured.out and "ghost/repo" in captured.err and "NOT analyzed" in captured.err
