# Ecosystem: existing tools and services worth using

Researched 2026-10-21. Part 1 (below) was **tested live the same day**; the rest comes from one search pass over mostly secondary sources and is untested. Verify licensing, limits and current status before depending on any item. Rankings are my judgment.

Principle (DECISIONS D3): our own algorithms stay the core. Use outside services where they save real work or replace an expensive step, and wrap each behind a small interface so it can be swapped or dropped.

## Live test results (2026-10-21)

| Endpoint | Result | Used by |
|---|---|---|
| GitHub REST `/repos/{o}/{r}` | Works with token (stars, topics, archived, license, last push) | `External.repo_meta` -> evidence |
| GitHub `/search/repositories` (topic, language, stars, pushed filters, sorted) | Works, 30/min, sensible results | `External.search_repos` -> **V3 candidate source** (no code search needed) |
| repos.ecosyste.ms `/hosts/GitHub/repositories/{o}/{r}` | Works, no key, 0.4s | Fallback when GitHub API fails |
| repos.ecosyste.ms `/hosts/GitHub/repositories/{o}/{r}/manifests` | Works, returns declared dependencies **without cloning** (includes noise: GitHub Actions paths, Docker images; filtered) | `External.manifest_dependencies` -> V3 cheap pre-filter |
| packages.ecosyste.ms package + `dependent_packages` | Works (published packages that depend on X, with repo URLs) | V3, packages only (apps not included) |
| repos.ecosyste.ms `/usage/pypi/{pkg}` | Works: dependents count (e.g. chromadb 7,581) | Adoption signal (not wired yet) |
| repos.ecosyste.ms `/usage/.../dependent_repositories` | **Broken**: HTTP 500 after ~15s for every package tried (chromadb, ragas, langgraph, sentence-transformers) | Do not depend on it |
| repos.ecosyste.ms topic search | **Unreliable**: topic/sort filters ignored | Do not depend on it |
| deps.dev v3 package, v3alpha `:dependents` | Works, but returns dependent **counts only** (e.g. 1,852), no list | Adoption signal (not wired yet) |
| OpenSSF Scorecard API | Works for repos that opted in (e.g. chroma-core/chroma: 5.1/10); others return nothing | `External.scorecard` -> evidence |

**Consequence for V3:** the plan to use code search for "repos using X + Y" is replaced by: GitHub repo search (topic/language/stars/recency) -> ecosyste.ms manifests to verify the stack cheaply -> lazy-analyze only the finalists. See DECISIONS D12.

## Adopt (high value, low risk)

