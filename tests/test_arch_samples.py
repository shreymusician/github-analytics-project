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


def test_core_directory_is_covered_even_when_glue_files_dominate_the_import_graph(tmp_path):
    """chonkie-style layout: the import graph's favourites are glue (__init__, cli helpers); the real work lives in
    chunker/. The picker must still show something from the heaviest directories and from the most-changed files."""
    write(tmp_path, "src/pkg/__init__.py", "from .cli import run\n" * 10)
    write(tmp_path, "src/pkg/cli.py", "def run():\n    pass\n" * 5)
    write(tmp_path, "src/pkg/api/main.py", "app = 1\n" * 20)
    write(tmp_path, "src/pkg/chunker/recursive.py", "def split(text):\n    return text.split()\n" * 200)   # the core, big
    write(tmp_path, "src/pkg/chunker/token.py", "def tokens(text):\n    return list(text)\n" * 50)
    write(tmp_path, "src/pkg/embeddings/openai.py", "def embed():\n    pass\n" * 10)
    files = ["src/pkg/__init__.py", "src/pkg/cli.py", "src/pkg/api/main.py", "src/pkg/chunker/recursive.py",
             "src/pkg/chunker/token.py", "src/pkg/embeddings/openai.py"]
    st = {"path_index": files, "notable_files": stack.notable_files(files)}
    glue_only = {"read_first": [{"file": "src/pkg/__init__.py"}, {"file": "src/pkg/cli.py"}]}

    without_history = profile.pick_arch_files(tmp_path, st, glue_only)
    assert "src/pkg/chunker/recursive.py" in without_history          # heaviest directory is covered via its biggest file

    hot = {"hotspots": [{"file": "src/pkg/chunker/token.py", "changes": 40}, {"file": "README.md", "changes": 30}]}
    with_history = profile.pick_arch_files(tmp_path, st, glue_only, hot)
    assert with_history[:3] == ["src/pkg/__init__.py", "src/pkg/cli.py", "src/pkg/chunker/token.py"]   # graph picks, then the hotspot
    assert "README.md" not in with_history and len(set(with_history)) == len(with_history)


def test_missing_or_nonexistent_hotspots_are_ignored(tmp_path):
    write(tmp_path, "a.py", "x = 1\n" * 30)
    st = {"path_index": ["a.py"], "notable_files": ["a.py"]}
    got = profile.pick_arch_files(tmp_path, st, {"read_first": []}, {"hotspots": [{"file": "deleted_long_ago.py", "changes": 99}]})
    assert got == ["a.py"]
