<div align="center">

<img src="assets/banner.png" alt="An ornate chariot drawn by four horses." width="100%">

# sarathi

<p lang="sa"><strong>योगः कर्मसु कौशलम्</strong></p>

<p><em>“Yoga is skill in action.”</em><br>
<sub><a href="https://github.com/gita/gita">Bhagavad Gita 2.50</a>, from the public-domain <code>gita/gita</code> dataset</sub></p>

<p><strong>Engineering interpretation:</strong> Plan carefully, then carry that care into execution.</p>

**A compact reasoning discipline that helps AI agents stay scoped, verify claims, and spend effort where risk requires it.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-69%20passing-brightgreen.svg)](bench/test_bench.py)
[![Invariants](https://img.shields.io/badge/invariants-12%20enforced-brightgreen.svg)](bench/validate.py)
[![Benchmark](https://img.shields.io/badge/benchmark-pilot%2C%20not%20proof-orange.svg)](#benchmark)

</div>

## What Sarathi does

Sarathi is an installable skill for coding agents. It teaches one practical loop:

1. Keep the requested outcome explicit.
2. Inspect evidence before prescribing a fix.
3. Match effort to risk.
4. Make the smallest root-cause change.
5. Verify before claiming success.

It also tells an agent to change hypotheses after repeated failures, preserve tests and safety
controls, avoid unrelated refactors, and keep final answers concise.

Use it for long implementation tasks, uncertain repository work, repeated failures, security or
payment code, and any situation where an agent might guess or stop too early. It is not a model,
training dataset, application server, or religious assistant.

## Install

Claude Code:

```bash
claude plugin marketplace add ujjwalredd/sarathi
claude plugin install sarathi@sarathi
```

Local clone:

```bash
make install
```

The marketplace command uses the real GitHub owner, `ujjwalredd`, not a placeholder organization.

## Why the Bhagavad Gita data is included

The Gita is not used to train or fine-tune a model. Sarathi uses nine short references as optional
memory cues for engineering failure modes. For example, `BG 2.47` points to focusing on the work
instead of gaming its metric.

The bundled source data serves three purposes:

- It prevents Sanskrit and citations from being typed from memory.
- It keeps literal summaries separate from this project's engineering interpretations.
- It lets the fidelity experiment test whether a model resolves each reference correctly.

Exact text, provenance, literal summaries, and operational interpretations are bundled with the
skill in [`skills/sarathi/references/anchors.json`](skills/sarathi/references/anchors.json). The
frequently loaded skill prompt contains no Sanskrit.

## Benchmark

### Latest exploratory pilot

The final local run used Codex CLI 0.142.3, `gpt-5.5`, medium reasoning, 14 synthetic tasks, one
sample per task and arm, and 56 isolated calls. Every call ran in a fresh empty directory with user
config and rules disabled.

| Arm | Skill body | Passed | 95% Wilson | Mean output tokens | Total tokens per pass |
|---|---:|---:|---:|---:|---:|
| Control | 0 bytes | 13/14 | [68.5%, 98.7%] | 394 | **15,619** |
| Caveman | 4,774 bytes | 13/14 | [68.5%, 98.7%] | 223 | 16,693 |
| Ponytail | 5,700 bytes | 13/14 | [68.5%, 98.7%] | **180** | 16,742 |
| **Sarathi** | **2,473 bytes** | **14/14** | [78.5%, 100.0%] | 242 | 17,074 |

Sarathi has the highest point pass rate and the smallest instruction body among the three skills.
Its body is 48.2% smaller than Caveman and 56.6% smaller than Ponytail.

This is not proof that Sarathi is better. Its `+7.1` percentage-point pass difference has a 95%
Newcombe interval of `[-15.2, +31.5]`, which includes harm, no effect, and benefit. Sarathi also
loses on total tokens per verified pass. Codex CLI did not report per-call dollar cost, so this run
does not prove dollar savings.

The suite was inspected while the skill and scorer were improved. Treat this as an exploratory
pilot. A credible superiority claim needs held-out executable tasks, hidden tests, independent task
authors, multiple models, and enough samples to resolve the expected effect.

### What is compared

| Arm | Content |
|---|---|
| A | no skill |
| F | exact pinned Caveman body |
| G | exact pinned Ponytail body |
| H | exact deployed Sarathi body |

Competitor commits and hashes are recorded in
[`bench/vendor/provenance.json`](bench/vendor/provenance.json). Generated arms are built from
tracked sources and are not committed.

The separate A to E codebook ablation asks whether correct Gita references compress full English
guidance better than labels or incorrect references. It is not used as the product comparison.

### Reproduce

Free checks:

```bash
make check
```

Current result: 69 unit tests and 12 repository invariants pass.

Codex pilot:

```bash
python bench/run.py \
  --backend codex \
  --model gpt-5.5 \
  --arms A F G H \
  --tasks reasoning minimalism \
  --n 1
```

Claude pilot:

```bash
python bench/run.py \
  --backend claude \
  --model opus \
  --arms A F G H \
  --tasks reasoning minimalism \
  --n 1
```

Model calls cost money. Start with `--n 1`. Each run records model, CLI version, seed, task and
prompt hashes, skill hash, usage, outputs, and confidence intervals under local `results/`.

Raw runs and generated arms are intentionally ignored by Git. This keeps the public repository
small and avoids publishing bulky model transcripts. The benchmark code, tasks, scorer, pinned
competitor inputs, and summary above remain public and reproducible.

## Repository layout

| Path | Purpose |
|---|---|
| `skills/sarathi/` | installable skill, Codex metadata, and sourced references |
| `.claude-plugin/` | Claude Code marketplace metadata |
| `bench/tasks/` | public reasoning and minimalism scenarios |
| `bench/vendor/` | exact pinned competitor skill sources and provenance |
| `bench/run.py` | isolated Claude and Codex benchmark driver |
| `bench/analyze.py` | confidence intervals, usage summaries, and manifest checks |
| `bench/validate.py` | repository and experiment integrity checks |

## Respect for the source text

The Bhagavad Gita is living scripture for many people. This project uses selected references as
engineering mnemonics and labels that use as its own interpretation. It claims no religious
authority and provides no spiritual, medical, legal, or financial advice.

Verse text comes from the public-domain [`gita/gita`](https://github.com/gita/gita) dataset.
In-copyright translations are not copied into this repository.

## License

MIT. See [LICENSE](LICENSE). Vendored Caveman and Ponytail sources retain their exact upstream
content, provenance, and required notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
