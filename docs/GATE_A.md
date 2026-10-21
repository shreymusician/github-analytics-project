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

## Results

| # | Repo | Insight | False statements | Completeness | Deployability | Read-first | Trust | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | chonkie | | | | | | | |
