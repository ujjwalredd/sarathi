#!/usr/bin/env python3
"""Generate the codebook ablation and deployed Sarathi benchmark prompts.

The experiment asks whether a short verse reference can carry the same practical
guidance as a full English explanation. Generating every condition from one file
keeps the comparison fair and reproducible.

The five conditions are:

    arm A   nothing                          control
    arm B   `operational` text in full       the principle, spelled out
    arm C   label + correct `BG x.y`         the principle, as a pointer
    arm D   label + incorrect `BG x.y`       control: does correctness matter?
    arm E   label alone, no reference        control: does the pointer matter?

Arm H is separate from that controlled ablation. It contains the body of the
actual installed Sarathi skill and is the only Sarathi arm that should be used
for product comparisons against vendored competitor skill bodies F and G.

The two control conditions answer questions that A, B, and C cannot answer alone.
The label may carry the idea without the verse, and a reference may influence the
model even when it points to the wrong verse.

    C vs E   does the reference add anything over the English label?
    C vs D   does a correct reference beat an incorrect one?

Arm D uses a fixed random seed to select real but incorrect verses. This keeps it
close to arm C in length while changing only the accuracy of the references.

Usage:
    python bench/build_arms.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = ROOT / "skills/sarathi/SKILL.md"
ANCHORS_PATH = ROOT / "skills/sarathi/references/anchors.json"
VENDOR_DIR = ROOT / "bench/vendor"
PROVENANCE_PATH = VENDOR_DIR / "provenance.json"

PREAMBLE = (
    "Use the following reasoning checklist while answering this task. "
    "Review it when you make an important decision.\n"
)

CHECKPOINTS = [
    ("Duty", "what was actually asked, not what would be more interesting", "own-task"),
    ("Separate", "what can I act on, versus what can I only react to", "action-not-fruit"),
    ("Budget", "am I closer to too little thought, or too much", "effort-budget"),
    ("Act", "including choosing not to act, named as a choice", "inaction-is-action"),
    ("Drift", "is the objective I am serving the one I started with", "drift-cascade"),
    ("Release", "give the full recommendation, let the decision be the user's", "release-the-decision"),
]


def load_anchors() -> list[dict]:
    try:
        return json.loads(ANCHORS_PATH.read_text(encoding="utf-8"))["anchors"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: cannot load anchors.json: {exc}", file=sys.stderr)
        print("hint: run bench/build_anchors.py first", file=sys.stderr)
        raise SystemExit(1)


def build_a() -> str:
    return ""


def build_b(anchors: list[dict]) -> str:
    """Build the condition that spells out every principle in plain English."""
    lines = [PREAMBLE]
    for anchor in anchors:
        lines.append(f"- {anchor['operational']}")
    lines.append("\nAt each decision point, check:")
    for name, gloss, _ in CHECKPOINTS:
        lines.append(f"- {name}: {gloss}.")
    return "\n".join(lines) + "\n"


def build_c(anchors: list[dict]) -> str:
    """Build the condition that uses labels with correct references."""
    lines = [PREAMBLE]
    for anchor in anchors:
        refs = ", ".join(anchor["refs"])
        lines.append(f"- {anchor['id']} ({refs})")
    lines.append("\nAt each decision point, check:")
    for name, _, anchor_id in CHECKPOINTS:
        lines.append(f"- {name}: {anchor_id}.")
    return "\n".join(lines) + "\n"


# Standard-recension verse counts. Used to generate wrong-but-real references
# for arm D. Chapter 13 is excluded: it has 34 or 35 verses depending on
# recension, so a BG 13.x pointer is ambiguous - which is the exact failure this
# project measures. Leaving it out avoids adding unrelated ambiguity to the control.
CHAPTER_LENGTHS = {
    1: 47, 2: 72, 3: 43, 4: 42, 5: 29, 6: 47, 7: 30, 8: 28, 9: 34,
    10: 42, 11: 55, 12: 20, 14: 27, 15: 20, 16: 24, 17: 28, 18: 78,
}
SCRAMBLE_SEED = 1729


def scramble_refs(anchors: list[dict], seed: int = SCRAMBLE_SEED) -> dict[str, list[str]]:
    """Map each anchor to real but incorrect verse references.

    Deterministic, so arm D is reproducible across runs and machines. Guarantees:
      - same number of refs per anchor as arm C (so token cost matches)
      - never the correct reference for that anchor
      - never any reference used correctly by another anchor, so the model
        cannot accidentally receive a right answer through the back door
      - never chapter 13
    """
    correct = {ref for a in anchors for ref in a["refs"]}
    rng = random.Random(seed)
    chapters = sorted(CHAPTER_LENGTHS)
    used: set[str] = set()
    out: dict[str, list[str]] = {}

    for anchor in anchors:
        refs = []
        for _ in anchor["refs"]:
            for _attempt in range(10_000):
                chapter = rng.choice(chapters)
                verse = rng.randint(1, CHAPTER_LENGTHS[chapter])
                candidate = f"BG {chapter}.{verse}"
                if candidate not in correct and candidate not in used:
                    refs.append(candidate)
                    used.add(candidate)
                    break
            else:  # pragma: no cover - only if the verse space were exhausted
                raise RuntimeError("could not find a distinct wrong reference")
        out[anchor["id"]] = refs
    return out


def build_d(anchors: list[dict]) -> str:
    """Build the condition that pairs each label with a real but incorrect reference.

    If D matches C, the model is responding to the shape of a reference rather
    than to the verse it points at.
    """
    wrong = scramble_refs(anchors)
    lines = [PREAMBLE]
    for anchor in anchors:
        lines.append(f"- {anchor['id']} ({', '.join(wrong[anchor['id']])})")
    lines.append("\nAt each decision point, check:")
    for name, _, anchor_id in CHECKPOINTS:
        lines.append(f"- {name}: {anchor_id}.")
    return "\n".join(lines) + "\n"


def build_e(anchors: list[dict]) -> str:
    """Build the condition that uses labels without verse references.

    If E matches C, the English label is doing the useful work and the verse
    reference adds no measurable value. This is an important control because it
    can disprove the project's central idea.
    """
    lines = [PREAMBLE]
    for anchor in anchors:
        lines.append(f"- {anchor['id']}")
    lines.append("\nAt each decision point, check:")
    for name, _, anchor_id in CHECKPOINTS:
        lines.append(f"- {name}: {anchor_id}.")
    return "\n".join(lines) + "\n"


def skill_body(text: str) -> str:
    """Return body loaded after skill routing, excluding YAML metadata."""
    if not text.startswith("---\n"):
        raise ValueError("skill is missing opening YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError("skill has unterminated YAML frontmatter")
    body = parts[2].lstrip("\n")
    if not body.strip():
        raise ValueError("skill body is empty")
    return body


def build_h() -> str:
    """Build the product arm from the exact deployed Sarathi skill body."""
    try:
        return skill_body(SKILL_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"cannot read {SKILL_PATH}: {exc}") from exc


def build_vendor_arms() -> dict[str, str]:
    """Build competitor arms from exact pinned source snapshots."""
    try:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load competitor provenance: {exc}") from exc

    arms = {}
    for name, item in provenance.get("skills", {}).items():
        source_path = VENDOR_DIR / f"{name}-SKILL.md"
        try:
            source = source_path.read_bytes()
            if hashlib.sha256(source).hexdigest() != item["source_sha256"]:
                raise ValueError("source SHA-256 does not match provenance")
            if len(source) != item["source_bytes"]:
                raise ValueError("source size does not match provenance")
            body = skill_body(source.decode("utf-8"))
            body_bytes = body.encode("utf-8")
            if hashlib.sha256(body_bytes).hexdigest() != item["arm_sha256"]:
                raise ValueError("derived arm SHA-256 does not match provenance")
            if len(body_bytes) != item["arm_bytes"]:
                raise ValueError("derived arm size does not match provenance")
            arms[item["arm"]] = body
        except (OSError, KeyError, ValueError) as exc:
            raise RuntimeError(f"cannot build competitor arm for {name}: {exc}") from exc
    return arms


def build_all() -> dict[str, str]:
    """Render every arm from tracked source files without network access."""
    anchors = load_anchors()
    return {
        "A": build_a(),
        "B": build_b(anchors),
        "C": build_c(anchors),
        "D": build_d(anchors),
        "E": build_e(anchors),
        **build_vendor_arms(),
        "H": build_h(),
    }


def estimate_tokens(text: str) -> int:
    """Rough char/4 heuristic. Real counts come from net.py against session logs.

    Deliberately not presented as authoritative - this is for a build-time sanity
    signal, not for the published result.
    """
    return len(text) // 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate experiment arms from anchors.json")
    parser.add_argument("--out", type=Path, default=ROOT / "bench/arms")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    arms = build_all()
    for name, text in arms.items():
        (args.out / f"{name}.txt").write_text(text, encoding="utf-8")

    print(f"  {len(load_anchors())} anchors → {len(arms)} arms in {args.out}\n")
    print(f"  {'arm':<6}{'chars':>8}{'~tokens':>10}   content")
    print("  " + "─" * 62)
    labels = {
        "A": "nothing (control)",
        "B": "principles spelled out",
        "C": "label + correct reference",
        "D": "label + incorrect reference (control)",
        "E": "label only, no reference (control)",
        "F": "pinned Caveman skill body",
        "G": "pinned Ponytail skill body",
        "H": "deployed Sarathi skill body",
    }
    for name, text in arms.items():
        print(f"  {name:<6}{len(text):>8}{estimate_tokens(text):>10}   {labels[name]}")

    b_tok, c_tok = estimate_tokens(arms["B"]), estimate_tokens(arms["C"])
    if c_tok:
        print("  " + "─" * 62)
        print(f"  B/C ratio: {b_tok / c_tok:.1f}x if the references resolve correctly")
        print("\n  key comparisons:")
        print("    C vs B   does the pointer carry the spelled-out principle?")
        print("    C vs E   does the reference add anything over the label alone?")
        print("    C vs D   does a correct reference beat an incorrect one?\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
