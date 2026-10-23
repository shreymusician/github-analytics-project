# RepoLens (working name)

A GitHub intelligence tool that helps people **learn from other people's projects**. Give it a repository and it tells you what the README never does: what the project really is, how it works, whether it is alive, tested and runnable, and which files to read first. Every claim cites the evidence it came from.

> GitHub is built around personal and team project management. There is no good way to learn from the world's projects at scale. RepoLens is that layer.

## What a report contains

- **At a glance**: language, maintenance status, tests, CI, Docker, license, stars, archived flag, main libraries, source folders (all deterministic).
- **What it is**: summary, scope, maturity, written by a model **from cited evidence only**.
- **How it works**: a cited explanation of the flow plus the key parts, built from real source files and notebooks (any language).
- **Scores** for completeness and deployability, each with the reason for every point (heuristic, not yet calibrated).
- **Read these first**, subsystems, history (abandoned? one person? how it started), and the evidence list behind every citation.

## The web page (easiest way to use it)

```bash
python -m repolens.web
```

It prints a link (with a secret token) and opens it. Tabs: **Find repos** for a goal, **Analyze a repo**, **Reports** (the saved ones, with clickable citations that show the evidence), and **The project** (how RepoLens is built: pipeline, code map, roadmap %, decisions, verification results, commits, honest limits). It only listens on this machine and your keys are never sent to the page. See decision D28.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env            # add at least one LLM key (GROQ_API_KEY or GEMINI_API_KEY); GITHUB_TOKEN is optional
python -m repolens owner/name --md report.md      # or a GitHub URL, or a local git folder
python -m repolens owner/name --no-llm            # deterministic analysis only, no keys needed
python -m repolens.find "build a RAG chatbot" --language python   # find repos worth studying for a goal (no cloning)
python -m repolens.find "build a RAG chatbot" --deep 3 --dry-run   # show which repos a deep analysis would clone, and how big (downloads nothing)
python -m repolens.find "build a RAG chatbot" --deep 3             # clone and analyze the top 3 in depth; full reports go to reports/find/
python -m pytest -q
```

Useful scripts (run with `PYTHONPATH=.`):

| Script | What it does |
|---|---|
| `python -m repolens.llm.smoke` | check which configured LLM providers work |
| `scripts/gate_a.py` | analyze the 10 review repos into `reports/gate_a/` |
| `scripts/fact_check.py` | compare our facts with GitHub's own data |
| `scripts/audit_gate_a.py` | a second model checks every claim against its evidence |
| `scripts/audit_selftest.py` | plant false claims and confirm the judge catches them |
| `scripts/discovery_check.py` | run the repo finder on ten goals and print objective red flags |
| `scripts/answerability.py` | can a reader answer factual questions from the README vs our report? (graded by code) |
| `scripts/make_labels.py` | refresh `data/labels/gate_a.csv` (human scores are never overwritten) |

Keys live only in `.env` (git-ignored). The product design is bring-your-own-key: each user supplies their own.

## How it works

1. **Fetch**: a partial git clone (full history, file contents only for HEAD). Repo code is only ever *read*, never run.
2. **Custom analyzers (no AI)**: stack and manifests, Python and JavaScript/TypeScript import graphs with PageRank, git-history statistics, notebook outlines, CI/test/Docker/license rules, secret redaction.
3. **Evidence packet**: numbered facts (E1, E2, ...) and source excerpts (S1, S2, ...); repo text is fenced as untrusted data.
4. **LLM stages** (Groq / Gemini / OpenRouter / GitHub Models with automatic failover): narration and "how it works". Every statement must cite evidence; names, files and numbers must exist in it, or the statement is dropped.
5. **Verification**: facts cross-checked against GitHub, every claim audited by a *different* model, and an answerability test graded by code.

Results are cached per repo and commit, versioned by analyzer version, so an unchanged repo costs nothing.

## Status (honest)

V1 is code-complete: all 10 review repos are analyzed, narrated and explained, with 0 crashes and about 5 s per cached repo. **The human review (Gate A) was waived by the owner**, so the project is *machine-verified, human-unverified*: scores are first guesses, and nobody but the author has judged whether the reports are useful. See [docs/DECISIONS.md](docs/DECISIONS.md) (D18) and [docs/STATUS.md](docs/STATUS.md).

V3 has started: `python -m repolens.find "<goal>"` ranks repositories for a goal from GitHub search data (relevance, freshness, popularity, size, a model's reading of each description), flags curated lists, and suggests an easiest-first order. By default it clones nothing, so completeness and code quality are not assessed; `--deep N` (or `--deep-repos a/b,c/d`) then clones those finalists (partial clones, read-only, never run) and folds their health, tests, CI, completeness and a one-sentence summary into the ranking. `--dry-run` shows what would be cloned first.

Not built yet: a web app (V4), running repos in a sandbox (V5), community features (V6).

## Docs

| Doc | What's in it |
|---|---|
| [docs/VISION.md](docs/VISION.md) | The problem, the idea, who it's for, how it differs from existing tools |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Every key decision and why (read this to avoid re-litigating them) |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Versioned path V0 to V6 with deliverables, exit tests and decision gates |
| [docs/STATUS.md](docs/STATUS.md) | What's built, what's tested, known limits, next steps |
| [docs/GATE_A.md](docs/GATE_A.md) | The V1 review: repos, automatic verification results, how to score |
| [docs/DEEPWIKI_COMPARISON.md](docs/DEEPWIKI_COMPARISON.md) | How we compare with DeepWiki (they explain code better; we assess health better) |
| [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) | Existing tools and services, with live test results |
| [docs/PLAN.md](docs/PLAN.md) | Original architecture plan, profile schema, milestones |

## Layout

```
repolens/
  fetch.py         partial clone; read-only            files.py       bounded file walking
  stack.py         manifests, file census, taxonomy    ci.py          CI system detection (shared)
  graph.py         import graph, PageRank, read-first  jsgraph.py     JS/TS imports (regex)
  notebooks.py     notebook outline/imports/view       history.py     git-history intelligence
  signals.py       completeness / deployability rules  external.py    GitHub, Scorecard (fail-soft)
  evidence.py      numbered evidence packet            redact.py      secret scrubbing
  narrate.py       cited narration + grounding         architecture.py  cited "how it works"
  audit.py         second-model claim audit            factcheck.py   facts vs GitHub
  answerability.py readers answer checkable questions  labels.py      human review CSV
  discover.py      goal -> ranked repos (V3)           find.py        python -m repolens.find
  profile.py       pipeline + cache                    report.py      Markdown report
  storage.py       SQLite cache                        cli.py         command line
  llm/             providers, failover router, smoke test
tests/             synthetic repos, mocked HTTP, regression tests for every bug found on real repos
scripts/           batch runs, audits, benchmarks
docs/              vision, decisions, roadmap, status, reviews
data/labels/       human review scores (empty until someone reviews)
```
