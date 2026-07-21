<div align="center">

<img src="assets/banner.png" alt="An ornate chariot drawn by four horses." width="50%">

# sarathi

<p lang="sa"><strong>योगः कर्मसु कौशलम्</strong></p>

<p><em>“Yoga is skill in action.”</em><br>
<sub><a href="https://github.com/gita/gita">Bhagavad Gita 2.50</a>, from the public-domain <code>gita/gita</code> dataset</sub></p>

<p><strong>Engineering interpretation:</strong> Plan carefully, then carry that care into execution.</p>

**A reasoning checklist for AI agents, plus a benchmark that tests whether its compact references actually help.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A63D2.svg)](https://claude.com/claude-code)
[![Tests](https://img.shields.io/badge/tests-48%20passing-brightgreen.svg)](bench/test_bench.py)
[![Codex pilot](https://img.shields.io/badge/Codex%20pilot-no%20measured%20gain-orange.svg)](#historical-benchmark-result)

</div>

## What does this repo do?

Sarathi has two parts:

1. **An agent skill.** It gives an AI agent a short checklist for staying focused during long, uncertain, or high-stakes work.
2. **A research benchmark.** It tests whether a short reference such as `BG 2.47` can remind a model of a full reasoning principle without repeating the whole explanation.

The main practical use is the skill. It is meant to help an agent avoid common mistakes such as:

- optimizing for a passing test instead of fixing the real problem
- drifting away from the task the user asked for
- guessing about files instead of reading them
- repeating a failed approach without learning from it
- thinking too little or overthinking a simple problem
- claiming that something works without verifying it
- making a decision that should remain with the user

The benchmark exists because a reasoning skill should not claim that it helps without evidence.

## Why is Bhagavad Gita data included?

The Bhagavad Gita data is **not used to train or fine-tune a model**. It is included for three specific reasons:

1. **The verses act as mnemonic references.** A short citation may point a model toward a longer idea that it already recognizes.
2. **The repository needs a reliable source of truth.** The Sanskrit and transliteration are loaded from the public-domain [`gita/gita`](https://github.com/gita/gita) dataset instead of being typed from memory.
3. **The benchmark must check the references.** `bench/fidelity.py` asks a model what each citation means and checks whether the answer contains the expected concepts.

For example, the project maps `BG 2.47` to a practical warning about reward hacking: focus on doing the work correctly instead of chasing the metric that represents it.

The literal meaning of a verse and this project's engineering interpretation are stored in separate fields. The repository does not claim that its software interpretation is the religious meaning of the text.

## How the skill works

The skill uses nine named reminders:

| Reminder | Reference | Practical purpose |
|---|---|---|
| `action-not-fruit` | BG 2.47 | Fix the real problem instead of gaming the metric |
| `steadiness` | BG 2.48 | Do not let one failed attempt make the next attempt careless |
| `drift-cascade` | BG 2.62-63 | Notice fixation before it turns into frustration and goal drift |
| `own-task` | BG 3.35 | Stay with the task the user actually requested |
| `inaction-is-action` | BG 4.18 | Treat not checking the environment as a deliberate choice |
| `effort-budget` | BG 6.16-17 | Avoid both premature answers and unnecessary overthinking |
| `skill-in-action` | BG 2.50 | Make execution quality match planning quality |
| `not-sole-cause` | BG 18.16 | Separate verified facts from assumptions and outside factors |
| `release-the-decision` | BG 18.63 | Give a clear recommendation, then leave the decision with the user |

The agent checks the task, available evidence, effort level, risk of drift, and who owns the final decision. The complete instructions are in [`skills/sarathi/SKILL.md`](skills/sarathi/SKILL.md).

## Install for Claude Code

```bash
claude plugin marketplace add ujjwalredd/sarathi
claude plugin install sarathi@sarathi
```

Both commands were tested with Claude Code 2.1.206 on 2026-07-21. The installed plugin reports version 0.1.0 and is enabled at user scope.

## How the benchmark works

The benchmark compares five prompt conditions. All derived prompts come from `reference/anchors.json`, so the content stays consistent across conditions.

| Arm | Prompt content | Question it answers |
|---|---|---|
| **A** | No guidance | How does the model behave without the skill? |
| **B** | Full English principles, about 476 tokens | Do the principles help at all? |
| **C** | Labels with correct references, about 144 tokens | Can the short references carry the full guidance? |
| **D** | Labels with real but incorrect references, about 144 tokens | Does reference accuracy matter? |
| **E** | Labels without references, about 114 tokens | Are the English labels doing all the work? |

The generated prompt in arm C is about 3.3 times shorter than arm B. That is only useful if C preserves the behavior of B and performs better than the label-only and wrong-reference controls.

```bash
python bench/build_arms.py
python bench/fidelity.py --n 5
python bench/run.py --arms A B C D E --n 3
```

These commands make paid model calls. Start with a small run.

### Compression experiment status

There is no valid five-arm result yet. The older `results/20260720-234003/` run is kept for audit purposes but is excluded because its model probe hit a session limit, its rows use an older result format, and the agent could inspect this repository while answering the benchmark prompts.

The current harness now runs each scenario in an empty temporary directory and rejects calls that do not return model and usage metadata.

## Historical benchmark result

A separate Codex pilot tested whether installing the complete skill improved answers to eight reasoning scenarios.

The pilot used skill SHA-256 `e23523624179668c6f8c0ee0b0b4c6cbdfdd45a679323af91cbe2efd5cd9ecf7`.
It was run before the wording in this repository was rewritten for clarity, so it is historical
evidence rather than a benchmark of the current text.

It did **not show an improvement**.

| Condition | Pass rate | Change from baseline | Confirmed `SKILL.md` reads | Mean output tokens per call |
|---|---:|---:|---:|---:|
| Skill not installed | 21/24 (87.5%) | Not applicable | 0/24 | 457.6 |
| Installed with automatic routing | 21/24 (87.5%) | 0.0 percentage points | 1/24 | 438.5 |
| Installed and explicitly requested | 19/24 (79.2%) | -8.3 percentage points | 21/24 | 576.0 |

The automatic condition matched the baseline and rarely produced direct evidence that the skill file was read. Explicit use scored lower and produced 25.9% more output tokens than the baseline. The confidence intervals are wide and include zero, so this small pilot does not prove benefit or harm. It only shows that this run found no improvement.

Test setup: Codex CLI 0.142.3, `gpt-5.5`, medium reasoning effort, eight tasks, three repetitions, and 24 fresh sessions per condition. The scoring rules were finalized before the treatment runs.

Artifacts:

- [Baseline](results/codex-skill/20260721-000238-baseline.json)
- [Automatic routing](results/codex-skill/20260721-000438-sarathi.json)
- [Explicit invocation](results/codex-skill/20260721-000710-sarathi-explicit.json)
- [Machine-readable comparison](results/codex-skill/20260721-comparison.json)

## Repository layout

| Path | Purpose |
|---|---|
| `skills/sarathi/SKILL.md` | Instructions loaded by the agent |
| `reference/anchors.json` | Sourced verses, literal summaries, and separate engineering interpretations |
| `bench/build_anchors.py` | Builds the reference file from the public-domain source dataset |
| `bench/build_arms.py` | Generates the five benchmark prompt conditions |
| `bench/fidelity.py` | Checks whether models recognize the verse references |
| `bench/run.py` | Runs the five-arm Claude benchmark |
| `bench/codex_skill.py` | Compares Codex before and after installing the skill |
| `bench/validate.py` | Enforces repository and experiment integrity rules |

## Integrity checks

Run:

```bash
python -m unittest discover bench -v
python bench/validate.py
```

The checks enforce these rules:

- every verse includes its source
- chapter 13 is excluded because verse numbering differs across recensions
- Sanskrit is not placed in the frequently loaded skill prompt
- literal summaries and engineering interpretations remain separate
- the full-text control does not contain verse references
- the wrong-reference and label-only controls remain valid
- every anchor has a fidelity probe
- plugin manifests and benchmark files parse correctly
- the skill stays within its prompt-size budget
- authored documentation, prompts, manifests, and source messages contain no em dashes

The current suite has 48 passing tests and 10 repository invariants.

## Respect for the source text

The Bhagavad Gita is living scripture. This project uses selected references as engineering mnemonics and clearly labels that use as its own interpretation. It claims no religious authority and provides no spiritual, medical, legal, or financial advice.

The Sanskrit source is public domain through [`gita/gita`](https://github.com/gita/gita). Plain-language summaries were checked against public-domain translations. In-copyright translations are not copied into the repository.

## Limitations

- The reference-compression idea may not work.
- Results can vary by model because different models may recognize the citations differently.
- The current behavior benchmark is small and starts from a high baseline score.
- Regular-expression scoring can miss nuance.
- Nine references are not enough to show that the method scales to a large knowledge base.
- A citation may change an answer's tone or make it longer, which can cancel the token savings.

## Related work

- `loadbearing`, an unpublished sibling project that supplied `bench/net.py`
- [LLMLingua](https://arxiv.org/pdf/2310.05736)
- [Prompt-compression survey](https://arxiv.org/html/2410.12388v2)
- [NVIDIA SkillSpector](https://github.com/nvidia/skillspector), which can scan plugins before installation

## License

MIT. See [LICENSE](LICENSE). The verse source is public domain through [`gita/gita`](https://github.com/gita/gita).
