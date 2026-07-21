<div align="center">

# sarathi

**The charioteer steers and counsels. The warrior decides and acts.**

An agent skill that encodes reasoning discipline as compact anchors — and the experiment that tests whether the encoding actually works.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-8A63D2.svg)](https://claude.com/claude-code)
[![Tests](https://img.shields.io/badge/tests-29%20passing-brightgreen.svg)](bench/test_bench.py)
[![Result](https://img.shields.io/badge/result-not%20yet%20measured-lightgrey.svg)](#the-experiment)

</div>

---

## The idea

Token-efficiency skills compress by **deleting** — fewer words, fewer lines, less hedging. That has a floor. Past it you are removing information and calling it compression.

This tests a different mechanism. **A widely-known text is a codebook already resident in the model's weights.** You don't pay to transmit a principle. You pay for a pointer into it.

```
"BG 2.62"                                              ~5 tokens
"beware the cascade where dwelling on a blocked goal
 breeds frustration, frustration distorts judgment,
 distorted judgment corrupts memory of the original
 objective, and corrupted memory destroys reasoning"  ~45 tokens
```

Across all nine anchors the measured ratio is **4.1×** — smaller than that single example suggests, and the honest number. Run `python bench/build_arms.py` to reproduce it.

The compression is real **only if the pointer resolves.** That conditional is the entire project, and it is measured rather than assumed.

## Why this text

The Bhagavad Gita is a good first codebook for three reasons: it is heavily represented in training data, so pointers plausibly resolve; it is public domain in Sanskrit; and it is specifically a treatise on *how minds fail at action under uncertainty* — the same subject as the 2026 agent-failure literature.

The mappings are tight enough to be worth taking seriously:

| Documented failure mode | Anchor | Fit |
|---|---|---|
| Reward hacking — RL post-training raises exploit rate 0.6% → 13.9% ([arXiv 2605.02964](https://arxiv.org/abs/2605.02964)) | `action-not-fruit` **BG 2.47** | "right to the action, never to its fruits" — optimize the action, not the metric |
| Doom loops, context rot, goal drift | `drift-cascade` **BG 2.62–63** | an 8-stage cascade ending in *smṛti-bhraṁśa* (memory loss) → *buddhi-nāśa* (reasoning collapse) |
| Overthinking **and** premature commitment, two opposite failures ([arXiv 2601.22311](https://arxiv.org/pdf/2601.22311)) | `effort-budget` **BG 6.16–17** | "not for one who eats too much, nor too little" — a rare two-sided budget rule |
| Scope creep | `own-task` **BG 3.35** | "better one's own duty imperfectly than another's done well" |
| Prefers internal simulation over checking the environment | `inaction-is-action` **BG 4.18** | "sees action in inaction" — not-checking is a choice |
| Sycophancy / railroading | `release-the-decision` **BG 18.63** | after 700 verses: "reflect fully, then do as you wish" |

That last one is the project's posture, and the name. Krishna is Arjuna's *charioteer*. He steers, he counsels completely, and he does not fight the battle. His closing line is not "therefore obey."

## Install

```bash
claude plugin marketplace add <your-org>/sarathi
claude plugin install sarathi@sarathi
```

## The experiment

Three arms. **B and C are generated from the same `reference/anchors.json`**, so they carry identical content and differ only in encoding — removing the author's prose as a confound.

| Arm | Content | Answers |
|---|---|---|
| **A** | nothing | control |
| **B** | principles spelled out (~576 tok) | do the principles help at all? |
| **C** | label + `BG x.y` (~142 tok) | does the pointer carry the same weight? |

```bash
python bench/build_arms.py          # regenerate arms from anchors
python bench/run.py --n 3           # three-arm run. real API spend.
python bench/fidelity.py --n 5      # do the pointers resolve? run this FIRST
python bench/net.py --baseline runs/<ts>/B --treatment runs/<ts>/C
```

**B vs C is the thesis.** A vs B is the necessary control — if B doesn't beat A, the principles are worthless and the compression question is moot.

Every outcome is publishable:

- **C ≈ B in behavior, C ≪ B in tokens** → anchoring is real compression. Novel result.
- **C < B** → pointers don't resolve reliably; the anchors are decoration. Worth knowing.
- **B ≈ A** → the principles don't help; the framing is the problem, not the encoding.

### No results yet

Deliberately. This project argues that unproven percentages are the disease in this category, so it does not get to ship one. The harness is here; the numbers go here when they exist.

`bench/fidelity.py` is the probe that can kill the whole idea, which is why it exists before any result: it asks the model what `BG 2.47` says, n times, and scores resolution **accuracy** (deterministic keyword grounding, no LLM judge) and **consistency** (variance across runs). A reference that means something different each time is not a pointer — it's noise.

## Integrity rules, enforced in CI

Run `python bench/validate.py`. Eight invariants, all failing the build:

- **No Sanskrit is ever typed by hand.** Verse text is fetched from [`gita/gita`](https://github.com/gita/gita) (Unlicense) and joined programmatically by `bench/build_anchors.py`. Citation hallucination runs 13–21% even under retrieval grounding; a project whose mechanism *is* "the reference resolves" cannot afford a wrong reference.
- **No chapter-13 anchors.** The source has 701 verses — 35 in chapter 13 where Shankara's recension has 34. "The Gita has 700 verses" is a recension choice, not a fact, and a `BG 13.x` pointer therefore does not resolve unambiguously. That is the project's own failure mode, so the chapter is excluded.
- **No Devanagari in the hot path.** It costs 2–4 tokens per character ([arXiv 2601.06142](https://arxiv.org/abs/2601.06142)); inlining it would destroy the saving being claimed. Script lives in `reference/`, loaded on demand.
- **`literal` and `operational` stay separate fields.** The engineering reading is this project's own, and must never be presented as what the verse means.
- **Arm B contains no verse references.** Otherwise it doesn't isolate the variable.
- **Every anchor has a fidelity probe**, or its reliability is untested.

## On the text

The Gita is living scripture for many people. This repo uses it as an engineering mnemonic — compact, widely-known handles for failure modes in acting under uncertainty — and says so rather than blurring it. The skill gives no spiritual, medical, legal, or financial advice, claims no religious authority, and keeps its operational readings in a field explicitly separate from the literal ones.

Translations used are public domain (Arnold 1885, Besant 1895, Ganguli 1883–96). In-copyright translations are deliberately excluded — notably Prabhupada's, which is BBT-owned and [has been litigated](https://spicyip.com/2017/02/printing-the-bhagavad-gita-copyright-protection-of-translations.html).

## Development

```bash
python bench/build_anchors.py --source /tmp/gita_verse.json   # regenerate reference
python bench/build_arms.py                                     # regenerate arms
python -m unittest discover bench -v                           # 29 tests, stdlib only
python bench/validate.py                                       # 8 invariants
```

No runtime dependencies. Python 3.10+.

## Honest limitations

- **The mechanism may not work.** Central risk, measured by `fidelity.py` rather than assumed.
- **Register contamination.** Verse references may pull the model toward ornate or devotional prose, inflating output tokens and eating the saving. Arm C measures output length, so this surfaces rather than hides.
- **Results won't transfer across models.** Anchoring depends on training-data representation, so this is more model-bound than an ordinary skill. Every run records its model id.
- **Keyword scoring is coarse.** It detects a missing concept; it cannot fully judge whether a resolution is *right*. Real gap.
- **Nine anchors is a small codebook.** Whether the mechanism generalizes to hundreds is untested.

## Related

- [loadbearing](https://github.com/<your-org>/loadbearing) — sibling project; `bench/net.py` is copied from it
- [LLMLingua](https://arxiv.org/pdf/2310.05736), [prompt-compression survey](https://arxiv.org/html/2410.12388v2) — prior art, which compresses by pruning or learned soft tokens rather than by shared priors
- [NVIDIA/SkillSpector](https://github.com/nvidia/skillspector) — scan any plugin before installing, including this one

## License

MIT — see [LICENSE](LICENSE). Verse text is public domain via [`gita/gita`](https://github.com/gita/gita) (Unlicense).
