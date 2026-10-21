"""LLM router with automatic failover across providers.

Keys are supplied per instance (BYOK): the web layer builds a router from the
requesting user's keys. `keys_from_env()` is the developer fallback only.
Keys are never logged or included in exceptions.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from .providers import PROVIDERS, Provider

DEFAULT_COOLDOWN = 60.0   # seconds to bench a provider after a rate limit with no Retry-After
SERVER_ERROR_COOLDOWN = 15.0   # 5xx ("model overloaded", 503) is usually momentary: retry sooner than a rate limit
MAX_COOLDOWN = 3600.0


class AllProvidersFailed(RuntimeError):
    """Raised when every configured provider failed. `errors` maps provider -> reason."""

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        detail = "; ".join(f"{k}: {v}" for k, v in errors.items()) or "no providers configured"
        super().__init__(f"All LLM providers failed ({detail})")


@dataclass
class _State:
    cooldown_until: float = 0.0
    dead: bool = False  # bad key (401/403): don't retry this provider


def keys_from_env() -> dict[str, str]:
    from dotenv import load_dotenv
    load_dotenv()
    return {n: os.environ[p.key_env] for n, p in PROVIDERS.items() if os.environ.get(p.key_env)}


@dataclass
class LLMRouter:
    keys: dict[str, str]                      # provider name -> API key
    order: list[str] | None = None            # preference order; defaults to registry order
    timeout: float = 60.0
    client: httpx.Client | None = None        # injectable for tests
    clock: Callable[[], float] = time.monotonic
    _state: dict[str, _State] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        names = self.order or list(PROVIDERS)
        self.order = [n for n in names if n in PROVIDERS and self.keys.get(n)]
        self._state = {n: _State() for n in self.order}
        self.client = self.client or httpx.Client(timeout=self.timeout)

    def ask(self, messages: list[dict], *, prefer: str | None = None,
            temperature: float = 0.2, max_tokens: int = 1500,
            json_mode: bool = False) -> tuple[str, str]:
        """Return (text, provider_name). `prefer` tries one provider first."""
        order = self.order[:]
        if prefer in order:
            order.remove(prefer)
            order.insert(0, prefer)

        errors: dict[str, str] = {}
        now = self.clock()
        for name in order:
            st = self._state[name]
            if st.dead:
                errors[name] = "invalid key"
                continue
            if now < st.cooldown_until:
                errors[name] = f"cooling down {st.cooldown_until - now:.0f}s"
                continue
            try:
                return self._call(PROVIDERS[name], messages, temperature, max_tokens, json_mode), name
            except _Skip as e:
                errors[name] = e.reason
        raise AllProvidersFailed(errors)

    def soonest_available(self) -> float | None:
        """Seconds until some non-dead provider leaves cooldown (0 if one is ready now); None if none will."""
        now = self.clock()
        waits = [max(0.0, st.cooldown_until - now) for st in self._state.values() if not st.dead]
        return min(waits) if waits else None

    def _call(self, p: Provider, messages, temperature, max_tokens, json_mode) -> str:
        body = {"model": p.model(), "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens, **p.extra_params()}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        st = self._state[p.name]
        try:
            r = self.client.post(f"{p.base_url}/chat/completions", json=body,
                                 headers={"Authorization": f"Bearer {self.keys[p.name]}"})
        except httpx.HTTPError as e:
            st.cooldown_until = self.clock() + DEFAULT_COOLDOWN
            raise _Skip(f"network error ({type(e).__name__})")

        if r.status_code in (401, 403):
            st.dead = True
            raise _Skip(f"auth failed ({r.status_code})")
        if r.status_code == 429 or r.status_code >= 500:
            default = SERVER_ERROR_COOLDOWN if r.status_code >= 500 else DEFAULT_COOLDOWN
            st.cooldown_until = self.clock() + _retry_after(r, default)
            raise _Skip(f"HTTP {r.status_code}")
        if r.status_code >= 400:
            # e.g. model removed or bad request: skip this call, don't bench the provider
            raise _Skip(f"HTTP {r.status_code}")
        try:
            choice = r.json()["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise _Skip("malformed response")
        if not isinstance(content, str) or not content.strip():
            # typically a reasoning model that used its whole token budget thinking
            raise _Skip(f"empty reply (finish_reason={choice.get('finish_reason')})")
        return content


class _Skip(Exception):
    def __init__(self, reason: str):
        self.reason = reason


def _retry_after(r: httpx.Response, default: float = DEFAULT_COOLDOWN) -> float:
    try:
        return min(max(float(r.headers.get("retry-after", default)), 1.0), MAX_COOLDOWN)
    except ValueError:
        return default
