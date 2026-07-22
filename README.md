<div align="center">

<img src="assets/banner.png" alt="An ornate chariot drawn by four horses." width="100%">

# sarathi

<p lang="sa"><strong>योगः कर्मसु कौशलम्</strong></p>

<p><em>“Yoga is skill in action.”</em><br>
<sub><a href="https://github.com/gita/gita">Bhagavad Gita 2.50</a></sub></p>

<p><strong>Plan carefully, then carry that care into execution.</strong></p>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

Most coding agents can write code. The hard part is getting them to be honest about it: to read
the real files instead of guessing, fix the actual bug instead of hiding it, slow down when the
work is risky, and run the one check that proves the change works.

Sarathi is a small set of instructions for exactly that. It is not a framework and it is not a
program you run. It adds nothing to your project. It is 2,077 bytes of plain guidance that tells an
agent one thing: find the cheapest way to a verified result, stop once the evidence is clear, and
say so plainly when the evidence is missing.

## When it helps

Use it when a confident wrong answer would cost you:

- code changes that need to be read and tested before you trust them
- bugs where the first fix often just hides the problem
- anything with state, concurrency, security, or actions you cannot undo
- an agent that keeps failing the same way and needs a fresh idea
- a decision where the final call is yours, not the agent's

For a quick question, it gets out of the way and just answers.

## Install

For Claude Code:

```bash
claude plugin marketplace add ujjwalredd/sarathi
claude plugin install sarathi@sarathi
```

From a local clone:

```bash
git clone https://github.com/ujjwalredd/sarathi.git
cd sarathi
make install
```

The current plugin version is `0.3.0`.

If Claude Code is already open, reload its plugins:

```text
/reload-plugins
```

Claude loads Sarathi on its own when a request matches the skill. To call it directly, run:

```text
/sarathi:sarathi
```

To check the installed version:

```bash
claude plugin details sarathi@sarathi
```

It should show version `0.3.0` and `Skills (1) sarathi`.

## Why the Bhagavad Gita?

Because agents fail in old, familiar ways, and the Gita already had names for them.

An agent that games a test instead of fixing the bug is chasing the fruit of the work instead of
doing the work. An agent that spirals after one mistake has lost its footing. So Sarathi borrows
nine verses and uses them as labels for nine common failure modes. `action-not-fruit`, for example,
is a reminder to solve the real problem instead of gaming the score that stands in for it.

