# GitHub Intelligence Platform: Architecture Plan (v1.1)

> See [STATUS.md](STATUS.md) for what is built (M1 is largely done, minus the LLM narration) and [DECISIONS.md](DECISIONS.md) for the reasoning behind choices.

Working name: TBD. Goal: help people *learn from* other people's projects. It understands repos beyond what the README says, and guides users to the right ones.

Principle: **no crawling or bulk indexing.** Everything is lazy, live, or a tiny fingerprint.

## Pipeline (all six ideas combined)

```
User goal ("I'm building a RAG chatbot")
        |
  [2] Discovery agent ---- GitHub Search API, topics, awesome-lists
        |                  [3] dependency graph: repos using lib X + Y
        v
   Candidate repos (20-50)
        |
  [4] Fingerprint check ---- cached ~1KB signature? yes -> reuse
        |                                              no  -> analyze
        v
  [1] Lazy analyzer (on demand, results cached)
        |-- Static layer: file tree, manifests, CI, Dockerfile, tests, license
        |-- [5] History layer: commit cadence, authorship, co-change, abandonment
        |-- LLM layer: scope, completeness, inferred purpose (evidence-cited)
        v
   Ranked finalists (top 3-5)
        |
  [6] Sandbox run ---- try build/install/start -> "runs: yes/no" + logs
        v
   Learning guide: what to read first, difficulty, gotchas
```

## Components

### 1. Lazy analyzer (core)
- Triggered by user request, never by crawling.
- Cheap-first: heuristics decide what the LLM needs to read, so most repos cost a few thousand tokens.
- Output: structured **Repo Profile** (schema below) with an evidence link for every claim.
- Cache result keyed by `repo + commit SHA`. Invalidate when HEAD moves.

### 2. Discovery agent
- LLM agent with tools: `search_repos`, `get_readme`, `get_tree`, `get_dependents`, `read_file`.
- Expands the user's goal into queries (synonyms, topics, library names, awesome-lists).
- Stops when it has enough strong candidates. Budget-capped (tool calls and tokens).

### 3. Dependency-graph search
- Parse manifests (`requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml`).
- Query: "repos depending on {langchain, chromadb, fastapi}". Use GitHub dependents data and code search. This is a factual stack signal, not an embedding.
- Also gives clean stack detection for the profile.

### 4. Fingerprints
- ~1KB per analyzed repo: stack tags, structure hash, maturity score, last-analyzed SHA.
- Stored in SQLite (Postgres later). Supports "similar repos" by tag/overlap and clustering with no content stored.
- Full files are fetched only on drill-down.

### 5. Git-history intelligence
- From `git log` (shallow-ish clone or API): commit cadence, bus factor, last-activity gap, WIP/fix ratio, files that change together (real architecture), early-commit narrative (how it was built).
- Derives signals like `abandoned`, `weekend-project`, `actively-maintained`, `team-built`.

### 6. Sandbox verification
- Only for finalists. Ephemeral container, no network after install, hard CPU/mem/time limits.
- Attempt: detect run recipe (Dockerfile, README commands, Makefile) -> build -> start -> health check.
- Result: `builds`, `starts`, failure log, time taken. Treat the repo as **untrusted code**. Isolation is a hard requirement (gVisor/Firecracker/Docker with no host mounts).

## Repo Profile schema (draft)

```json
{
  "repo": "owner/name", "sha": "...",
  "stack": {"languages": [], "frameworks": [], "services": []},
  "scope": "one-paragraph inferred purpose",
  "completeness": {"score": 0-100, "evidence": []},
  "deployability": {"score": 0-100, "evidence": [], "sandbox": {"builds": null, "starts": null, "log": ""}},
  "history": {"first_commit": "", "last_commit": "", "contributors": 0, "status": "active|stale|abandoned", "narrative": ""},
  "learning": {"difficulty": "beginner|intermediate|advanced", "read_first": [], "gotchas": []},
  "fingerprint": {"tags": [], "structure_hash": ""}
}
```

Every score must cite evidence (file/commit/log line). No unexplained numbers.

## Suggested stack (assumptions, change freely)
- Backend: Python (+ FastAPI when the web layer starts). Plain `git` via subprocess (partial clone); GitHub REST/GraphQL only for search and dependents.
- Custom algorithms first: import graph, PageRank, label propagation, git-history statistics, rules engine (see DECISIONS D3). The LLM only narrates the evidence packet.
- LLM: user-supplied keys (BYOK, D5) through `repolens/llm/router.py`, with failover across Groq, Gemini, OpenRouter and GitHub Models (D6). Not built on Copilot (D4).
- Storage: SQLite -> Postgres. Cache by `repo+SHA`.
- Sandbox: Docker with strict limits locally, then gVisor/Firecracker for hosting.
- Frontend: Next.js (or a simple React app) with a chat-style guide plus repo profile cards.

## MVP milestones
1. **M1: Analyzer CLI.** Given a repo URL, output a Repo Profile (static + LLM layers). Prove "inferred insight" quality.
2. **M2: History layer.** Add git-history signals and the narrative.
3. **M3: Dependency search.** "Find repos using X+Y" returning candidates.
4. **M4: Discovery agent.** Goal in, ranked finalists out.
5. **M5: Fingerprint cache** and similar-repo lookup.
6. **M6: Sandbox run** for finalists.
7. **M7: Web UI** with the guided learning flow.

## Risks and open questions
- GitHub API rate limits: use authenticated tokens, conditional requests, cache aggressively.
- Sandboxing untrusted code is a security risk: design isolation before writing M6.
- LLM judgment of "completeness" can be wrong: require evidence and calibrate on ~30 hand-labeled repos.
- Scope: start with AI/ML repos only.
- Open: product vs. hackathon/college project? Hosted service vs. local tool? LLM budget?
