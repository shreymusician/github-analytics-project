from repolens import ci, factcheck, signals
from tests.test_analyzers import write  # noqa: F401


def test_detects_the_common_ci_systems():
    paths = [".github/workflows/test.yml", ".travis.yml", ".appveyor.yml", ".circleci/config.yml", ".gitlab-ci.yml",
             "azure-pipelines.yml", "bitbucket-pipelines.yml", "Jenkinsfile", "ci/Jenkinsfile", "README.md", "src/app.py"]
    found = ci.detect(paths)
    assert set(found) == {"GitHub Actions", "Travis CI", "AppVeyor", "CircleCI", "GitLab CI", "Azure Pipelines",
                          "Bitbucket Pipelines", "Jenkins"}
    assert found["Travis CI"] == ".travis.yml" and found["Jenkins"] == "Jenkinsfile"        # first match is reported


def test_config_files_must_be_where_the_tool_looks():
    assert ci.detect(["docs/.travis.yml", "examples/appveyor.yml", "tests/data/.drone.yml"]) == {}   # nested copies are not CI
    assert ci.detect([".github/ISSUE_TEMPLATE/bug.md"]) == {}                                         # .github alone is not workflows
    assert ci.detect([]) == {}


def test_analyzer_and_fact_check_agree_on_a_travis_only_repo(tmp_path):
    """snips-nlu / image-super-resolution: Travis (and AppVeyor), no GitHub Actions."""
    paths = [".travis.yml", ".appveyor.yml", "setup.py", "pkg/a.py"]
    assert factcheck.truth_has_ci(paths) is True
    stack = {"lockfiles": [], "pinned_ratio": None, "manifests": ["setup.py"], "languages": {"Python": 1.0},
             "primary_language": "Python", "_paths": paths}
    for p in paths:
        write(tmp_path, p, "x = 1\n")
    out = signals.assess(tmp_path, stack, {"entry_points": []}, {})
    note = next(e["note"] for e in out["deployability"]["evidence"] if e["note"].startswith(("CI pipeline", "no CI")))
    assert note == "CI pipeline configured (Travis CI, AppVeyor)"