| Tool | What it gives us | Where it fits | Notes |
|---|---|---|---|
| [ecosyste.ms](https://packages.ecosyste.ms/docs) (Packages, Repos, Parser APIs) | Package/version/dependency metadata across many registries, **dependent counts and dependent repositories**, repo metadata, manifest parsing | **V3 3.1 dependency search**; V2 manifest coverage | Free and open. README says default 5,000 requests/hour per IP. Code is AGPL-3.0 (we only call the API). Could sidestep GitHub's 10/min code-search limit. Check which endpoints list dependents before designing around it. |
| [deps.dev API](https://blog.deps.dev/api/) (Google Open Source Insights) | Transitive dependency graphs, dependents, advisories, OpenSSF Scorecard data | V3 discovery; V2 health signals | Covers Go, Maven, PyPI, npm, Cargo, NuGet. Free. Current v3 endpoints and limits not confirmed: read docs.deps.dev. |
| [OpenSSF Scorecard API](https://api.securityscorecards.dev/swagger.json) | Precomputed security/maintenance checks per repo, `GET /projects/github.com/{org}/{repo}` | Optional evidence in the profile (maintained? reviewed? pinned deps?) | Only repos whose maintainers publish results appear (opt-in). Weekly scans skip some checks. Data is CDLA-Permissive-2.0. Good *extra* signal, never required. |
| [tree-sitter](https://pypi.org/project/tree-sitter/) + language grammars (or tree-sitter-language-pack) | One parser for 100+ languages | **V2 2.4 JS/TS (and Go/Rust/Java) import graphs** | Use current per-language wheels (`tree-sitter-python` etc.); older `build_library` guidance is outdated. Our graph/PageRank code stays; only the import extractor changes. |

## Consider (useful, optional)

| Tool | Use | Notes |
|---|---|---|
| [scc](https://github.com/boyter/scc) (or tokei) | Fast code counting across 250+ languages with complexity estimates, plus a file-type census | Fixes the `mini_proj` blind spot (non-code files). But it is an external Go binary; a small Python census is enough for now. |
| [PyDriller](https://pydriller.readthedocs.io) | Convenient git-mining API (commits, diffs, per-file change metrics) | We already mine `git log` directly. Useful only if we need diff-level metrics (churn, per-author edits). |
| [Semgrep OSS](https://semgrep.dev) / Bandit | Static-analysis rules; flag risky AI/ML patterns (unsafe `pickle`, `numpy.load(allow_pickle=True)`; Trail of Bits wrote rules for this) | A "risk flags" line in the profile. Noted gap: Semgrep misses some dynamic imports that Bandit catches. |
| [Ollama](https://ollama.com) / llama.cpp | Local LLM with an OpenAI-compatible API (`/v1/chat/completions`) | Fits our router as a fifth provider with zero code changes. Sources disagree on speed differences; benchmark on your own hardware. Reports of Ollama's OpenAI shim quirks, so test JSON mode. |
| [GH Archive](https://gharchive.org/) (+ BigQuery public dataset) | Hourly public GitHub event data since 2011; stars, forks, activity over time | Popularity/trend signals and V6 trends. Large; BigQuery usage is billed beyond free quota. |
| [Software Heritage](https://docs.softwareheritage.org/devel/swh-dataset/graph/) | Deduplicated archive of public source code (GitHub, GitLab, PyPI...) with a public API and graph dataset | Resilience if a repo vanishes; research-scale cross-repo analytics. Bulk access needs accepting their terms; we could not read the license text. |

## Study but do not depend on

| Tool | Why |
|---|---|
| [Gitingest](https://github.com/cyclotruc/gitingest), [Repomix](https://github.com/yamadashy/repomix) | Pack a repo into one LLM-ready file. Our evidence packet is deliberately smaller and cited, but Repomix's secret-detection and token counting are worth comparing against our `redact.py`. |
| [DeepWiki](https://huggingface.co/blog/lynn-mikami/deepwiki) / deepwiki-open | Direct competitor on summarization. Study its output as a baseline for Gate A comparisons. |
| [RepoSnipy/RepoSim](https://research-portal.st-andrews.ac.uk/en/publications/mapping-the-repository-landscape-harnessing-similarity-with-repos/), [MetaSim](https://conf.researchr.org/details/icsme-2024/icsme-2024-tool-demo-track/3/MetaSim-A-search-engine-for-finding-Similar-GitHub-Repositories) | Research on repo similarity. Useful for evaluating our fingerprint approach (V3 3.4), and for the benchmark methodology. |
| [OpenSSF Scorecard](https://github.com/ossf/scorecard) and [CHAOSS](https://wiki.linuxfoundation.org/chaoss/metrics) | Established metric definitions. Borrow their check names and rationale for our rules engine instead of inventing from scratch. |

## Sandbox options (V5)

Vendor comparison pages dominate the results, so treat claims as marketing until verified.

| Option | Isolation | Self-host? | Notes |
|---|---|---|---|
| Docker + gVisor | User-space kernel | Yes | Lighter to run; per sources, used by Modal's hosted service. |
| [Firecracker](https://firecracker-microvm.github.io/) microVMs | Hardware-level (KVM, Linux only) | Yes | Strongest isolation; real DevOps effort, no managed SDK. |
| E2B | Firecracker | Cloud (self-host via enterprise BYOC; licensing described inconsistently) | Fast path to a hosted sandbox; paid at scale. |
| Daytona | Docker containers | Yes (Apache-2.0 per one comparison) | Weaker isolation than microVMs; aimed at dev environments. |

Recommendation for V5: start local-only with Docker + strict limits (no network after install, no host mounts); decide on gVisor/Firecracker or a hosted sandbox only when hosting is on the table.

## Not researched yet
GitHub Linguist (language detection), Syft/SBOM tools, libraries.io (status unknown), Sourcegraph/Zoekt (code search), curated "awesome" lists as discovery seeds, embedding models for the optional similarity upgrade.

## Suggested next steps
1. Test ecosyste.ms and deps.dev dependents endpoints with real queries; if they work, redesign V3 3.1 around them and keep GitHub code search as a fallback.
2. Add tree-sitter when starting V2 2.4.
3. Add a Python file-type census now (cheap, fixes a known blind spot); revisit scc if speed matters.
