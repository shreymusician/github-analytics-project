import json

from repolens import audit, evidence, profile
from repolens.llm.router import AllProvidersFailed
from tests.test_analyzers import repo, sh, write  # noqa: F401
from tests.test_v1 import FakeRouter, find, good_reply  # noqa: F401
from repolens.narrate import narrate


class JudgeRouter(FakeRouter):
    """FakeRouter that also exposes provider order and records the `prefer` it was given."""
    order = ["groq", "gemini"]

    def ask(self, messages, **kw):
        self.kw = kw
        return super().ask(messages, **kw)


def setup(repo):
    pk = evidence.build_packet(profile.analyze(str(repo)))
    nar = narrate(pk, FakeRouter(good_reply(pk)))
    nar["provider"] = "groq"
    return pk, nar


def verdict_reply(nar, overrides=None, drop=()):
    overrides = overrides or {}
    vs = [{"id": c["id"], "verdict": overrides.get(c["id"], "supported"), "reason": "ok"}
          for c in audit.claims_of(nar["narrative"]) if c["id"] not in drop]
    return json.dumps({"verdicts": vs})


def test_claims_are_flattened_with_ids(repo):
    pk, nar = setup(repo)
    ids = [c["id"] for c in audit.claims_of(nar["narrative"])]
    assert ids[:4] == ["summary", "scope", "audience", "maturity"]
    assert "how_to_run.0" in ids and "learning_path.0" in ids and "caveats.0" in ids
    lp = next(c for c in audit.claims_of(nar["narrative"]) if c["id"] == "learning_path.0")
    assert lp["text"].startswith("Read app/core.py:")


def test_judge_is_a_different_provider_and_counts_are_reported(repo):
    pk, nar = setup(repo)
    r = JudgeRouter(verdict_reply(nar, {"scope": "unsupported", "audience": "contradicted", "maturity": "partly"}))
    out = audit.audit(pk, nar, r)
    assert r.kw["prefer"] == "gemini"                                  # narrator was groq, so ask gemini
    assert out["judge"] == "fake" and out["independent"] is True        # fake router reports provider 'fake' != groq
    assert out["counts"]["unsupported"] == 1 and out["counts"]["contradicted"] == 1 and out["counts"]["partly"] == 1
    assert [p["id"] for p in out["problems"]] == ["scope", "audience"]


def test_not_independent_when_only_the_narrator_answered(repo):
    pk, nar = setup(repo)

    class SameProvider(JudgeRouter):
        def ask(self, messages, **kw):
            text, _ = super().ask(messages, **kw)
            return text, "groq"
    out = audit.audit(pk, nar, SameProvider(verdict_reply(nar)))
    assert out["independent"] is False and out["judge"] == "groq"


def test_missing_invalid_and_unknown_verdicts(repo):
    pk, nar = setup(repo)
    reply = json.dumps({"verdicts": [
        {"id": "summary", "verdict": "supported", "reason": "ok"},
        {"id": "summary", "verdict": "contradicted", "reason": "duplicate ignored"},
        {"id": "scope", "verdict": "mostly fine", "reason": "invalid word"},
        {"id": "made_up", "verdict": "supported", "reason": "unknown id"}]})
    out = audit.audit(pk, nar, JudgeRouter(reply))
    by = {v["id"]: v["verdict"] for v in out["verdicts"]}
    assert by["summary"] == "supported"                                 # first verdict wins
    assert by["scope"] == "unjudged" and by["audience"] == "unjudged"   # invalid or absent: never silently "supported"
    assert "made_up" not in by and out["problems"] == []


def test_failures_return_none_and_empty_narration_is_trivial(repo):
    pk, nar = setup(repo)
    assert audit.audit(pk, nar, JudgeRouter(AllProvidersFailed({"gemini": "HTTP 503"}))) is None
    assert audit.audit(pk, nar, JudgeRouter("not json at all")) is None
    empty = {"narrative": {"summary": None, "scope": None, "audience": None, "maturity": None,
                           "how_to_run": [], "learning_path": [], "caveats": []}, "provider": "groq"}
    assert audit.audit(pk, empty, JudgeRouter())["claims"] == 0         # nothing to judge, no model call