This is a naming library, not scripture and not religious instruction. The engineering rule and the
literal meaning of each verse are kept separate, and the Sanskrit stays out of the prompt the agent
loads every time. Storing the real text also stops the agent from inventing quotes or verse numbers
from memory. The exact verses, plain-language summaries, and sources are in
[`skills/sarathi/references/anchors.json`](skills/sarathi/references/anchors.json), drawn from the
public-domain [`gita/gita`](https://github.com/gita/gita) project. Sarathi claims no religious
authority.

## What a real-agent benchmark showed

The honest way to measure a skill is to watch a real agent do real work. So I borrowed Ponytail's
own agentic harness and added Sarathi as an arm. Every run is a headless Claude Code session
(Haiku 4.5) editing tiangolo's [full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template),
scored on the `git diff` it leaves behind. Twelve feature tickets for the size test, six adversarial
tickets for the safety test, the same agent with and without each skill, n=4.

![Every metric vs the no-skill baseline: sarathi is leaner than baseline on LOC, tokens, cost and time; ponytail cuts the most code; caveman rises above 100%.](assets/benchmark-agentic.svg)

Each arm as a percent of the no-skill baseline (lower is leaner, cheaper, faster):

| vs no-skill baseline | LOC | tokens | cost | time | safe |
|---|--:|--:|--:|--:|--:|
| **sarathi** | **-14%** | **-1%** | **-3%** | **-6%** | 96% |
| ponytail | -41% | +1% | -2% | -9% | 100% |
| caveman | +13% | +33% | +24% | +25% | 96% |

Sarathi beats the no-skill baseline on every metric and never bloats. It has the lowest raw cost
and token use of any arm here, and it buries caveman, which is worse than doing nothing on all four
metrics. But it does not win. Ponytail cuts far more code, because deleting lines is the one thing
it is built to do. And Sarathi is not perfect on safety: on the six adversarial tickets it scored
23 of 24, missing once when its `csv-sum` code crashed on a malformed row instead of handling it.
That is a real miss, so it is reported as one. Baseline and Ponytail held 100%.

Fairness note: all three skills are injected identically as always-on system prompts, and the
baseline gets none, so any difference is the skill's effect. Six safety tickets are a floor, not a
proof of security, and n=4 is small. The result stands on its own: leaner than nothing, far better
than caveman, behind Ponytail on code and one guard short of a clean safety sweep.

## An earlier check on Codex

Before the agentic run above, I ran a smaller single-shot benchmark on Codex `gpt-5.5`. It reached
a similar conclusion: Sarathi got cheaper but did not beat everything, and the plainest agent won.

Here is that test. Four setups did the same eight repair tasks, once each, using Codex `gpt-5.5`.
That is 32 runs. Every agent got the same starter file and the same spec. After each agent
finished, a grader ran 62 hidden checks it had never seen. Those same checks pass on a clean
reference solution, so they are fair.

The four setups were: no skill at all (the control), two other published skills (Caveman and
Ponytail), and Sarathi. Here is how many tasks each one solved, and how many tokens it spent to get
there:

| Setup | Solved | Skill size | Tokens per solved task |
|---|---:|---:|---:|
| No skill | **8/8** | 0 bytes | **129,148** |
| Ponytail | **8/8** | 5,700 bytes | 202,511 |
| Sarathi | 7/8 | **2,077 bytes** | 172,581 |
| Caveman | 7/8 | 4,774 bytes | 175,631 |

Sarathi tied Caveman and spent 1.7% fewer tokens per solved task. It was 14.8% leaner than
Ponytail. But Ponytail solved one more task, and the agent with no skill at all solved the most and
spent the least.

Both misses were on the same tricky task, and for different small reasons. Sarathi checked the
shape of the data before it checked the version number, so it raised the wrong error. Caveman kept
the original order of some labels when the answer needed them sorted.

One more honest caveat: 32 runs is not enough to call a winner. Once you account for how small the
sample is, none of these differences are real yet in the statistical sense. And "tokens per solved
task" is a rough cost proxy, not a dollar figure, because this run did not report money.

## How I kept it fair

- Sarathi was locked before the tasks were written, so it could not be tuned to them.
- The other two skills use the exact published text, pinned to a commit. Hashes are in
  [`bench/vendor/provenance.json`](bench/vendor/provenance.json).
- The order of runs is shuffled with a saved seed, so no setup gets an easier slot.
- Each run is fully isolated, so no installed skill can leak in and help another setup.
- A safety check confirms the agent cannot touch this repo, your home folder, or the network.
- A hidden test that fails to run is thrown out. It never counts as a pass.
- All raw output stays local and is never pushed to GitHub.

This is a test harness for ordinary model output, not a shield against hostile code. If you ever
run untrusted candidates through it, use a throwaway machine or account.

## Reproduce it

Free checks:

```bash
make check
```

Current result: 80 unit tests and 14 repository invariants pass.

Preview the scored matrix without model calls:

```bash
python bench/repo_bench.py \
  --suite heldout-v2 \
  --arms A F G H \
  --n 1 \
  --jobs 1 \
  --dry-run
```

Run it:

```bash
make repo-bench N=1
```

Model calls can consume quota. The runner records the model, CLI and Python versions, seed, prompt
hashes, task hashes, skill hash, token usage, outputs, and confidence intervals in local ignored
artifacts.

## What would count as a real win

A real win needs a bigger test, planned in advance, with each task run several times. Sarathi would
have to match everyone on correctness, clearly cost less per solved task, and hold that lead even
after you account for luck. Until then, the honest summary is simple: on this run Sarathi was
smaller and leaner than the two other skills and tied Caveman on correctness, but Ponytail and the
no-skill agent still did better.

## Repository map

- [`skills/sarathi/`](skills/sarathi/) contains the installable skill and sourced references.
- [`bench/repo_bench.py`](bench/repo_bench.py) runs isolated executable repository tasks.
- [`bench/repo_tasks/`](bench/repo_tasks/) contains the final forward-test suite.
- [`bench/`](bench/) also contains the original reference ablation, scorer, and pinned competitors.
- [`.claude-plugin/`](.claude-plugin/) contains Claude Code marketplace metadata.
- [`assets/banner.png`](assets/banner.png) is the banner shown above.

## License

Sarathi is MIT licensed. See [LICENSE](LICENSE). Vendored Caveman and Ponytail sources retain their
upstream text, provenance, and notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
