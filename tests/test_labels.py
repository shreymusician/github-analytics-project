import csv

from repolens import labels


def mrow(repo, c=50, d=40, version=7, dropped=0):
    return labels.machine_row({"repo": repo, "completeness": c, "deployability": d, "provider": "groq", "dropped": dropped},
                              {"analysis_depth": "full"}, version)


def test_creates_file_with_empty_human_columns(tmp_path):
    p = tmp_path / "x" / "labels.csv"
    labels.merge(p, [mrow("a/b"), mrow("c/d")])
    rows = labels.load(p)
    assert list(rows) == ["a/b", "c/d"]
    assert rows["a/b"]["machine_completeness"] == "50" and rows["a/b"]["analysis_depth"] == "full"
    assert all(rows["a/b"][h] == "" for h in labels.HUMAN)
    with open(p, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == labels.COLUMNS


def test_refresh_updates_machine_columns_but_never_human_ones(tmp_path):
    p = tmp_path / "l.csv"
    labels.merge(p, [mrow("a/b", c=50)])
    rows = labels.load(p)
    rows["a/b"].update({"insight_0_2": "2", "trust": "yes", "notes": 'good, but "read first" list is odd'})
    with open(p, "w", newline="", encoding="utf-8") as f:                    # the reviewer edits the file
        w = csv.DictWriter(f, fieldnames=labels.COLUMNS)
        w.writeheader()
        w.writerow({c: rows["a/b"].get(c, "") for c in labels.COLUMNS})
    labels.merge(p, [mrow("a/b", c=77, version=8), mrow("e/f")])               # a later run: new scores, new repo
    got = labels.load(p)
    assert got["a/b"]["machine_completeness"] == "77" and got["a/b"]["analyzer_version"] == "8"
    assert got["a/b"]["insight_0_2"] == "2" and got["a/b"]["trust"] == "yes"
    assert got["a/b"]["notes"] == 'good, but "read first" list is odd'        # commas and quotes round-trip
    assert "e/f" in got


def test_repos_missing_from_a_run_are_kept(tmp_path):
    p = tmp_path / "l.csv"
    labels.merge(p, [mrow("a/b"), mrow("c/d")])
    labels.merge(p, [mrow("a/b")])                                              # c/d skipped this time
    assert set(labels.load(p)) == {"a/b", "c/d"}


def test_problems_flags_bad_values_but_not_empty_cells(tmp_path):
    p = tmp_path / "l.csv"
    labels.merge(p, [mrow("a/b")])
    assert labels.problems(p) == []                                            # nothing reviewed yet is not a problem
    rows = labels.load(p)
    rows["a/b"].update({"insight_0_2": "5", "completeness_verdict": "about_right", "trust": "definitely",
                        "false_statements": "two", "read_first_quality": "good"})
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=labels.COLUMNS)
        w.writeheader()
        w.writerow({c: rows["a/b"].get(c, "") for c in labels.COLUMNS})
    msgs = labels.problems(p)
    assert len(msgs) == 3 and any("insight_0_2" in m for m in msgs) and any("trust" in m for m in msgs)
    assert any("false_statements" in m for m in msgs)
