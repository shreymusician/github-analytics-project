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
