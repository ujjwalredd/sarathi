<div align="center">

<img src="assets/banner.png" alt="An ornate chariot drawn by four horses." width="100%">

# sarathi

<p lang="sa"><strong>योगः कर्मसु कौशलम्</strong></p>

<p><em>“Yoga is skill in action.”</em><br>
<sub><a href="https://github.com/gita/gita">Bhagavad Gita 2.50</a></sub></p>

<p><strong>Plan carefully, then carry that care into execution.</strong></p>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

Coding agents rarely fail because they cannot write another line of code. They fail because they
guess what a file contains, fix a test instead of the bug, wander into unrelated refactors, repeat
an approach that already failed, or declare victory before running the checks.

Sarathi is a small skill that pushes an agent in the other direction. It keeps the task in view,
asks for evidence, matches effort to risk, and verifies the result before making a claim.

## What changes when Sarathi is active?

Without Sarathi, an agent might see a failing permission test and suggest skipping it. With
Sarathi, it treats the test as evidence, inspects the authorization path, fixes the behavior, and
runs the relevant checks.

The same idea applies elsewhere:

- If the repository is available, read the code before prescribing a patch.
- If the files are missing, say what needs to be inspected instead of inventing their contents.
- If two attempts fail, stop repeating them and test a different hypothesis.
- If the task touches payments, security, production, or user data, slow down and verify more.
- If the question is simple, answer it simply.

The full skill is only about 620 estimated tokens when invoked. It does not add a framework,
runtime, or external service to your project.

## Install

For Claude Code:

```bash
claude plugin marketplace add ujjwalredd/sarathi
claude plugin install sarathi@sarathi
```

To install from a local clone:

```bash
git clone https://github.com/ujjwalredd/sarathi.git
cd sarathi
make install
```

The published plugin is version `0.2.0`.

## Why are there Bhagavad Gita references?

They are memory cues, not training data and not religious instruction.

A short name such as `action-not-fruit (BG 2.47)` points to a longer engineering reminder: solve
the real problem instead of optimizing the score that represents it. The installed skill uses nine
of these cues.

The source data is bundled so citations are not typed from memory. Sanskrit, literal summaries,
and the project's engineering readings are kept in separate fields in
[`skills/sarathi/references/anchors.json`](skills/sarathi/references/anchors.json). The Sanskrit
does not sit in the frequently loaded prompt.

The Bhagavad Gita is living scripture for many people. Sarathi makes no claim to religious
authority, and its engineering readings are clearly marked as interpretations created for this
project. Verse text comes from the public-domain [`gita/gita`](https://github.com/gita/gita)
dataset.

## What did the benchmark show?

We ran a small comparison against no skill, Caveman, and Ponytail using Codex `gpt-5.5`. The run
contained 14 synthetic tasks and one sample per task, for 56 isolated calls in total.

| Arm | Passed | Skill body | Mean answer tokens | Total tokens per pass |
|---|---:|---:|---:|---:|
| Control | 13/14 | 0 bytes | 394 | **15,619** |
| Caveman | 13/14 | 4,774 bytes | 223 | 16,693 |
| Ponytail | 13/14 | 5,700 bytes | **180** | 16,742 |
| **Sarathi** | **14/14** | **2,473 bytes** | 242 | 17,074 |

That is encouraging, but it is not a victory lap. Sarathi was the only arm to pass every task and
its instructions were less than half the size of either competing skill. It also used more total
tokens per successful answer.

The measured pass-rate lead was 7.1 percentage points, with a 95% interval from `-15.2` to `+31.5`.
The sample is too small to tell whether the lead is real. Codex did not report dollar cost either,
so this run does not prove cost savings.

In plain English: the skill looks useful and compact, but it has not earned a universal “better”
claim yet.

## Run it yourself

Free repository checks:

```bash
make check
```

Current result: 69 unit tests and 12 repository invariants pass.

Product comparison through Codex:

```bash
python bench/run.py \
  --backend codex \
  --model gpt-5.5 \
  --arms A F G H \
  --tasks reasoning minimalism \
  --n 1
```

Product comparison through Claude:

```bash
python bench/run.py \
  --backend claude \
  --model opus \
  --arms A F G H \
  --tasks reasoning minimalism \
  --n 1
```

Model calls can cost money, so start with `--n 1`. Each run records its model, CLI version, seed,
task hashes, prompt hashes, skill hash, outputs, usage, and confidence intervals in local
`results/`.

Raw runs and generated prompt arms are ignored by Git. The repository keeps the benchmark code,
tasks, scorer, and exact pinned competitor inputs, which are the pieces needed to reproduce a run.
Competitor revisions and hashes live in
[`bench/vendor/provenance.json`](bench/vendor/provenance.json).

## What is in this repository?

- [`skills/sarathi/`](skills/sarathi/) contains the installable skill and its references.
- [`bench/`](bench/) contains the benchmark runner, tasks, scorer, and pinned comparisons.
- [`.claude-plugin/`](.claude-plugin/) contains the Claude Code marketplace metadata.
- [`assets/banner.png`](assets/banner.png) is the banner shown above.

## License

Sarathi is MIT licensed. See [LICENSE](LICENSE). Vendored Caveman and Ponytail sources retain their
upstream text, provenance, and notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
