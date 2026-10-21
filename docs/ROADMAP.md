# Roadmap: V0 to V6

Each version is a **shippable slice with an exit test**, not a list of tasks. Do not start version N+1 until version N's exit test passes. Targets marked *(proposed)* are starting points to tune, not measured facts.

Sizes are relative effort for one developer working with Claude: **S** = a day or two, **M** = about a week, **L** = two weeks or more. Dates are deliberately absent because the deadline and team are unknown (see "Open questions").

```
V0 Foundation ──> V1 Single-Repo Brain ──> V2 Trust ──> V3 Find ──> V4 Use ──> V5 Prove ──> V6 Society
   (done)          CLI, end to end        calibrated    discovery    web app    sandbox      community
                        |                                              |
                  GATE A: is the output                         GATE B: do real people
                  genuinely insightful?                         come back and use it?
```

---

## V0: Foundation (done)

**Goal:** prove the custom-algorithm approach works and lay the groundwork.

**Delivered**
- Analyzers: stack detection, Python import graph with PageRank and subsystem detection, git-history intelligence, completeness/deployability rules engine.
- Multi-provider LLM router with failover (mocked-HTTP tested).
- CLI: `python -m repolens <source>`. 14 passing tests. Docs (README, VISION, DECISIONS, PLAN, STATUS).

**Known gaps carried forward:** no LLM narration, GitHub cloning untested, scoring weights uncalibrated, Python only.

---

## V1: Single-Repo Brain (size M)

**Goal:** give any public Python AI/ML repo URL, get a trustworthy, readable report. First time the whole idea is visible end to end.

