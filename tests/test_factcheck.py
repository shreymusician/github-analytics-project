from datetime import date

from repolens import factcheck as fc


def profile(**over):
    p = {
        "deployability": {"evidence": [{"ok": True, "note": "Dockerfile present (Dockerfile)"},
                                       {"ok": False, "note": "no CI pipeline"}]},
        "completeness": {"evidence": [{"ok": True, "note": "license present"}]},
        "stack": {"manifests": ["pyproject.toml"], "primary_language": "Python", "file_census": {"total_files": 10}},
        "metrics": {"test_files": 3},
        "history": {"status": "active"},
    }
    p.update(over)
    return p


TRUTH = {"paths": ["Dockerfile", "LICENSE", "pyproject.toml", "src/a.py", "tests/test_a.py"],
         "license": "MIT", "last_commit": "2026-10-01", "language": "Python"}


def by_check(rows):
    return {r["check"]: r for r in rows}


def test_all_agree_when_ours_matches_github():
    rows = by_check(fc.compare(profile(), TRUTH, today=date(2026, 10, 21)))
    assert {k: v["agree"] for k, v in rows.items() if k != "has_ci"} == {k: True for k in rows if k != "has_ci"}
    assert rows["has_ci"]["ours"] is False and rows["has_ci"]["truth"] is False and rows["has_ci"]["agree"] is True
    assert fc.summarize(list(rows.values())) == {"checks": len(rows), "agree": len(rows), "disagreements": []}


def test_disagreements_are_reported_by_name():
    truth = {**TRUTH, "paths": TRUTH["paths"] + [".github/workflows/ci.yml"], "license": None}
    truth["paths"].remove("LICENSE")
    s = fc.summarize(fc.compare(profile(), truth, today=date(2026, 10, 21)))
    assert set(s["disagreements"]) == {"has_ci", "has_license"}          # we missed CI; we claimed a license GitHub lacks


def test_activity_status_uses_default_branch_date_and_thresholds():
    for last, expect in (("2026-10-01", "active"), ("2026-03-01", "stale"), ("2024-01-01", "abandoned")):
        assert fc.truth_activity(last, date(2026, 10, 21)) == expect
    rows = by_check(fc.compare(profile(history={"status": "abandoned"}), TRUTH, today=date(2026, 10, 21)))
    assert rows["activity_status"]["agree"] is False and rows["activity_status"]["truth"] == "active"


def test_missing_ground_truth_is_not_counted():
    rows = fc.compare(profile(), {"paths": None, "last_commit": None, "language": None}, today=date(2026, 10, 21))
    assert rows == [] and fc.summarize(rows) == {"checks": 0, "agree": 0, "disagreements": []}


def test_truth_helpers():
    assert fc.truth_has_tests(["web/a.test.ts"]) and fc.truth_has_tests(["pkg/tests/x.py"]) and fc.truth_has_tests(["test_x.py"])
    assert not fc.truth_has_tests(["tests/data.json", "src/main.py"])        # a data file in tests/ is not a test
    assert fc.truth_has_manifest(["requirements-dev.txt"]) and not fc.truth_has_manifest(["README.md"])
    assert fc.truth_has_license(["docs/LICENSE.md"], None) is False          # only top-level files count
    assert fc.truth_has_license([], "Apache-2.0") and not fc.truth_has_license([], "NOASSERTION")
    assert fc.truth_has_dockerfile(["docker/api.dockerfile"]) and fc.truth_has_ci(["Jenkinsfile"])


def test_primary_language_normalizes_notebooks_and_case():
    rows = by_check(fc.compare(profile(stack={"manifests": [], "primary_language": "Jupyter", "file_census": {"total_files": 1}}),
                               {"paths": None, "last_commit": None, "language": "Jupyter Notebook"}, today=date(2026, 10, 21)))
    assert rows["primary_language"]["agree"] is True
