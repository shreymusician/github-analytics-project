"""Provider registry. All providers expose an OpenAI-compatible chat endpoint,
so the router needs a single code path. Model names are defaults only; free-tier
model lineups change often, so each can be overridden via env or per request."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    default_model: str
    model_env: str
    key_env: str

    def model(self) -> str:
        return os.environ.get(self.model_env, self.default_model)

    def extra_params(self) -> dict:
        """Provider/model-specific request tweaks. gpt-oss models are reasoning models that
        spend completion tokens thinking (an empty reply if the budget is small), so ask for
        low reasoning effort."""
        if self.name == "groq" and self.model().startswith("openai/gpt-oss"):
            return {"reasoning_effort": "low"}
        return {}


# Order = default preference: fast first, long-context next, broad fallback last.
PROVIDERS: dict[str, Provider] = {
    p.name: p
    for p in (
        Provider("groq", "https://api.groq.com/openai/v1",
                 "openai/gpt-oss-120b", "GROQ_MODEL", "GROQ_API_KEY"),
        Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
                 "gemini-3.5-flash-lite", "GEMINI_MODEL", "GEMINI_API_KEY"),
        Provider("openrouter", "https://openrouter.ai/api/v1",
                 "cohere/north-mini-code:free", "OPENROUTER_MODEL", "OPENROUTER_API_KEY"),
        Provider("github", "https://models.github.ai/inference",
                 "openai/gpt-4.1-mini", "GITHUB_MODELS_MODEL", "GITHUB_MODELS_TOKEN"),
    )
}
