# Status

Last updated: 2026-10-21 (V1 in progress)

## Built and tested (42 tests passing)

| Component | File | Notes |
|---|---|---|
| LLM router with failover | `repolens/llm/router.py`, `providers.py` | 7 tests, mocked HTTP only. **Never called a real provider yet.** |
| Repo fetch | `repolens/fetch.py` | Local paths tested. **GitHub URL cloning is written but untested.** |
| Stack detection | `repolens/stack.py` | requirements, pyproject, package.json, go.mod, Cargo; AI/ML taxonomy |
| Import graph + PageRank + subsystems | `repolens/graph.py` | Python only |
| Git-history analysis | `repolens/history.py` | Optional: degrades to `no-git-history` outside a git repo |
| Completeness / deployability rules | `repolens/signals.py` | Weights uncalibrated |
| Pipeline + SHA cache | `repolens/profile.py`, `storage.py` | SQLite cache by repo+commit SHA (D11); unchanged repos cost no analysis or tokens |
| Secret redaction | `repolens/redact.py` | README/code excerpts are scrubbed before leaving the machine |
| Evidence packet | `repolens/evidence.py` | Numbered facts (E1, E2...); untrusted repo text is fenced |
| LLM narration | `repolens/narrate.py` | Citation-enforced: uncited/unknown-ID statements and invented files are dropped; one JSON retry; returns None on failure |
| Report renderer | `repolens/report.py` | Markdown with scores, reasons, read-first, citations; works without the LLM |
| CLI | `repolens/cli.py` | `python -m repolens <source> [--md f] [--json f] [--no-llm] [--no-cache]` |
| File-type census | `repolens/stack.py` | Composition by category (code/slides/docs/media/data...); shown deterministically in the report |
| Third-party import detection | `repolens/graph.py` | Works without any manifest; alias map (PIL -> Pillow); import-derived capability tags |
| External signals (fail-soft) | `repolens/external.py` | GitHub facts (+ ecosyste.ms fallback), OpenSSF Scorecard, repo search and manifest deps (V3 helpers). Live-tested; `--offline` skips |
| Citation grounding | `repolens/narrate.py` | Names/files/numbers must exist in the packet; wrong citations repaired, unsupported statements dropped with reasons (D13) |
| Provider smoke test | `repolens/llm/smoke.py` | `python -m repolens.llm.smoke` (needs keys; **not yet run**) |

## V1 checklist (see ROADMAP.md)
- [~] 1.1 Provider smoke test: **Groq OK** (`openai/gpt-oss-120b`), **Gemini OK** (`gemini-3.1-flash-lite`). **Real failover verified** (invalid Groq key -> marked dead -> Gemini answered). Gemini produced valid cited narration JSON in 2.3s. OpenRouter and GitHub Models untested (no keys).
- [ ] 1.2 Verify GitHub clone path: **waiting on permission to download a public repo**
- [x] 1.3 Evidence packet builder
- [x] 1.4 LLM narration with enforced citations. Ran once against real Groq on a local project; see findings below.
- [x] 1.5 Cache by repo + commit SHA
- [x] 1.6 Report renderer
- [x] 1.7 Graceful degradation (no keys / all providers fail -> deterministic report)
- [ ] Gate A exit test: 10 varied public AI/ML repos, human-judged. Needs 1.1 and 1.2 first.

Tests use synthetic repos created on the fly (no network). One real-world run was done on a local project (`mini_proj`, a presentation project): the scores and reasons were sensible, and the run surfaced two bugs, now fixed (non-git folders crashed the analyzer; a package named `app` was flagged as an entry point).

