# Vision

## The problem

GitHub is excellent for managing your own projects and collaborating with a team. Its value is mostly personal, not collective. Someone building an AI/ML project who wants to learn how others solved the same problem has no good platform for it:

- Search is keyword-based. It finds repos that *mention* a thing, not repos that *implement it well*.
- A README says what the owner chose to say. It rarely says whether the project is finished, runnable or abandoned, what the architecture really is, or where to start reading.
- Stars measure popularity, not learnability or completeness.

## The idea

A platform with two parts:

1. **Repo understanding.** Given a repository, infer what isn't explicitly stated:
   what's in it, the tech stack, whether it's complete, whether it's deployable, its scope, how it was built, and which files matter most.
2. **Guided exploration.** Given a goal ("I'm building a RAG chatbot"), guide the user to the repos worth studying, in a sensible order, with notes on what to read first and what to watch out for.

The longer-term, "society-based" angle: cross-repo analytics (how do 20 projects handle RAG chunking?) and community-verified annotations ("I got this running; step 4 of the README is broken").

## Who it's for

Primarily learners and builders in AI/ML who want to learn from existing projects. The first target is AI/ML repositories only, to keep the problem narrow and the taxonomy tractable.

## Differentiation

The research (October 2026, shallow, mostly secondary sources; see caveats) found the pieces exist separately but not combined:

| Piece | Existing work | Gap |
|---|---|---|
| Repo summaries / docs | [DeepWiki](https://huggingface.co/blog/lynn-mikami/deepwiki) (Cognition, free, public repos), Repolyze, Gorang | DeepWiki is the strongest and is a direct competitor on summarization. It documents what a repo *is*; it doesn't judge completeness or guide discovery. |
| Deployment readiness | [ShipSage](https://lablab.ai/submissions/s1lui6e0od3et666xmc6714f) (hackathon project) | Hackathon-grade, not combined with discovery |
| Health / quality | [OpenSSF Scorecard](https://cisa.gov/resources-tools/services/openssf-scorecard) (security), [CHAOSS](https://wiki.linuxfoundation.org/chaoss/metrics) (community health) | Built for maintainers and enterprises, not learners |
| Similar-repo search | [RepoSnipy/RepoSim](https://research-portal.st-andrews.ac.uk/en/publications/mapping-the-repository-landscape-harnessing-similarity-with-repos/) (Python only), [MetaSim](https://conf.researchr.org/details/icsme-2024/icsme-2024-tool-demo-track/3/MetaSim-A-search-engine-for-finding-Similar-GitHub-Repositories), [GitHub Repo Radar](https://chromewebstore.google.com/detail/bceechbnflcmoabbeahepafgackkjcno) | Research prototypes, narrow, often dated |

**Where GitHub Intel is different**
1. *Inferred insight*: completeness, deployability and "what it really is", each backed by cited evidence.
2. *Guided exploration*: learning paths, not search results.
3. *Cross-repo analytics* once repos are structured data.
4. *Explainable by construction*: custom algorithms produce facts; the LLM narrates them.

**Do not compete on plain summarization.** DeepWiki is free and backed by a company.

**Caveats on the research:** it was shallow; most hits were hackathon or community listings whose features and maintenance status were not verified. Commercial tools (Sourcegraph, Greptile, CodeSee, etc.) were not checked. Re-check the landscape before any launch.

## Risks

- DeepWiki overlap on the summarization layer.
- Reliability of completeness/deployability verdicts. A wrong verdict kills trust.
- LLM and GitHub API cost and rate limits (mitigated by the design, see PLAN.md).
- Cold start for any discovery product (mitigated by the AI/ML niche and lazy analysis).
- Distribution: building the tool is easier than getting people to use it. Launch narrow (a paste-a-URL page or browser extension) and learn first.
- Running untrusted repo code in a sandbox is a real security risk. It is deferred until isolation is designed.
