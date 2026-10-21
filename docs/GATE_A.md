# Gate A review: 10 repos

Goal (ROADMAP V1 exit test): for each repo, does the report tell a reader something the README does not, and is every claim true? Prepared 2026-10-21 from GitHub search metadata only. **Nothing has been downloaded yet; cloning needs approval.**

Sizes are GitHub's reported repo size (upper bound; partial clones with `--filter=blob:none` should be smaller). Total about 95 MB at most.

## The list

| # | Repo | Why it's here | Stars | Size | Last push | Expected stress |
|---|---|---|---|---|---|---|
| 1 | [feyninc/chonkie](https://github.com/feyninc/chonkie) | Maintained, packaged RAG-chunking library: the "complete" archetype | 4.8k | 23.6 MB | 2026-10-20 | Should score high on completeness/deployability |
| 2 | [lightly-ai/lightly](https://github.com/lightly-ai/lightly) | Mature computer-vision library with tests and docs | 3.8k | 12.6 MB | 2026-10-15 | Second "complete" sample, different domain |
| 3 | [roboflow/sports](https://github.com/roboflow/sports) | Small CV project, mixed code and example notebooks | 5.4k | 1.7 MB | 2026-08-28 | Notebook/example-heavy small repo |
| 4 | [nianticlabs/monodepth2](https://github.com/nianticlabs/monodepth2) | Research code accompanying a paper (ICCV 2019): not packaged, still touched | 4.5k | 10.3 MB | 2026-10-05 | "Research code" archetype: no tests/CI expected, still valuable to learn from |
| 5 | [jaymody/picoGPT](https://github.com/jaymody/picoGPT) | Tiny GPT-2 in NumPy: a handful of files, abandoned 2023 | 3.5k | ~0 MB | 2023-04-24 | Tiny-repo edge case; "abandoned" but arguably *complete* |
| 6 | [snipsco/snips-nlu](https://github.com/snipsco/snips-nlu) | Serious NLU library, abandoned since 2023 | 4.0k | 19.8 MB | 2023-05-22 | Large, well-built, **stale**: tests the history/status signal |
| 7 | [idealo/image-super-resolution](https://github.com/idealo/image-super-resolution) | Archived CV project | 4.8k | 15.0 MB | 2024-12-18 | **Archived** flag from GitHub; TensorFlow-era code |
| 8 | [andri27-ts/Reinforcement-Learning](https://github.com/andri27-ts/Reinforcement-Learning) | Course repo, mostly notebooks, abandoned 2020 | 4.7k | 10.2 MB | 2020-06-30 | **Notebook-heavy**: our Python-import graph barely sees notebooks |
| 9 | [raiyanyahya/how-to-train-your-gpt](https://github.com/raiyanyahya/how-to-train-your-gpt) | Tutorial: build an LLM from scratch | 4.1k | 0.3 MB | 2026-08-30 | Teaching repo: "complete as a tutorial" vs "not deployable" |
| 10 | [mishushakov/llm-scraper](https://github.com/mishushakov/llm-scraper) | TypeScript LLM library | 6.9k | 0.2 MB | 2026-09-10 | **Known weakness**: our import graph is Python-only; shows how badly we degrade |

Optional 11th, stress test: [gradio-app/gradio](https://github.com/gradio-app/gradio), 43.8k stars, about 123 MB, Python + JS monorepo. Include only if you want to test large-repo behavior.

Covers: maintained (1-3), research code (4), tiny (5), stale-but-serious (6), archived (7), notebooks (8), tutorial (9), non-Python (10). Predictions in the last column are guesses made without opening the repos.

## Safety
These are untrusted repos from strangers. The tool only *reads* files (`git clone` with symlinks off, then text reads and `ast.parse`); it never installs, imports or runs anything from them. Text from the repos goes to an LLM with secrets redacted and is fenced as untrusted.

## How to score each report (about 5 minutes each)

For each repo, open the generated report and the repo's README side by side.

| Question | Score |
|---|---|
| **Insight**: did the report tell me something true that the README does not? | 0 none / 1 a little / 2 clearly yes |
| **Accuracy**: any statement that is false or misleading? | count them (0 is the goal) |
| **Completeness verdict**: does the completeness score + reasons match your own view? | too low / about right / too high |
| **Deployability verdict**: same | too low / about right / too high |
| **Read-first list**: are the suggested files a good place to start? | useless / okay / good |
| **Would you trust this to decide whether to study the repo?** | yes / maybe / no |

Optional baseline: open `deepwiki.com/<owner>/<repo>` for 3 or 4 repos and note what DeepWiki says that we do not, and the reverse.

## Pass criteria *(proposed)*
- Insight score of at least 1 on 8 of 10 repos.
- No more than 1 false statement per 3 reports on average.
- Completeness and deployability "about right" on at least 7 of 10.

Your scores also become the first labeled data for V2 calibration. Record them in a table at the bottom of this file as you go.

## Where the reports are, and how they were produced

Reports are on disk in `reports/gate_a/` (git-ignored; regenerate any time with `python scripts/gate_a.py`, about 5 to 30 seconds per repo once cloned). Each repo has a `.md` report to read and a `.json` with the full evidence. Earlier passes are kept for comparison: `reports/gate_a_v1/` (first run) and `reports/gate_a_v2/` (after the first round of fixes). Clones are cached under `.cache/repos/`.

Timing. The first run, including cloning, took chonkie 162 s, lightly 123 s, image-super-resolution 89 s and snips-nlu 80 s. Timing instrumentation then showed a cold chonkie run spent 15 s cloning but **41 s on git history**: rename detection makes a partial clone download file contents one batch at a time. With `--no-renames` the same cold run takes 22 s total (history 0.2 s), under the proposed 60 s target. Current warm runs for all ten repos are 5 to 19 s.

## What changed between the first run and the one you are reviewing

The first run exposed defects that the synthetic tests could not. They are fixed (see git history from `chore: stop tracking generated Gate A reports` onward), so read the current reports, not the v1 ones.

| First-run problem | Fix |
|---|---|
| 5 of 10 reports opened with "dominated by media/other files" (images and weights swamping byte counts) | Composition now separates what the authors wrote from binary assets |
| snips-nlu and image-super-resolution reported "no dependency manifest" (they use setup.py) | setup.py / setup.cfg / Pipfile / conda env files are parsed (statically, never executed) |
| llm-scraper (TypeScript) scored Completeness 100 because Python-only checks silently passed | Those checks are now "not assessed" and excluded; the report says the analysis is partial |
| monodepth2's demo script test_simple.py counted as a test | A test file must actually contain tests |
| Abstract methods counted as unfinished stubs | They are skipped |
| "Read these first" favored constants.py, logger.py, bare __init__.py | Ranked by entry point, hub role and substance |
| Model suggestions like README.md or a notebook were rejected as "not found" | Notable non-Python files are valid suggestions |
| Rounded figures ("about 1500 commits") dropped true statements | Round figures within 10% are accepted |
| Narration missing for some repos during the batch | Waits once for rate limits; asks for fewer tokens (Groq's 8,000 tokens/minute budget) |

Current state of the final run (analyzer version 7): 10 of 10 narrated, 0 crashes, 2 statements dropped in total (monodepth2: "cuDNN" and Reinforcement-Learning: "requirements.txt" were not in the evidence).

Bugs found while regenerating the reports and fixed since the table above: inline evidence IDs such as "(E38, E41)" were read as invented numbers and wiped one repo's whole narration; a 503 benched a provider for 60 s, so picoGPT lost its narration twice; a degraded narration was cached; real files such as `chapters/*.md` were rejected as reading suggestions; large `.txt` split lists counted as docs.

## Known weak spots to look for while scoring

These are things I already suspect are wrong or weak. Please say if they bother you.

- **Scores are still my guesses.** Completeness and deployability weights are uncalibrated; your "too low / about right / too high" answers are what will calibrate them.
- **Notebook-heavy repos (#3, #8, #9)**: the import graph does not read notebooks, so architecture details are thin.
- **llm-scraper (#10)**: analysis depth is partial by design; there is no "read first" list because the graph is Python-only. Judge whether the narration is still useful without it.
- **monodepth2 (#4)**: previously mislabelled as 98.7% "docs" (large `.txt` split lists); fixed, they now count as data. Check that its composition reads sensibly.
- **Maturity labels** (prototype / working-demo / usable) come from the model reading the rule results, so they can disagree with the numeric scores. Chonkie got "working-demo" despite a 100/90 score.
- **Narration is from one model family**, mostly Groq gpt-oss-120b, with Gemini as fallback; wording and judgment can vary between runs of the same repo.
- **The citations check names, filenames and numbers, not meaning.** A statement can pass and still be misleading, so please flag any claim that feels wrong even if it looks cited.

## Automated verification (done without a human, analyzer version 8)

Because reading every report is slow, three automatic checks were run. They verify facts and internal consistency; they do **not** replace your judgment of whether a report is useful.

**1. Facts checked against GitHub** (`scripts/fact_check.py`): 78 of 80 facts agree. Dockerfile, CI, license, dependency manifest, tests, file count and activity status all matched GitHub's own file list and default-branch commit dates on all ten repos. The two disagreements are `primary_language` for monodepth2 and Reinforcement-Learning: GitHub says "Jupyter Notebook" because it counts raw notebook bytes including embedded outputs; we count the code people wrote (Python). We think ours is the more faithful answer. These are easy facts with simple rules on both sides, so this shows there are no gross analyzer bugs, nothing more.

**2. Second-model audit of every claim** (`scripts/audit_gate_a.py`): a different model (Gemini for eight repos, Groq for two whose narrator was Gemini) judged each statement against the evidence. 103 claims: 102 supported, 1 partly, 0 unsupported, 0 contradicted. Positive control (`scripts/audit_selftest.py`): the judge caught 3 of 3 planted false claims and accepted the planted true one. Earlier runs of the audit were useful: they flagged the narrator guessing each repo's "audience" (the prompt now forbids guessing) and reading-list reasons inferred from file names alone (Reinforcement-Learning). Limits: the judge sees the same evidence as the narrator, so it cannot find facts the evidence never held, and four planted claims prove sensitivity to obvious errors only.

**3. Comparison with DeepWiki** (`docs/DEEPWIKI_COMPARISON.md`, three repos, overview pages only): DeepWiki explains what the code does and how, much better than we do (including for TypeScript); our reports add maintenance, test/CI/deployability, history and risk signals that its overview pages did not show. Complementary, not a replacement. Author's reading, not neutral.

**What is still unknown and needs you:** whether a person finds the reports insightful, whether the maturity labels and read-first lists feel right, and whether the scores are too generous. The audit cannot answer those.

## Where to record your scores

Preferred: edit **`data/labels/gate_a.csv`** (open it in Excel or any editor). Machine columns are pre-filled; fill the seven human columns per repo:

| Column | Allowed values |
|---|---|
| insight_0_2 | 0 (nothing new), 1 (a little), 2 (clearly yes) |
| false_statements | a whole number (0 is the goal) |
| completeness_verdict, deployability_verdict | too_low, about_right, too_high |
| read_first_quality | useless, ok, good |
| trust | yes, maybe, no |
| notes | free text |

Check your entries with `PYTHONPATH=. python scripts/make_labels.py --check`. Re-running `scripts/make_labels.py` after a new analysis refreshes only the machine columns and never overwrites what you wrote. These scores become the calibration data for V2, so honest "too_high / too_low" answers matter more than being kind to the tool.

The table below is an optional human-readable summary if you prefer prose.

## Results

| # | Repo | Insight | False statements | Completeness | Deployability | Read-first | Trust | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | chonkie | | | | | | | |
