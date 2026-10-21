"""Scrub secrets from repo text before it is sent to a third-party LLM.

Repos sometimes contain committed keys. Anything sent to a provider leaves the
machine, so redact first. Patterns are best-effort, not a guarantee.
"""
from __future__ import annotations

import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
]
_ASSIGN = re.compile(r"""(?ix)((?:api[_-]?key|secret|token|passw(?:or)?d|auth)\w*\s*[:=]\s*)(['"]?)[^\s'"]{8,}\2""")


def redact(text: str) -> str:
    for p in _PATTERNS:
        text = p.sub("[REDACTED]", text)
    return _ASSIGN.sub(r"\1[REDACTED]", text)
