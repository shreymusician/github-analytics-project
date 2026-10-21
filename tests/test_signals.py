"""Rules-engine fixes found by the Gate A run: what counts as a test, what counts as a stub."""
from repolens import signals
from tests.test_analyzers import write  # noqa: F401


def test_only_real_tests_count(tmp_path):
    write(tmp_path, "test_simple.py", "import sys\nprint('demo script')\n")                 # monodepth2-style demo
    write(tmp_path, "tests/fixture.json", "{}")                                                # data in tests/
    write(tmp_path, "tests/test_ok.py", "def test_a():\n    assert True\n")
    write(tmp_path, "web/a.test.ts", "describe('x', () => { it('y', () => { expect(1).toBe(1) }) })\n")
    paths = ["test_simple.py", "tests/fixture.json", "tests/test_ok.py", "web/a.test.ts"]
    assert signals.confirmed_tests(tmp_path, paths) == ["tests/test_ok.py", "web/a.test.ts"]


def test_abstract_and_protocol_methods_are_not_stubs(tmp_path):
    write(tmp_path, "a.py", (
        "from abc import ABC, abstractmethod\nfrom typing import Protocol\n"
        "class A(ABC):\n    @abstractmethod\n    def f(self):\n        pass\n"
        "class P(Protocol):\n    def g(self): ...\n"
        "def todo():\n    pass\n"))
    r = signals._scan_python(tmp_path, ["a.py"])
    assert r["functions"] == 1 and r["stubs"] == 1          # only the real stub counts
