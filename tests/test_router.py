import httpx
import pytest

from repolens.llm.router import AllProvidersFailed, LLMRouter

OK = {"choices": [{"message": {"content": "hi"}}]}


def make(handler, keys=None, clock=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    kw = {"clock": clock} if clock else {}
    return LLMRouter(keys=keys or {"groq": "k1", "gemini": "k2", "openrouter": "k3"}, client=client, **kw)


def host(req):
    return req.url.host


def test_first_provider_used():
    r = make(lambda req: httpx.Response(200, json=OK))
    assert r.ask([{"role": "user", "content": "x"}]) == ("hi", "groq")


def test_failover_on_429_then_cooldown_skips_provider():
    calls = []

    def handler(req):
        calls.append(host(req))
        if "groq" in host(req):
            return httpx.Response(429, headers={"retry-after": "30"})
        return httpx.Response(200, json=OK)

    t = [0.0]
    r = make(handler, clock=lambda: t[0])
    assert r.ask([])[1] == "gemini"
    calls.clear()
    assert r.ask([])[1] == "gemini"          # groq still benched, not retried
    assert not any("groq" in c for c in calls)
    t[0] = 31
    r.ask([])                                 # cooldown over, groq tried again
    assert "api.groq.com" in calls


def test_bad_key_is_permanently_skipped():
    def handler(req):
        return httpx.Response(401) if "groq" in host(req) else httpx.Response(200, json=OK)

    r = make(handler)
    assert r.ask([])[1] == "gemini"
    assert r._state["groq"].dead


def test_all_fail_raises_with_reasons_and_no_keys_leaked():
    r = make(lambda req: httpx.Response(500))
    with pytest.raises(AllProvidersFailed) as e:
        r.ask([])
    assert set(e.value.errors) == {"groq", "gemini", "openrouter"}
    assert "k1" not in str(e.value)


def test_prefer_and_missing_keys():
    r = make(lambda req: httpx.Response(200, json=OK), keys={"gemini": "k"})
    assert r.order == ["gemini"]
    r = make(lambda req: httpx.Response(200, json=OK))
    assert r.ask([], prefer="openrouter")[1] == "openrouter"


def test_malformed_body_falls_through():
    def handler(req):
        return httpx.Response(200, json={}) if "groq" in host(req) else httpx.Response(200, json=OK)

    assert make(handler).ask([])[1] == "gemini"


def test_no_keys_raises():
    with pytest.raises(AllProvidersFailed):
        LLMRouter(keys={}).ask([])


def test_empty_reply_is_failure_not_success():
    empty = {"choices": [{"finish_reason": "length", "message": {"content": ""}}]}

    def handler(req):
        return httpx.Response(200, json=empty) if "groq" in host(req) else httpx.Response(200, json=OK)

    r = make(handler)
    assert r.ask([])[1] == "gemini"                      # fell through instead of returning ""
    assert not r._state["groq"].dead and r._state["groq"].cooldown_until == 0   # not benched: may succeed next time


def test_groq_gpt_oss_gets_low_reasoning_effort():
    seen = {}

    def handler(req):
        import json as j
        seen.update(j.loads(req.content))
        return httpx.Response(200, json=OK)

    make(handler).ask([])
    assert seen["reasoning_effort"] == "low"
