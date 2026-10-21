# Decision log

Newest decisions last. Each entry: what, why, and what would change it.

## D1. No bulk crawling or pre-indexing of repos
**Decision:** analyze lazily on demand, cache results, store only tiny fingerprints.
**Why:** indexing GitHub is expensive (DeepWiki reportedly spent about $300K of compute on roughly 30K repos, per a secondary source) and the user wanted non-default approaches.
**Revisit if:** user demand shows a popular set of repos worth precomputing.

## D2. Six techniques combined, not one
The pipeline combines: (1) lazy analysis, (2) a live discovery agent, (3) dependency-graph search, (4) fingerprints instead of storage, (5) git-history intelligence, (6) sandbox verification of finalists. See PLAN.md.

## D3. Hybrid: custom algorithms + LLMs
**Decision:** deterministic, self-written algorithms do as much as possible; LLMs only handle what needs language (scope, summary, learning path).
**Why:** cheaper (a few thousand tokens per repo instead of whole repos), explainable, no hallucinated facts, and robust to LLM vendors changing terms.
**How:** analyzers produce an *evidence packet*; the LLM may only narrate and judge from it, citing evidence.

## D4. Not building on GitHub Copilot
**Decision:** do not make Copilot the product's agent backend.
**Why (researched Oct 2026):** GitHub App-based Copilot Extensions were shut down on 10 Nov 2025 in favor of MCP ([notice](https://github.blog/changelog/2025-09-23-deprecate-github-copilot-extensions-github-apps)). The Copilot SDK exists but is a technical preview that needs a Copilot subscription and counts against premium-request quotas (secondary sources: [overview](https://itbrief.co.uk/story/github-unveils-copilot-sdk-to-power-ai-agent-workflows)); verify against GitHub's official terms.
**Still possible:** Copilot SDK as one optional backend for a local tool running on a user's own subscription.

## D5. Bring-your-own-key (BYOK) for LLMs
**Decision:** the product asks each user for their own API keys. The developer's own keys in `.env` are for development only.
**Why:** no shared cost or rate-limit exposure, and no per-user billing risk.
**Implication:** `LLMRouter` takes keys per instance. The future web layer must hold user keys carefully (prefer client-side or short-lived server memory; never log them).

## D6. Multi-provider failover
**Decision:** a router tries providers in order (Groq, Gemini, OpenRouter, GitHub Models), benches one on 429/5xx (respecting `Retry-After`), permanently drops one on 401/403, and raises one error listing every reason (never including keys).
**Why:** free tiers change or vanish without warning (several changed in 2026).
**Notes:** all providers are called through OpenAI-compatible endpoints, so there is one code path. Default model names rot quickly (a retired Gemini model 404'd on a new account within this project's first day). Verified defaults: Groq `openai/gpt-oss-120b`, Gemini `gemini-3.1-flash-lite`. Empty replies from reasoning models count as failures (D6 bug found live). Override via `.env`; run `python -m repolens.llm.smoke` to check.

## D7. Evidence for every score
**Decision:** no unexplained numbers. Completeness and deployability scores are sums of weighted checks, each with a reason.
**Caveat:** weights are first guesses and must be calibrated on about 30 hand-labeled repos before the scores are trusted.

## D8. Partial clone, read-only
**Decision:** fetch repos with `git clone --filter=blob:none` (full history, blobs only for HEAD). Analyzers only read files; no repo code is executed during analysis. `core.symlinks=false`; symlinks are skipped when walking.
**Why:** cheap history for the history layer, and avoids GitHub API rate limits.

## D9. Narrow first: AI/ML repos, Python first
**Decision:** the taxonomy and import graph start with Python and AI/ML libraries.
**Why:** a tractable domain, and it matches the creator's own use case. JS/TS and Go graph analysis come later.

## D10. Sandbox execution is last
**Decision:** running repos in a sandbox (milestone M6) comes after everything else, and only after isolation is designed (no host mounts, no network after install, hard limits).
**Why:** it's the riskiest component (untrusted code).

## D11. Storage: SQLite now, Postgres at V4
**Decision:** a database is needed from V1 (profile cache keyed by `repo + commit SHA`), later for fingerprints (V3), jobs and permalinks (V4) and accounts/annotations (V6). Use **SQLite** through V3 and move to **Postgres** at V4 if the app becomes multi-user and hosted. All database access goes through one thin module (`repolens/storage.py`) so the move is small.
**Why SQLite first:** zero setup, native JSON, FTS5 text search, tiny data (about 1 KB per fingerprint). **Why Postgres later:** concurrent writes, JSONB, aggregation for cross-repo analytics, optional `pgvector`.
**Rejected:** vector DB (similarity uses tag overlap + MinHash, not embeddings), MongoDB (relational + JSON covers it; one DB beats two), Redis/queue (not needed before V4), graph DB (import graphs are small and computed per repo in memory).
**Never stored:** user API keys (see D5).
**Revisit if:** V3 similar-repo quality is poor (consider embeddings/`pgvector`), or V4 stays single-server low-traffic (SQLite may be enough).

## D12. V3 discovery without code search
**Decision:** candidate generation uses GitHub *repository* search (topic, language, stars, recency; 30/min); candidates are verified cheaply through ecosyste.ms manifests (declared dependencies, no clone); only finalists get full lazy analysis. GitHub *code* search (10/min) is not on the critical path.
**Why:** live tests (2026-10-21) showed repo search works well while ecosyste.ms `dependent_repositories` is broken and deps.dev returns counts only. See ECOSYSTEM.md.
**Fail-soft rule:** every outside service is optional. `repolens/external.py` returns None/[] on any failure and analysis must still work.

## D13. Citations are grounded, and repaired rather than dropped
**Decision:** names, file names and numbers (2+ digits) in a model statement must appear in the evidence packet. If they appear in the packet but not in the cited items, the citation is *repaired*; if they appear nowhere, the statement is dropped, with a reason recorded in `dropped_detail`.
**Why:** the first live run cited IDs that existed but did not support the claim. Strict "cited items only" dropped true statements (model cited the wrong ID); "any ID exists" let unsupported claims through.
**Known limits:** heuristic, not entailment. A hallucinated plain-word library name (e.g. "Django") is only caught if the analyzers found that name in the repo or it is mixed-case. Judgment errors (the model ignoring the file census) are not detectable this way; mitigated by showing the census deterministically in the report.

**D13 addendum (2026-10-21):** numbers are compared with tolerance for rounding. A round figure (whole, at least 100, multiple of 10) is grounded if some number in the cited evidence is within 10% of it ("about 1500 commits" for 1524). Non-round numbers must match exactly. Trade-off: an invented round figure near a real one passes.

## D14. Cached results are keyed by the code that produced them
**Decision:** cache kinds are `analysis.v<N>` and `narrative.v<N>` where N is `ANALYZER_VERSION` in `repolens/profile.py`. Bump it whenever analyzer output or the narration prompt changes; older entries are ignored (a miss) but not deleted.
**Why:** the cache key is repo + commit SHA, so after analyzer fixes an unchanged repo would otherwise keep serving its old, wrong profile.
**Cost:** a bump forces re-analysis and new LLM calls for every repo, so do not bump for cosmetic changes.

## D15. Checks that cannot run are "not assessed", never "passed"
**Decision:** a rule that cannot be evaluated for a repo (e.g. stub detection on TypeScript) is recorded with ok=None and weight 0, shown in the report, and excluded from the score; the profile carries `analysis_depth: full | partial`.
**Why:** a silently-passing check inflated llm-scraper's completeness to 100.

## D16. Narration reserves a modest token budget
**Decision:** `NARRATE_MAX_TOKENS = 2500`, and narrate() waits once (up to 45 s) when a provider will recover soon.
**Why:** Groq's free tier counts max_tokens against an 8,000 tokens-per-minute budget before generating, so a 4,000 reservation caused 429s even though real output is under 1,000 tokens.
**Update (later the same day):** once development testing accumulated, the binding limit became Groq's DAILY budget (200,000 tokens per day; 199,280 used), which returns 429 with a 20-minute retry hint. That is longer than the 45 s patience, so calls fall through to the next provider by design.

## D17. Verify with independent sources before asking a human
**Decision:** before asking the reviewer to grade reports, run (1) a fact-check against GitHub's own data using separate, simple logic, and (2) a second-model audit of every claim, with a planted-falsehood control to show the judge is not simply approving everything. Ask the human only for what machines cannot judge: whether a report is useful.
**Why:** the human is the scarce resource, and the audit already found real defects (guessed audiences, reading-list reasons inferred from file names).
**Honest limits:** the facts are easy and the rules are simple on both sides; the judge sees the same evidence the narrator saw; four planted claims show sensitivity to obvious errors only. None of this answers "is it insightful".
**Related:** judge independence is recorded per audit (narrator and judge are different providers when possible); a self-graded audit is flagged, not hidden.

## D18. Gate A human review waived by the owner (2026-10-21)
**Decision (owner's):** skip the manual review of the ten Gate A reports and continue building on machine verification only.
**What is verified:** facts against GitHub (78 of 80), every claim audited by a second model (102 of 103 supported; judge checked with planted falsehoods), a first DeepWiki comparison. See D17 and docs/GATE_A.md.
**What is NOT verified, and this is the accepted risk:** that a real person finds the reports insightful and the scores about right. Gate A is therefore recorded as "machine-verified, human-unverified", NOT "passed". Scores stay uncalibrated; the labels file (data/labels/gate_a.csv) stays empty on the human side.
**Consequences:** V2 score calibration has no human labels yet, so score weights remain first guesses and should be presented as such; a cheap automated proxy for usefulness is worth building (see ROADMAP/STATUS); any user-facing launch should be treated as an experiment that gathers real feedback, not a proven product.
**Revisit:** whenever the owner (or any early user) is willing to spend 10 minutes tapping useful/meh/wrong on a few reports.

## D19. A separate, cited "how it works" stage
**Decision:** explaining how the code works is its own LLM stage (`repolens/architecture.py`), not a few more sentences in the main narration. It reads up to 6 source excerpts in any language, uses its own evidence IDs (S1, S2...), applies the shared grounding rules, additionally requires each named component to exist as a file and be visible in the evidence it cites, and prefers Gemini (longer context; leaves Groq's budget to the narration). It is opt-in in `run(architecture=True)`, cached per commit, and not cached when empty.
**Why:** the DeepWiki comparison showed this is where we are weakest, and the import graph gives nothing for non-Python repos; reading source directly works for any language.
**Known limits:** quality depends on which files are shown. chonkie's report explains the API and CLI but misses the chunkers, because the picker favors well-imported glue files. Cited does not mean complete.
**Next:** pick files by directory/role (for example the package's largest, most-changed or most-named modules), not only by import counts.

## Open questions
- Product vs. hackathon/college project? (changes polish and scope)
- Local tool vs. hosted service? (affects sandbox design and key handling)
- Backend stack: Python/FastAPI assumed; unconfirmed.
- Frontend form: paste-a-URL page vs. browser extension vs. chat UI.
