<div align="center">

<img src="assets/banner.png" alt="An ornate chariot drawn by four horses." width="100%">

# sarathi

<p lang="sa"><strong>योगः कर्मसु कौशलम्</strong></p>

<p><em>“Yoga is skill in action.”</em><br>
<sub><a href="https://github.com/gita/gita">Bhagavad Gita 2.50</a></sub></p>

<p><strong>Plan carefully, then carry that care into execution.</strong></p>

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

Coding agents usually know how to write code. The harder part is staying honest about the work:
reading the real files, fixing the cause instead of the symptom, respecting risk, and running the
one check that can prove the change works.

Sarathi is a compact instruction set for that discipline. It is not a framework or runtime. It
adds no dependency to the project being edited. Its current body is 2,077 bytes and tells an agent
to seek the lowest-cost verified success, stop after decisive evidence, and say plainly when the
evidence is missing.

## When is it useful?

Sarathi is meant for agent work where a confident wrong answer is expensive:

- repository changes that need inspection and tests
- bugs where the first fix may only hide the symptom
- stateful, concurrent, security-sensitive, or irreversible behavior
- repeated failed attempts that need a new hypothesis
- recommendations where the final tradeoff belongs to the user

For a simple question, it should stay out of the way and answer briefly.

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

## Why is the Bhagavad Gita data here?

It is a citation library, not a training dataset and not religious instruction.

Nine short references act as names for recurring engineering failures. For example,
`action-not-fruit` reminds the agent to solve the real problem instead of gaming the visible score.
The operational rule and the verse's literal meaning are stored separately. Sanskrit is kept out
of the frequently loaded skill prompt.

The source data prevents quotes and verse numbers from being invented from memory. Exact text,
literal summaries, project interpretations, and sources live in
[`skills/sarathi/references/anchors.json`](skills/sarathi/references/anchors.json). Verse data comes
from the public-domain [`gita/gita`](https://github.com/gita/gita) project. Sarathi claims no
religious authority.

## What did the executable benchmark show?

Sarathi became cheaper, but it did not beat everything.

The fresh v2 comparison used Codex `gpt-5.5` at medium reasoning effort, eight repository-repair
tasks, four arms, and one sample per task. That is 32 model calls. Each agent received the same
starter file and specification. The grader ran 62 hidden assertions only after the agent exited.
Independent reference implementations passed all 62 assertions before scoring.

| Arm | Passed | Skill body | Mean fresh input | Mean cached input | Mean output | Raw tokens per verified pass |
|---|---:|---:|---:|---:|---:|---:|
| Control | **8/8** | 0 bytes | 17,161 | **107,920** | 4,067 | **129,148** |
| Caveman | 7/8 | 4,774 bytes | 19,429 | 130,224 | 4,024 | 175,631 |
| Ponytail | **8/8** | 5,700 bytes | 25,054 | 173,232 | 4,225 | 202,511 |
| Sarathi | 7/8 | **2,077 bytes** | **16,894** | 130,144 | **3,971** | 172,581 |

On this run, Sarathi tied Caveman on correctness and used 1.7% fewer raw tokens per verified pass.
It used 14.8% fewer than Ponytail, but Ponytail passed one more task. The no-skill control was both
the most accurate and the cheapest.

The two failed arms missed different version-1 validation details in the same state-migration
task. Sarathi returned the wrong exception class because it checked schema shape before checking
the version type. Caveman preserved version-1 label order when the output required sorting.

This sample is too small for a victory claim. Sarathi's pass-rate difference from Caveman was
0 percentage points with a 95% interval from -36.1 to +36.1. Its difference from Ponytail and the
control was -12.5 points with an interval from -47.1 to +21.5. None was statistically significant.

“Raw tokens” adds fresh input, cached input, and output tokens at equal weight. That is useful for
reproduction, but it is not a dollar estimate because cached and uncached tokens can have different
prices, and this Codex run did not report monetary cost. The benchmark therefore does not prove
dollar savings.

## How the comparison is kept honest

- Sarathi was frozen before the v2 tasks were written.
- Caveman and Ponytail use exact bodies from pinned upstream commits. Revisions and hashes are in
  [`bench/vendor/provenance.json`](bench/vendor/provenance.json).
- Job order is randomized with a recorded seed, then run serially to avoid quota-related timeouts.
- A temporary Codex home prevents installed Sarathi, Caveman, or Ponytail skills from leaking into
  the control or another arm.
- A preflight confirms that candidate commands cannot write to this repository or the normal home
  directory and cannot access the network.
- Skipped hidden tests are infrastructure-invalid, never passes.
- Raw outputs, candidate snapshots, and run metadata stay under ignored `results/`. They are not
  pushed to GitHub.

This is a local evaluation harness for ordinary model output, not hostile-code isolation. The
macOS Codex sandbox permits broader filesystem reads than a dedicated VM. Use a disposable VM or
dedicated account when evaluating untrusted candidates.

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

## What would count as a real win?

A stronger claim needs a preregistered larger suite, repeated samples, no accuracy loss, lower
measured cost per verified pass, and confidence intervals narrow enough to rule out a practical
regression. Until then, the honest conclusion is smaller and cheaper than the two competitor
prompts in this run, tied with Caveman on correctness, and behind Ponytail and the control.

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