| # | Deliverable | Notes |
|---|---|---|
| 1.1 | Provider smoke test | Run a real call against each configured provider; record which work, with which model names. Keys from `.env` only. |
| 1.2 | Verify GitHub clone path | Clone one small public repo (with the owner's explicit OK to download). Fix what breaks. |
| 1.3 | **Evidence packet builder** | Compress analyzer output to a few thousand tokens: stack, core files with short excerpts, README head, history story, rule results. |
| 1.4 | **LLM narration** | Produce: what it is (scope), how far along it is, how to run it, who it's for, the "read first" learning path. Every claim cites an evidence ID; unsupported claims are dropped. Structured JSON output, validated. |
| 1.5 | Cache by `repo + commit SHA` | SQLite. Same SHA means no re-analysis and no tokens. |
| 1.6 | Report renderer | Markdown and JSON report: summary, scores with reasons, architecture map, learning path. |
| 1.7 | Graceful degradation | If every provider fails, still output the analyzer-only report (it is already useful). |

**Exit test (Gate A):** on 10 varied public AI/ML repos, a human reader says the report told them something the README did not, and no cited claim is false. Analysis completes in under 60 seconds and under about 15K tokens per repo *(proposed)*.

**Risks:** LLM invents facts, so enforce evidence citations and validate. Free-tier token caps, so keep packets small.

**Decision at Gate A:** if the reports are not insightful, fix the approach before building anything else. This is the cheapest point to change direction.

---

## V2: Trust (size M to L)

**Goal:** make the scores believable, and support more than Python.

| # | Deliverable | Notes |
|---|---|---|
| 2.1 | **Labeled calibration set** | Hand-label 30 to 50 repos: complete or not, deployable or not, abandoned or not, difficulty. Store as data in the repo. |
| 2.2 | Weight calibration | Tune rule weights against the labels; report agreement per signal. Consider a small logistic model *(your own algorithm)* if hand-tuning plateaus. |
| 2.3 | Confidence levels | Scores come with high/medium/low confidence and say what was not checked. |
| 2.4 | JS/TS import graph | Parse imports for JavaScript/TypeScript (and `package.json` entry points). Go and Rust later. |
| 2.5 | Notebook support | Many AI/ML repos are Jupyter-first: extract cells, imports and outputs. |
| 2.6 | Richer taxonomy | Expand the AI/ML library taxonomy; add pattern detectors (RAG pipeline, training loop, fine-tuning, agent loop). |
| 2.7 | Regression suite | Frozen expected outputs for the labeled repos; any change that moves scores must be deliberate. |

**Exit test:** completeness/deployability verdicts agree with the human labels at least 80% of the time *(proposed)* on repos not used for tuning, and the README claims the numbers.

**Risks:** label bias (one labeler), overfitting the small set. Hold out 10 repos untouched.

---

## V3: Find (size L)

**Goal:** from a goal in plain words to a ranked list of worthwhile repos.

| # | Deliverable | Notes |
|---|---|---|
| 3.1 | **Candidate search + cheap stack verification** | GitHub repo search (topic/language/stars/recency, 30/min) for candidates, then ecosyste.ms manifests to confirm "uses chromadb + fastapi" without cloning (see DECISIONS D12). `External.search_repos` and `manifest_dependencies` already exist and are live-tested. Code search is a fallback only. |
| 3.2 | Goal understanding | Map a free-text goal to taxonomy tags and queries (LLM plus the hand-built taxonomy as a guardrail). |
| 3.3 | **Discovery agent** | Tool-using agent: search repos, read READMEs and trees, shortlist; hard budgets on calls and tokens. |
| 3.4 | Fingerprint store | About 1 KB per analyzed repo: tags, structure hash, maturity, SHA. Similar-repo lookup via tag overlap and MinHash on structure *(own algorithms)*. |
| 3.5 | **Ranking for learning** | Score = relevance x completeness x readability x recency, tuned for "how much can I learn from this", not stars. |
| 3.6 | Learning-path generator | Sequence the top picks from simplest to most advanced, with what to read first in each. |

**Exit test:** for 10 realistic goals, a human judges the top 5 results better than a GitHub search for the same goal, at least 7 times out of 10 *(proposed)*.

**Risks:** GitHub rate limits shape everything. Cold start for similar-repo lookup (fingerprints grow with use). Search quality depends on query expansion.

---

## V4: Use (size L). First public version

**Goal:** a real person, not a developer, can use it without a terminal.

| # | Deliverable | Notes |
|---|---|---|
| 4.1 | API layer | FastAPI: analyze, search, report endpoints; background jobs for slow analysis. |
| 4.2 | **BYOK key handling** | Users paste their own provider keys; keep them client-side or in short-lived server memory; never logged or stored in plaintext; clear explanation of what is sent where. |
| 4.3 | Web UI | Two flows: paste a repo URL for a report; describe a goal for a guided list. Evidence shown inline, with "why this score". |
| 4.4 | Shareable report pages | Permalink per `repo + SHA`. |
| 4.5 | Onboarding | First run: get a GitHub token and one LLM key in under 5 minutes. |
| 4.6 | Basic ops | Rate limiting, error reporting, usage counts that contain no keys or private data. |
| 4.7 | Private beta | 10 to 20 learners from AI/ML communities. Watch them use it. |

**Exit test (Gate B):** at least 40% of beta users return within a week *(proposed)*, and users can name a repo they would not have found otherwise.

**Decision at Gate B:** if people do not come back, stop adding features. Revisit the audience, the entry point (browser extension?) or the value.

**Risks:** BYOK friction (many people will not bring keys), so consider a clearly-labeled small free quota. Security of key handling. Distribution, which is the hardest part.

---

## V5: Prove (size L)

**Goal:** turn "probably deployable" into "we ran it and it started".

| # | Deliverable | Notes |
|---|---|---|
| 5.1 | **Security design first** | Threat model for running untrusted code: no host mounts, no network after install, CPU/memory/time/disk limits, ephemeral. Reviewed before any code. |
| 5.2 | Run-recipe detection | Derive build and start commands from Dockerfile, Makefile, README, manifests. |
| 5.3 | Sandboxed build + start | Container isolation (gVisor/Firecracker-class for hosting). Health-check and capture logs. |
| 5.4 | Results in the profile | `builds`, `starts`, failure reason, time taken, shown as hard evidence. |
| 5.5 | Run only for finalists | Never for every search result. |

**Exit test:** on the labeled set, sandbox results match known-runnable repos (at least 90% of known-good build; known-broken fail for the right reason).

**Risks:** the biggest security surface in the project. If hosting it safely is not feasible, offer it as a local-only feature instead.

---

## V6: Society (size L, open-ended)

**Goal:** the "society-based" layer from the original idea: knowledge that compounds across users.

| # | Deliverable | Notes |
|---|---|---|
| 6.1 | Accounts and saved lists | Collections of repos, learning progress. |
| 6.2 | **Community annotations** | "I ran this; step 4 is broken", "good for beginners". Verified by use, tied to a commit SHA, with moderation. |
| 6.3 | Cross-repo analytics | "How do 20 projects handle RAG chunking?" Aggregations over fingerprints and patterns. |
| 6.4 | Compare view | Side-by-side of repos solving the same problem. |
| 6.5 | Trends | What the ecosystem is converging on, what is dying. |

**Exit test:** a meaningful share of reports have at least one community contribution, and cross-repo views are used.

**Risks:** moderation and spam. Needs critical mass, so it only makes sense after V4 has real users.

---

## Beyond V6 (ideas, unscheduled)

- Browser extension overlaying the analysis on github.com (also a possible early entry point, see Gate B).
- More languages (Go, Rust, Java); non-AI/ML domains.
- Private-repo analysis for teams.
- IDE integration ("find a reference implementation for what I'm writing").
- Optional local-model mode and optional Copilot-SDK backend (see DECISIONS D4).
- An open dataset of structured repo profiles, if licensing allows.

---

## Critical path and shortcuts

**Critical path:** V1 -> V2 (calibration) -> V3 -> V4. V5 and V6 branch off V4 and can swap order.

**If time is short (hackathon or college demo):** V0 -> V1 -> thin V3 (dependency search plus ranked list for one niche) -> minimal V4 (single page). Skip V2's JS/TS and V5 entirely; show the evidence-backed reports, the graph "read first" view and the learning path. This is a believable demo in a few weeks of work.

**If this is a real product:** do not skip V2. Untrusted scores are the fastest way to lose users.

## Open questions that change this roadmap

1. **Hackathon/college project or a real product?** Decides the shortcut above.
2. **Local tool or hosted service?** Moves BYOK handling, sandbox safety and costs.
3. **Backend stack:** Python assumed; the frontend form (page, extension, chat) is undecided.
4. **Deadline and team size.** Needed to put dates on this.
