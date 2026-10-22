"""Which CI/CD systems a repository is configured for, from its file list alone.

One list shared by the analyzer (signals) and the fact-check (factcheck), so they cannot disagree about what
counts. History: the first version only knew GitHub Actions and GitLab, and both the analyzer and the
"independent" fact-check said snips-nlu and image-super-resolution had no CI, although they use Travis and
AppVeyor. The answerability test caught it because a README reader answered correctly and our key did not.
"""
from __future__ import annotations

# (label, matcher): a lower-cased repo-relative path matches if it starts with the prefix or equals the name.
_PREFIXES = {
    ".github/workflows/": "GitHub Actions",
    ".circleci/": "CircleCI",
    ".buildkite/": "Buildkite",
    ".woodpecker/": "Woodpecker",
    ".teamcity/": "TeamCity",
}
_FILES = {
    ".gitlab-ci.yml": "GitLab CI",
    ".travis.yml": "Travis CI",
    "appveyor.yml": "AppVeyor",
    ".appveyor.yml": "AppVeyor",
    "azure-pipelines.yml": "Azure Pipelines",
    "bitbucket-pipelines.yml": "Bitbucket Pipelines",
    ".drone.yml": "Drone",
    "jenkinsfile": "Jenkins",
    "cloudbuild.yaml": "Google Cloud Build",
    "cloudbuild.yml": "Google Cloud Build",
    ".cirrus.yml": "Cirrus CI",
    ".woodpecker.yml": "Woodpecker",
    "wercker.yml": "Wercker",
    "codeship-steps.yml": "Codeship",
    "buddy.yml": "Buddy",
}


def detect(paths: list[str]) -> dict[str, str]:
    """{CI system label: first matching path}, for every CI system found."""
    found: dict[str, str] = {}
    for p in paths:
        low = p.lower()
        base = low.rsplit("/", 1)[-1]
        label = next((v for k, v in _PREFIXES.items() if low.startswith(k)), None) or (
            _FILES.get(base) if "/" not in low or base in ("jenkinsfile",) else None)
        if label and label not in found:
            found[label] = p
    return found
