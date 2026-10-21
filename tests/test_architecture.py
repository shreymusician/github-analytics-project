import json

from repolens import architecture, profile
from repolens.llm.router import AllProvidersFailed
from repolens.narrate import ungrounded
from tests.test_analyzers import repo, sh, write  # noqa: F401
from tests.test_v1 import FakeRouter  # noqa: F401


def pk(repo):
    p = profile.analyze(str(repo))
    return p, architecture.build_packet(p)


def sid(packet, needle):
    return next(i["id"] for i in packet["items"] if needle in i["text"])


def reply(packet, **over):
    ex = sid(packet, "Source excerpt of app/core.py")
    d = {"how_it_works": [{"text": "core() returns a constant value.", "evidence": [ex]}],
         "components": [{"name": "core", "file": "app/core.py", "role": "holds the core function", "evidence": [ex]}]}
    d.update(over)
    return json.dumps(d)


def test_packet_uses_s_ids_and_fences_untrusted_source(repo):
    _, packet = pk(repo)
    assert all(i["id"].startswith("S") for i in packet["items"]) and packet["excerpt_count"] >= 1
    src = next(i for i in packet["items"] if i["text"].startswith("Source excerpt of app/core.py"))
    assert "untrusted" in src["text"] and "<<<" in src["text"] and "def core" in src["text"]


def test_valid_output_is_kept(repo):
    p, packet = pk(repo)
    out = architecture.narrate_architecture(p, FakeRouter(reply(packet)))
    a = out["architecture"]
    assert out["dropped"] == 0 and a["how_it_works"][0]["text"].startswith("core()")
    assert a["components"][0]["file"] == "app/core.py"


def test_invented_things_are_dropped_with_reasons(repo):
    p, packet = pk(repo)
    ex = sid(packet, "Source excerpt of app/core.py")
    bad = reply(packet,
                how_it_works=[{"text": "It trains a PyTorch model on 5000 samples.", "evidence": [ex]},     # invented name + number
                              {"text": "core() returns a constant value.", "evidence": ["S999"]},            # unknown citation
                              {"text": "core() returns a constant value.", "evidence": [ex]}],               # fine
                components=[{"name": "ghost", "file": "app/ghost.py", "role": "does things", "evidence": [ex]},    # file does not exist
                            {"name": "core", "file": "app/core.py", "role": "holds the function", "evidence": [sid(packet, "Languages by size")]},  # not visible in cited evidence
                            {"name": "core", "file": "app/core.py", "role": "", "evidence": [ex]}])             # incomplete
    out = architecture.narrate_architecture(p, FakeRouter(bad))
    a, why = out["architecture"], [d["why"] for d in out["dropped_detail"]]
    assert len(a["how_it_works"]) == 1 and a["components"] == []
    assert out["dropped"] == 5
    assert any("PyTorch" in w for w in why) and any("citation" in w for w in why)
    assert any("file not found" in w for w in why) and any("not visible" in w for w in why) and any("incomplete" in w for w in why)


def test_no_excerpts_means_no_model_call(tmp_path):
    sh(tmp_path, "init", "-q")
    write(tmp_path, "README.md", "# nothing to read here\n" + "x" * 600)
    sh(tmp_path, "add", "-A")
    sh(tmp_path, "commit", "-qm", "x")
    r = FakeRouter()                                   # would raise if asked
    assert architecture.narrate_architecture(profile.analyze(str(tmp_path)), r) is None and r.calls == []


def test_retry_on_bad_json_and_failure_returns_none(repo):
    p, packet = pk(repo)
    r = FakeRouter("sorry no json", reply(packet))
    assert architecture.narrate_architecture(p, r)["dropped"] == 0 and len(r.calls) == 2
    assert architecture.narrate_architecture(p, FakeRouter(AllProvidersFailed({"x": "down"}))) is None


def test_inline_s_citations_are_not_invented_numbers():
    assert ungrounded("The engine loads data (S12, S14).", "engine loads data", set()) == []
    assert ungrounded("It uses 5000 rows [S3].", "engine loads data", set()) == ["5000"]


def test_pipeline_stage_is_opt_in_cached_and_not_cached_when_empty(repo):
    from repolens.storage import Store
    from tests.test_v1 import good_reply
    p, packet = pk(repo)
    from repolens import evidence
    nar = good_reply(evidence.build_packet(p))
    store = Store(":memory:")

    off = profile.run(str(repo), store=store, router=FakeRouter(nar))              # default: no extra model call
    assert "architecture" not in off and "architecture" not in off["cache"]

    store = Store(":memory:")
    on = profile.run(str(repo), store=store, router=FakeRouter(nar, reply(packet)), architecture=True)
    assert on["cache"]["architecture"] == "miss" and on["architecture"]["architecture"]["how_it_works"]
    assert "architecture" in on["timings"]
    again = profile.run(str(repo), store=store, router=FakeRouter(), architecture=True)   # all cached: no calls at all
    assert again["cache"] == {"analysis": "hit", "narrative": "hit", "architecture": "hit"}

    store = Store(":memory:")
    empty = json.dumps({"how_it_works": [], "components": []})
    r = profile.run(str(repo), store=store, router=FakeRouter(nar, empty), architecture=True)
    assert r["architecture"]["architecture"]["how_it_works"] == []
    r2 = profile.run(str(repo), store=store, router=FakeRouter(reply(packet)), architecture=True)   # narrative cached; arch retried
    assert r2["cache"]["architecture"] == "miss" and r2["architecture"]["architecture"]["how_it_works"]
