from repolens import profile, stack
from tests.test_analyzers import sh, write  # noqa: F401


def picks(tmp_path, files, arch=None):
    st = {"notable_files": stack.notable_files(files), "_paths": files}
    return profile.pick_arch_files(tmp_path, st, arch or {"read_first": []})


def test_non_python_repo_gets_entry_like_files_first_then_big_ones(tmp_path):
    write(tmp_path, "src/utils/zzz.ts", "x" * 5000)
    write(tmp_path, "src/index.ts", "export const a = 1\n")
    write(tmp_path, "src/helpers.ts", "x" * 2000)
    write(tmp_path, "src/big.ts", "x" * 9000)
    write(tmp_path, "dist/index.min.js", "x" * 90000)
    files = ["src/utils/zzz.ts", "src/index.ts", "src/helpers.ts", "src/big.ts", "dist/index.min.js", "README.md"]
    got = picks(tmp_path, files)
    assert got[0] == "src/index.ts"                                 # entry-like name wins despite being tiny
    assert got.index("src/big.ts") < got.index("src/helpers.ts")      # then shallow, biggest first
    assert "dist/index.min.js" not in got and "README.md" not in got  # generated/minified and non-code are skipped


def test_python_import_graph_picks_come_first_and_cap_applies(tmp_path):
    for i in range(10):
        write(tmp_path, f"m{i}.py", "x = 1\n" * 20)
    files = [f"m{i}.py" for i in range(10)]
    got = picks(tmp_path, files, {"read_first": [{"file": "m7.py"}, {"file": "m3.py"}]})
    assert got[:2] == ["m7.py", "m3.py"] and len(got) == profile.ARCH_FILES and len(set(got)) == len(got)


def test_samples_carry_redacted_architecture_excerpts(tmp_path):
    sh(tmp_path, "init", "-q")
    write(tmp_path, "main.py", "KEY = 'sk-abcdefghijklmnopqrstuvwxyz0123'\n" + "def run():\n    return 1\n" * 3)
    write(tmp_path, "README.md", "# x\n" + "y" * 600)
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "x")
    p = profile.analyze(str(tmp_path))
    ex = p["samples"]["arch_excerpts"]
    assert [e["file"] for e in ex] == ["main.py"] and "sk-abcdefgh" not in ex[0]["text"] and "REDACTED" in ex[0]["text"]