## First real-model run: findings (2026-10-21, Groq gpt-oss-120b, local `mini_proj`)
- Output was valid JSON, nothing dropped, all citations resolve to real evidence IDs. Latency a few seconds.
- **Bug found and fixed:** gpt-oss is a reasoning model; with a small `max_tokens` it returned an *empty* reply that the router treated as success. Now an empty reply counts as a failure and falls through to the next provider; Groq gpt-oss gets `reasoning_effort: low`; narration budget raised to 4000 tokens.
- **(Addressed by D13, see below)** The citation check originally verified only that cited IDs *exist*, not that they *support* the claim. Example: "uses Pillow and NumPy" cited E1/E3/E4, none of which mention those libraries (the truth was only in the source excerpt, E24). Planned: stricter checks (e.g. require named libraries/numbers to appear in cited evidence text) and an LLM-free entailment heuristic.
- **Analyzer blind spot:** `mini_proj` is mostly presentation files (.pptx/.pdf), but the language census only counts code, so the model described it as "a single-file animation script". Planned: a file-type census (all extensions, by size and count) in the evidence packet.
- Only one repo has been tried; this is an anecdote, not a Gate A result.

## GitHub token (verified 2026-10-21)
Fine-grained, public-read-only token works: 5,000 core requests/hour, **search 30/min**, **code search only 10/min**. Code search is the tight one: V3's dependency-graph search (3.1) must batch, cache and back off, not fire a query per candidate. Not used by V1 (clones use plain `git`).

## Model-name rot (real example)
`gemini-2.5-flash` returned 404 for a new account ("no longer available to new users"). The `gemini-flash-latest` alias timed out (>90s), `gemini-3.8-flash` took 65s, `gemini-3.1-flash-lite` took 4s. Latency on free tiers varies widely. Defaults are verified only on the date above: expect to re-check with `python -m repolens.llm.smoke`, and override via `GEMINI_MODEL` / `GROQ_MODEL` in `.env`.

## Second live run (same day): what changed
- After adding the census, import evidence and grounding, two real Groq runs on `mini_proj` dropped 0 statements and traced library claims to the import evidence. The report now opens with "dominated by presentation slides (85%)" instead of "a single-file animation script".
- The first grounding version dropped a true statement because the model cited the wrong ID; fixed by repairing citations (D13).
- Not yet run: the GitHub clone path, the external signals inside a full `run()` on a real GitHub repo, and Gemini narration after the grounding change (Gemini was tested before it).

## Known limitations
- Scoring weights are first guesses. Need calibration on about 30 hand-labeled repos.
- Import graph is Python only; no JS/TS/Go.
- LLM narration is built but has **never run against a real model**; prompt quality is unverified.
- No discovery, dependency-search or fingerprint store yet.
- No sandbox. No web UI.
- Stub detection covers Python only; TODO density is Python only.
- No real provider call has been made; default model names may not exist on a given account.
- Taxonomy is small and hand-built.

## Next steps (in order)
1. Add the file-type census to the evidence packet and tighten citation checks (see findings). Add Gemini key; test failover for real.
2. Test GitHub URL cloning on one public repo (requires the user's OK to download it).
3. Pick 10 varied AI/ML repos for the Gate A review.
4. Extend the graph analysis to JS/TS.
5. Hand-label about 30 repos and calibrate the scoring weights.
6. Dependency-graph search, then the discovery agent (M3, M4 in PLAN.md).
7. Fingerprint store, then the sandbox, then the web UI.

## Free API notes (researched 2026-10-21, secondary sources, verify before relying)
- GitHub token: 5,000 REST requests/hour authenticated ([docs](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)). Essential.
- Groq: about 30 requests/min, 1,000/day, with roughly 200K tokens/day as the usual binding limit.
- Gemini Flash: free; sources disagree on daily limits; check AI Studio. Free-tier content may be used by Google.
- OpenRouter: free models about 20/min and 50/day; $10 credit lifts the daily cap to about 1,000.
- GitHub Models: free but rate-limited with small token caps; one site lists it as discontinued, which contradicts GitHub's docs. Verify.
- Cerebras and Mistral: unclear or restrictive terms; skipped.
