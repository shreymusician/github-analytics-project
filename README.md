# RepoLens (working name)

A GitHub intelligence platform that helps people **learn from other people's projects**. It analyzes a repository and infers what the README never says: what it really is, whether it's complete, whether it can be deployed, which files carry the architecture, and how it was built. It then guides users to the right repos to study.

> GitHub is built around personal and team project management. There's no good way to learn from the world's projects at scale. RepoLens is that layer.

## Docs

| Doc | What's in it |
|---|---|
| [docs/VISION.md](docs/VISION.md) | The problem, the idea, who it's for, how it differs from existing tools |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Every key decision and why (read this to avoid re-litigating them) |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Versioned path V0 to V6 with deliverables, exit tests and decision gates |
| [docs/ECOSYSTEM.md](docs/ECOSYSTEM.md) | Existing tools and services we can use (adopt / consider / study), with caveats |
| [docs/PLAN.md](docs/PLAN.md) | Architecture, pipeline, profile schema, milestones |
| [docs/STATUS.md](docs/STATUS.md) | What's built, what's tested, known limits, next steps |

## Core principle

**Hybrid: custom algorithms do the work, LLMs do the judgment.**
Deterministic analyzers (import graph + PageRank, git-history statistics, manifest parsing, rules engine) produce an evidence packet for free. An LLM, supplied by the user's own API keys, turns that evidence into the summary, scope and learning path. Every score cites its evidence.

## Quick start (current state: analyzers only)

```bash
pip install -r requirements.txt
python -m repolens <local-path | github-url | owner/name>
python -m pytest -q
```

Copy `.env.example` to `.env` for API keys (needed once the LLM layer is wired in). Never commit `.env`.

## Layout

```
repolens/
  fetch.py     partial clone (full history, blobs only for HEAD); read-only
  files.py     bounded file walking shared by all analyzers
  stack.py     stack detection from manifests + AI/ML capability taxonomy
  graph.py     Python import graph, PageRank (read-first), subsystem detection
  history.py   git-history intelligence (status, bus factor, co-change, origin story)
  signals.py   completeness / deployability rules engine, with evidence
  profile.py   assembles the Repo Profile; CLI entry
  llm/         multi-provider router with failover (Groq, Gemini, OpenRouter, GitHub Models)
tests/         synthetic-repo tests, mocked-HTTP router tests
docs/          vision, decisions, plan, status
```
