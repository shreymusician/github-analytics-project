# DeepWiki vs RepoLens: a first, small comparison

Date: 2026-10-21. Three repos, DeepWiki **overview pages only**, read through the built-in browser (the plain HTTP fetcher got 429 Too Many Requests on every try, so DeepWiki appears to rate-limit automated fetchers). Our side is the Gate A report at analyzer version 8.

**Bias warning.** I built RepoLens and wrote this comparison. It is a builder's reading, not a neutral evaluation, and three repos is an anecdote. DeepWiki has many sub-pages beyond the overview (for example sections on pipelines, APIs, testing) that I did not read, so "DeepWiki doesn't mention X" below means "X is not on the overview page".

## What I found

| | DeepWiki (overview page) | RepoLens report |
|---|---|---|
| **What the code does and how** | **Much stronger.** Names the architecture (chonkie's CHOMP pipeline), lists subsystems with their key classes, shows class hierarchies and data flow diagrams, runnable example code, source-line references, and a navigable wiki roadmap. For snips-nlu it walks the whole NLU pipeline step by step. | One-paragraph summary and scope. Accurate but shallow. "Read first" lists are weak (chonkie's top picks are `types/__init__.py` and `__init__.py`). |
| **TypeScript repo (llm-scraper)** | Handles it well: components, the three run modes, content formats, providers. | Partial analysis only: no read-first list, no architecture. Clearly the weakest of our ten reports. |
| **Is it maintained? abandoned?** | Not on the overview pages (zero mentions of abandoned, stale, last commit, archived for snips-nlu and llm-scraper). | **Stronger.** snips-nlu: abandoned, last default-branch commit 2021-05-03, bus factor 1, 20 contributors. llm-scraper: stale (last commit June 2026), bus factor 1. |
| **Tests, CI, Docker, deployability** | Not on the overview pages (zero mentions of CI, Docker, deploy). | **Stronger.** Checked per repo with reasons: chonkie has 86 test files, CI and a Dockerfile (completeness 100, deployability 90); snips-nlu has no CI or Dockerfile (deployability 35). Verified against GitHub's own file list (78 of 80 facts agree). |
| **Security / health signals** | None seen. | OpenSSF Scorecard when available (snips-nlu 3.2/10), license, stars, archived flag. |
| **Claim checking** | Not visible to the reader. | Every statement cites evidence; a second model audited 91 claims (85 supported, 2 partly, 4 unsupported). |
| **Cost / availability** | Free, instant for indexed public repos. | Needs an LLM key per user; reports take seconds to a minute. |

## What this suggests

1. **We should not compete on explaining the code.** On "what is it and how does it work", DeepWiki is clearly better, and it is free and backed by a company. Our version of that part is a weaker copy.
2. **Our edge is the assessment layer**: is it alive, is it tested, can it be run, who maintains it, how risky is it. That is information a learner choosing which project to study needs, and the overview pages I read did not provide it.
3. **The two are complementary.** A learner would want DeepWiki's architecture explanation next to our "is this worth studying" verdict. That points toward either linking out to DeepWiki from our reports or, longer term, doing a better job on the explanation layer ourselves (more of the source in the evidence). Linking is the cheap, honest option. Whether we may reuse or embed DeepWiki content has not been checked; I did not look at their terms.
4. **Our weakest parts are now visible:** the read-first lists, non-Python repos, and the shallow explanation. Those are the next improvements, not more scoring rules.

## What would make this a fair comparison

- Read several sub-pages per repo (not just the overview), including any testing, deployment and maintenance sections.
- Try more repos, including abandoned and notebook-heavy ones (only three were checked, all of which DeepWiki had indexed).
- Have someone who did not build RepoLens judge both side by side. That is what the Gate A human review is for.
